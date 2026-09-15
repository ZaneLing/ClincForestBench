from __future__ import annotations

import re
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

from backend.app.domain.temporal import TemporalCase

from .common import (
    ROOT,
    TemporalAdapter,
    build_mvp_simulations,
    build_temporal_graph,
    iso,
    make_event,
    parse_time,
    relative_minutes,
)


class MIMICTemporalAdapter(TemporalAdapter):
    dataset_slug = "mimic"
    dataset_name = "MIMIC-IV multimodal"

    def __init__(self, root: Path = ROOT):
        super().__init__(root)
        self.mimic = root / "dataset/restricted/mimiciv/3.1"
        self.notes = root / "dataset/restricted/mimic-iv-note/2.2"
        self.ecg = root / "dataset/restricted/mimic-iv-ecg"
        self.ed = root / "dataset/restricted/mimic-iv-ed-v2.2"
        self._prepared = False

    def list_cases(self, limit: int = 20) -> List[Dict[str, Any]]:
        query = f"""
            WITH dx AS (
              SELECT d.subject_id,d.hadm_id,
                     min(CASE WHEN d.seq_num=1 THEN i.long_title END) primary_dx,
                     sum(CASE WHEN regexp_matches(lower(i.long_title),
                         'pneumonia|sepsis|respiratory failure|influenza|covid|aspiration')
                         THEN 1 ELSE 0 END) target_count
              FROM read_csv_auto('{self.mimic / 'hosp/diagnoses_icd.csv.gz'}', header=true) d
              JOIN read_csv_auto('{self.mimic / 'hosp/d_icd_diagnoses.csv.gz'}', header=true) i
                USING(icd_code,icd_version)
              GROUP BY d.subject_id,d.hadm_id
            ), candidate AS (
              SELECT a.subject_id,a.hadm_id,a.admittime,a.dischtime,
                     a.admission_type,a.admission_location,dx.primary_dx,
                     e.stay_id,e.intime ed_intime,e.outtime ed_outtime,e.arrival_transport
              FROM read_csv_auto('{self.mimic / 'hosp/admissions.csv.gz'}', header=true) a
              JOIN dx USING(subject_id,hadm_id)
              JOIN read_csv_auto('{self.ed / 'ed/edstays.csv.gz'}', header=true) e
                USING(subject_id,hadm_id)
              JOIN read_csv_auto('{self.ed / 'ed/triage.csv.gz'}', header=true) t
                USING(subject_id,stay_id)
              WHERE dx.target_count > 0
                AND regexp_matches(lower(dx.primary_dx),
                    'pneumonia|sepsis|respiratory failure|influenza|covid|aspiration')
                AND (a.admission_type IN ('EW EMER.','DIRECT EMER.','URGENT')
                     OR lower(a.admission_location) LIKE '%emergency%')
              ORDER BY a.hadm_id LIMIT 600
            ), rad AS (
              SELECT r.hadm_id,count(*) rads
              FROM read_csv_auto('{self.notes / 'note/radiology.csv.gz'}', header=true) r
              JOIN candidate c USING(hadm_id) GROUP BY r.hadm_id
            ), ds AS (
              SELECT d.hadm_id,count(*) discharge_notes
              FROM read_csv_auto('{self.notes / 'note/discharge.csv.gz'}', header=true) d
              JOIN candidate c USING(hadm_id) GROUP BY d.hadm_id
            ), ecgs AS (
              SELECT c.hadm_id,count(*) ecg_count
              FROM candidate c
              JOIN read_csv_auto('{self.ecg / 'record_list.csv'}', header=true) e
                ON c.subject_id=e.subject_id
               AND e.ecg_time BETWEEN c.admittime
                                      AND c.admittime + INTERVAL '24 hours'
              GROUP BY c.hadm_id
            )
            SELECT c.*,rad.rads,ds.discharge_notes,ecgs.ecg_count
            FROM candidate c JOIN rad USING(hadm_id) JOIN ds USING(hadm_id)
            JOIN ecgs USING(hadm_id)
            WHERE rad.rads >= 1 AND ds.discharge_notes >= 1 AND ecgs.ecg_count >= 1
            ORDER BY rad.rads + ecgs.ecg_count DESC,c.hadm_id
            LIMIT {int(limit)}
        """
        cursor = self.connection.execute(query)
        columns = [item[0] for item in cursor.description]
        candidates = [dict(zip(columns, row)) for row in cursor.fetchall()]
        self._prepare_filtered_sources(candidates)
        return candidates

    def _prepare_filtered_sources(self, candidates: List[Dict[str, Any]]) -> None:
        if self._prepared:
            return
        self.connection.execute(
            "CREATE TEMP TABLE temporal_mimic_candidates(subject_id BIGINT,hadm_id BIGINT,stay_id BIGINT)"
        )
        self.connection.executemany(
            "INSERT INTO temporal_mimic_candidates VALUES (?,?,?)",
            [
                (item["subject_id"], item["hadm_id"], item["stay_id"])
                for item in candidates
            ],
        )
        sources = (
            ("poe", self.mimic / "hosp/poe.csv.gz", "hadm_id"),
            ("labs", self.mimic / "hosp/labevents.csv.gz", "hadm_id"),
            ("radiology", self.notes / "note/radiology.csv.gz", "hadm_id"),
            ("discharge", self.notes / "note/discharge.csv.gz", "hadm_id"),
            ("ecg", self.ecg / "machine_measurements.csv", "subject_id"),
        )
        for name, path, key in sources:
            reader_options = "header=true"
            if name == "labs":
                reader_options += ",all_varchar=true,strict_mode=false,null_padding=true,parallel=false"
            self.connection.execute(
                f"""CREATE TEMP TABLE temporal_mimic_{name} AS
                    SELECT source.* FROM read_csv_auto('{path}',{reader_options}) source
                    JOIN (SELECT DISTINCT {key} FROM temporal_mimic_candidates) candidate
                      USING({key})"""
            )
        self._prepared = True

    def load_case(self, candidate: Dict[str, Any]) -> TemporalCase:
        subject_id = int(candidate["subject_id"])
        hadm_id = int(candidate["hadm_id"])
        stay_id = int(candidate["stay_id"])
        case_id = f"CFB_MIMIC_{hadm_id}"
        anchor = parse_time(candidate["admittime"])
        discharge = parse_time(candidate["dischtime"])
        if not anchor or not discharge:
            raise ValueError("MIMIC admission anchor is incomplete")

        lab_orders = self._poe_orders(hadm_id, "Lab")
        rad_orders = self._poe_orders(hadm_id, "Radiology")
        ecg_orders = self._poe_orders(hadm_id, "Cardiology", "ECG")
        events = self._lab_events(case_id, subject_id, hadm_id, anchor, lab_orders)
        events.extend(
            self._radiology_events(case_id, subject_id, hadm_id, anchor, rad_orders)
        )
        ecg_events = self._ecg_events(
            case_id, subject_id, anchor, ecg_orders
        )
        events.extend(ecg_events)
        events.sort(key=lambda item: (item.order_min(), item.available_min(), item.event_id))

        eligible = [item for item in events if item.arena.arena_eligible]
        if len(eligible) < 5 or not any(
            item.clinical_concept.modality == "IMAGING" for item in events
        ):
            raise ValueError("insufficient MIMIC temporal evidence")
        patient = self._patient(subject_id, anchor)
        triage = self._triage(stay_id)
        discharge_note = self._discharge_note(hadm_id)
        sections = _extract_presentation_sections(discharge_note or "")
        initial_state = {
            "age": patient["age"],
            "sex": patient["gender"],
            "chief_complaint": triage.get("chiefcomplaint") or sections.get("chief_complaint"),
            "arrival_transport": candidate.get("arrival_transport"),
            "triage_acuity": triage.get("acuity"),
            "triage_vitals": {
                "temperature_f": triage.get("temperature"),
                "heart_rate": triage.get("heartrate"),
                "respiratory_rate": triage.get("resprate"),
                "spo2": triage.get("o2sat"),
                "sbp": triage.get("sbp"),
                "dbp": triage.get("dbp"),
                "pain": triage.get("pain"),
            },
            "presentation_hpi": sections.get("history_of_present_illness"),
        }
        diagnoses = self._diagnoses(hadm_id)
        reference = {
            "hospital_principal_diagnosis": diagnoses[:1],
            "discharge_diagnoses": diagnoses,
            "definitive_findings": [],
            "adjudicated_primary_diagnosis": diagnoses[0] if diagnoses else candidate.get("primary_dx"),
            "reference_strength": "CODER_ASSIGNED_REVIEW_REQUIRED",
            "is_absolute_ground_truth": False,
        }
        warnings = [
            "DISCHARGE_NOTE_USED_ONLY_FOR_PRE_ADMISSION_SECTIONS_REVIEW_REQUIRED",
            "INTERVENTION_BOUNDARY_NOT_FULLY_RESOLVED_IN_MVP",
        ]
        if ecg_events:
            warnings.append("MIMIC_ECG_MACHINE_CLOCK_MAY_NOT_BE_SYNCHRONIZED")
        diagnostic = [item for item in events if item.clinical_concept.modality in {"LAB", "IMAGING", "ECG"}]
        temporal_complete = sum(
            item.time.relative_available_min is not None for item in diagnostic
        ) / max(1, len(diagnostic))
        checks = {
            "anchor_present": True,
            "initial_state_has_no_future_diagnosis": "diagnosis" not in initial_state,
            "real_results_only": all(item.provenance.is_observed_real_result for item in events),
            "ecg_clock_uncertainty_recorded": not ecg_events
            or "MIMIC_ECG_MACHINE_CLOCK_MAY_NOT_BE_SYNCHRONIZED" in warnings,
            "mvp_branchable": len(eligible) >= 5,
        }
        trajectory = [
            {
                "sequence": index,
                "event_id": item.event_id,
                "action_id": item.action_id,
                "order_time_min": item.time.relative_order_min,
                "acquired_time_min": item.time.relative_acquired_min,
                "available_time_min": item.time.relative_available_min,
                "latency_min": round(max(0, item.available_min() - item.order_min()), 2),
                "temporal_confidence": item.time.temporal_confidence.value,
            }
            for index, item in enumerate(events, 1)
        ]
        graph = build_temporal_graph(case_id, events, reference)
        return TemporalCase(
            case_id=case_id,
            task_type="HOSPITAL_PRESENTATION_TEMPORAL_DIAGNOSIS",
            source={
                "dataset_family": "MIMIC",
                "dataset_version": "MIMIC-IV 3.1 + Note 2.2 + ECG snapshot + ED 2.2",
                "source_case_id": str(hadm_id),
                "subject_id": str(subject_id),
                "ed_stay_id": str(stay_id),
                "modalities": ["MIMIC-IV", "MIMIC-IV-Note", "MIMIC-IV-ECG", "MIMIC-IV-ED"],
                "access_class": "PHYSIONET_CREDENTIALLED_LOCAL_ONLY",
            },
            anchor={
                "anchor_type": "HOSPITAL_ADMISSION",
                "absolute_time": iso(anchor),
                "relative_zero": 0,
                "time_system": "DEIDENTIFIED",
                "timezone_policy": "SOURCE_NATIVE",
            },
            initial_state=initial_state,
            timeline_events=events,
            queryable_context=[
                {
                    "action_id": "REVIEW_PAST_MEDICAL_HISTORY",
                    "items": [sections.get("past_medical_history")]
                    if sections.get("past_medical_history")
                    else [],
                    "source": "discharge_summary_section_parser",
                    "temporal_scope": "PRE_ADMISSION_ONLY_REVIEW_REQUIRED",
                },
                {
                    "action_id": "REVIEW_HOME_MEDICATIONS",
                    "items": self._med_reconciliation(stay_id),
                    "source": "MIMIC-IV-ED medrecon",
                },
            ],
            hidden_evidence_pool=[item.event_id for item in eligible],
            realized_trajectory=trajectory,
            reference=reference,
            case_quality={
                "evidence_count": len(diagnostic),
                "modality_count": len({item.clinical_concept.modality for item in diagnostic}),
                "temporal_completeness": round(temporal_complete, 3),
                "timeline_consistency": all(item.available_min() >= item.order_min() for item in events),
                "branchability": min(1.0, len(eligible) / 10),
                "reference_quality": "HUMAN_REVIEW_REQUIRED",
                "pre_intervention_evidence_count": len(eligible),
                "checks": checks,
            },
            temporal_quality={
                "anchor_confidence": "EXACT",
                "core_event_minimum_confidence": "MEDIUM",
                "warnings": warnings,
                "ecg_time_policy": "MACHINE_CLOCK_LOW_OR_MEDIUM_CONFIDENCE; NEVER_MINUTE_PRECISE_AGAINST_OTHER_SYSTEMS",
            },
            arena_config={
                "time_mode": "WAIT_FOR_NEXT_RESULT",
                "time_bucket_min": 5,
                "unobserved_action_result": "UNOBSERVED_IN_RECORDED_EPISODE",
                "max_questions": 30,
                "free_reorder_scope": "FIRST_24H_DIAGNOSTIC_EVIDENCE; HUMAN_INTERVENTION_REVIEW_PENDING",
            },
            temporal_graph=graph,
            mvp_simulations=build_mvp_simulations(events),
        )

    def _poe_orders(self, hadm_id: int, order_type: str, subtype: Optional[str] = None):
        sql = f"""SELECT poe_id,ordertime,order_type,order_subtype,order_status
                   FROM temporal_mimic_poe
                   WHERE hadm_id=? AND order_type=?"""
        parameters: List[Any] = [hadm_id, order_type]
        if subtype:
            sql += " AND order_subtype=?"
            parameters.append(subtype)
        sql += " ORDER BY ordertime"
        return [
            {"id": row[0], "time": parse_time(row[1]), "type": row[2], "subtype": row[3], "status": row[4]}
            for row in self.connection.execute(sql, parameters).fetchall()
        ]

    def _lab_events(self, case_id: str, subject_id: int, hadm_id: int, anchor: datetime, orders):
        rows = self.connection.execute(
            f"""SELECT l.specimen_id,
                       min(try_cast(l.charttime AS TIMESTAMP)) acquired_time,
                       max(try_cast(l.storetime AS TIMESTAMP)) available_time,
                       list(struct_pack(label := d.label, value := l.value, number_value := try_cast(l.valuenum AS DOUBLE),
                                        unit := l.valueuom, flag := l.flag)
                            ORDER BY d.label) components
                FROM temporal_mimic_labs l
                JOIN read_csv_auto('{self.mimic / 'hosp/d_labitems.csv.gz'}',header=true) d USING(itemid)
                WHERE try_cast(l.hadm_id AS BIGINT)=?
                  AND try_cast(l.charttime AS TIMESTAMP) BETWEEN ? AND ?
                GROUP BY l.specimen_id ORDER BY acquired_time LIMIT 14""",
            [hadm_id, anchor, anchor + timedelta(hours=24)],
        ).fetchall()
        events = []
        for index, (specimen_id, acquired, available, components) in enumerate(rows, 1):
            acquired_dt = parse_time(acquired)
            available_dt = parse_time(available) or acquired_dt
            order = _nearest_preceding(orders, acquired_dt, timedelta(hours=6))
            order_time = order["time"] if order else None
            consistent = not order_time or not available_dt or available_dt >= order_time
            display = _lab_panel_name(components)
            events.append(
                make_event(
                    case_id=case_id,
                    event_id=f"{case_id}::LAB::{index:02d}",
                    event_type="LAB_RESULT",
                    display=display,
                    modality="LAB",
                    dataset="MIMIC-IV 3.1",
                    source_table="labevents+d_labitems+poe",
                    source_row_id=str(specimen_id),
                    anchor=anchor,
                    order_time=order_time,
                    acquired_time=acquired_dt,
                    available_time=available_dt,
                    confidence="MEDIUM" if order else "HIGH",
                    availability_semantics="LAB_SYSTEM_STORETIME",
                    result={"specimen_id": str(specimen_id), "components": [dict(item) for item in components]},
                    arena_eligible=bool(order and consistent),
                    leakage_risk="MEDIUM" if not order else "LOW",
                    exclusion_reason=None if order and consistent else "NO_RELIABLE_ORDER_LINK",
                    replay_mode=(
                        "OBSERVED_RESULT_WITH_SHIFTED_TAT" if order and consistent else "OBSERVED_FIXED_TIME"
                    ),
                )
            )
        return events

    def _radiology_events(self, case_id: str, subject_id: int, hadm_id: int, anchor: datetime, orders):
        rows = self.connection.execute(
            f"""SELECT note_id,charttime,storetime,text
                FROM temporal_mimic_radiology
                WHERE hadm_id=? AND charttime BETWEEN ? AND ?
                ORDER BY charttime LIMIT 6""",
            [hadm_id, anchor, anchor + timedelta(hours=48)],
        ).fetchall()
        events = []
        for index, (note_id, charttime, storetime, text) in enumerate(rows, 1):
            acquired = parse_time(charttime)
            available = parse_time(storetime) or acquired
            order = _nearest_preceding(orders, acquired, timedelta(hours=24))
            title, impression = _parse_radiology(text or "")
            events.append(
                make_event(
                    case_id=case_id,
                    event_id=f"{case_id}::RAD::{index:02d}",
                    event_type="IMAGING_RESULT",
                    display=title,
                    modality="IMAGING",
                    dataset="MIMIC-IV-Note 2.2",
                    source_table="radiology+poe",
                    source_row_id=str(note_id),
                    anchor=anchor,
                    order_time=order["time"] if order else None,
                    acquired_time=acquired,
                    available_time=available,
                    documented_time=available,
                    confidence="MEDIUM" if order else "HIGH",
                    availability_semantics="REPORT_SIGNED_PROXY",
                    result={"impression": impression},
                    arena_eligible=bool(order and available and available >= order["time"]),
                    leakage_risk="MEDIUM" if not order else "LOW",
                    exclusion_reason=None if order else "NO_RELIABLE_ORDER_LINK",
                    replay_mode="OBSERVED_RESULT_WITH_SHIFTED_TAT" if order else "OBSERVED_FIXED_TIME",
                )
            )
        return events

    def _ecg_events(self, case_id: str, subject_id: int, anchor: datetime, orders):
        rows = self.connection.execute(
            f"""SELECT study_id,ecg_time,report_0,report_1,report_2,report_3,report_4,
                       rr_interval,p_axis,qrs_axis,t_axis
                FROM temporal_mimic_ecg
                WHERE subject_id=? AND try_cast(ecg_time AS TIMESTAMP)
                      BETWEEN ? AND ? ORDER BY try_cast(ecg_time AS TIMESTAMP) LIMIT 3""",
            [str(subject_id), anchor, anchor + timedelta(hours=24)],
        ).fetchall()
        events = []
        for index, row in enumerate(rows, 1):
            study_id, ecg_time, *values = row
            acquired = parse_time(ecg_time)
            order = _nearest_preceding(orders, acquired, timedelta(hours=8))
            report = [item for item in values[:5] if item]
            consistent = bool(order and acquired and acquired >= order["time"])
            events.append(
                make_event(
                    case_id=case_id,
                    event_id=f"{case_id}::ECG::{index:02d}",
                    event_type="ECG_RESULT",
                    display="12-lead ECG",
                    modality="ECG",
                    dataset="MIMIC-IV-ECG",
                    source_table="machine_measurements+poe",
                    source_row_id=str(study_id),
                    anchor=anchor,
                    order_time=order["time"] if consistent else None,
                    acquired_time=acquired,
                    available_time=acquired,
                    confidence="MEDIUM" if consistent else "LOW",
                    availability_semantics="ECG_MACHINE_TIME_WITH_KNOWN_CLOCK_UNCERTAINTY",
                    result={
                        "automated_report": report,
                        "rr_interval": values[5],
                        "p_axis": values[6],
                        "qrs_axis": values[7],
                        "t_axis": values[8],
                    },
                    arena_eligible=consistent,
                    leakage_risk="MEDIUM",
                    exclusion_reason=None if consistent else "ECG_CLOCK_OR_ORDER_LINK_UNCERTAIN",
                    replay_mode="OBSERVED_RESULT_WITH_SHIFTED_TAT" if consistent else "OBSERVED_FIXED_TIME",
                )
            )
        return events

    def _patient(self, subject_id: int, anchor: datetime):
        row = self.connection.execute(
            f"""SELECT gender,anchor_age,anchor_year
                FROM read_csv_auto('{self.mimic / 'hosp/patients.csv.gz'}',header=true)
                WHERE subject_id=?""",
            [subject_id],
        ).fetchone()
        if not row:
            return {"gender": "UNKNOWN", "age": None}
        return {"gender": row[0], "age": int(row[1]) + anchor.year - int(row[2])}

    def _triage(self, stay_id: int):
        cursor = self.connection.execute(
            f"""SELECT temperature,heartrate,resprate,o2sat,sbp,dbp,pain,acuity,chiefcomplaint
                FROM read_csv_auto('{self.ed / 'ed/triage.csv.gz'}',header=true)
                WHERE stay_id=? LIMIT 1""",
            [stay_id],
        )
        row = cursor.fetchone()
        if not row:
            return {}
        return {key: value for key, value in zip([item[0] for item in cursor.description], row)}

    def _med_reconciliation(self, stay_id: int):
        rows = self.connection.execute(
            f"""SELECT charttime,name,etcdescription
                FROM read_csv_auto('{self.ed / 'ed/medrecon.csv.gz'}',header=true)
                WHERE stay_id=? ORDER BY charttime LIMIT 12""",
            [stay_id],
        ).fetchall()
        return [{"documented_time": iso(row[0]), "name": row[1], "class": row[2]} for row in rows]

    def _discharge_note(self, hadm_id: int):
        row = self.connection.execute(
            """SELECT text FROM temporal_mimic_discharge
                WHERE hadm_id=? ORDER BY storetime DESC LIMIT 1""",
            [hadm_id],
        ).fetchone()
        return row[0] if row else None

    def _diagnoses(self, hadm_id: int):
        rows = self.connection.execute(
            f"""SELECT i.long_title
                FROM read_csv_auto('{self.mimic / 'hosp/diagnoses_icd.csv.gz'}',header=true) d
                JOIN read_csv_auto('{self.mimic / 'hosp/d_icd_diagnoses.csv.gz'}',header=true) i
                  USING(icd_code,icd_version)
                WHERE d.hadm_id=? ORDER BY d.seq_num LIMIT 12""",
            [hadm_id],
        ).fetchall()
        return [row[0] for row in rows]


def _nearest_preceding(orders, event_time: Optional[datetime], window: timedelta):
    if not event_time:
        return None
    eligible = [
        item for item in orders
        if item["time"] and item["time"] <= event_time and event_time - item["time"] <= window
    ]
    return max(eligible, key=lambda item: item["time"]) if eligible else None


def _lab_panel_name(components: Iterable[dict]) -> str:
    labels = " | ".join(str(dict(item).get("label") or "") for item in components).upper()
    if "TROPONIN" in labels:
        return "Troponin panel"
    if all(item in labels for item in ("HEMOGLOBIN", "PLATELET")):
        return "Complete blood count"
    if all(item in labels for item in ("SODIUM", "POTASSIUM")):
        return "Metabolic panel"
    if "PH" in labels and ("PCO2" in labels or "PO2" in labels):
        return "Blood gas"
    first = next(iter(components), {})
    return f"Laboratory specimen · {dict(first).get('label') or 'panel'}"


def _extract_presentation_sections(text: str) -> Dict[str, str]:
    aliases = {
        "chief_complaint": r"chief complaint",
        "history_of_present_illness": r"history of present illness",
        "past_medical_history": r"past medical history",
    }
    result: Dict[str, str] = {}
    heading = re.compile(r"(?mi)^\s*([A-Za-z][A-Za-z /-]{2,45}):\s*$")
    matches = list(heading.finditer(text))
    for key, pattern in aliases.items():
        for index, match in enumerate(matches):
            if re.fullmatch(pattern, match.group(1).strip(), flags=re.I):
                end = matches[index + 1].start() if index + 1 < len(matches) else len(text)
                value = " ".join(text[match.end():end].strip().split())[:1800]
                if value:
                    result[key] = value
                break
    return result


def _parse_radiology(text: str):
    title = "Radiology report"
    match = re.search(r"(?im)^\s*(?:examination|exam):\s*(.+)$", text)
    if match:
        title = match.group(1).strip()[:160]
    impression = ""
    match = re.search(r"(?is)\bimpression:\s*(.+?)(?:\n\s*\n|$)", text)
    if match:
        impression = " ".join(match.group(1).split())[:2400]
    if not impression:
        impression = " ".join(text.split())[-1200:]
    return title, impression
