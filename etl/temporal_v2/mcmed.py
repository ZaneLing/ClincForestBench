from __future__ import annotations

from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List

from backend.app.domain.temporal import TemporalCase

from .common import (
    ROOT,
    TemporalAdapter,
    build_mvp_simulations,
    build_temporal_graph,
    clean,
    iso,
    make_event,
    parse_time,
    relative_minutes,
    slug,
)


class MCMEDTemporalAdapter(TemporalAdapter):
    dataset_slug = "mcmed"
    dataset_name = "MC-MED v1.0.1"

    def __init__(self, root: Path = ROOT):
        super().__init__(root)
        self.source = root / "dataset/restricted/mc-med-v1.0.1"

    def list_cases(self, limit: int = 20) -> List[Dict[str, Any]]:
        query = f"""
            WITH v AS (
              SELECT * FROM read_csv_auto('{self.source / 'visits.csv'}', header=true, all_varchar=true)
              WHERE lower(CC) LIKE '%chest pain%'
                AND Dx_name IS NOT NULL AND Dx_name <> ''
            ), l AS (
              SELECT CSN, count(distinct Display_name) panels, count(*) components
              FROM read_csv_auto('{self.source / 'labs.csv'}', header=true, all_varchar=true)
              GROUP BY CSN
            ), r AS (
              SELECT CSN, count(*) rads
              FROM read_csv_auto('{self.source / 'rads.csv'}', header=true, all_varchar=true)
              GROUP BY CSN
            ), o AS (
              SELECT CSN, count(*) orders
              FROM read_csv_auto('{self.source / 'orders.csv'}', header=true, all_varchar=true)
              GROUP BY CSN
            )
            SELECT v.MRN, v.CSN, v.Age, v.Gender, v.Race, v.Ethnicity,
                   v.Means_of_arrival, v.Triage_Temp, v.Triage_HR,
                   v.Triage_RR, v.Triage_SpO2, v.Triage_SBP, v.Triage_DBP,
                   v.Triage_acuity, v.CC, v.Dx_ICD9, v.Dx_ICD10, v.Dx_name,
                   v.Arrival_time, v.Roomed_time, v.Dispo_time, v.Admit_time,
                   v.Departure_time, l.panels, l.components, r.rads, o.orders
            FROM v JOIN l USING(CSN) JOIN r USING(CSN) JOIN o USING(CSN)
            WHERE l.panels >= 2 AND r.rads >= 1 AND o.orders >= 4
            ORDER BY l.panels + r.rads + o.orders DESC, v.CSN
            LIMIT {int(limit)}
        """
        columns = [item[0] for item in self.connection.execute(query).description]
        return [dict(zip(columns, row)) for row in self.connection.fetchall()]

    def load_case(self, candidate: Dict[str, Any]) -> TemporalCase:
        csn = str(candidate["CSN"])
        mrn = str(candidate["MRN"])
        case_id = f"CFB_MC_{csn}"
        anchor = parse_time(candidate["Arrival_time"])
        if not anchor:
            raise ValueError("MC-MED case has no arrival anchor")

        major = self._first_major_intervention(csn, anchor)
        intervention_min = major["relative_min"] if major else None
        events = self._lab_events(case_id, csn, anchor, intervention_min)
        events.extend(self._radiology_events(case_id, csn, anchor, intervention_min))
        if major:
            events.append(
                make_event(
                    case_id=case_id,
                    event_id=f"{case_id}::INTERVENTION::{slug(major['name'])}",
                    event_type="INTERVENTION_START",
                    display=major["name"],
                    modality="INTERVENTION",
                    dataset=self.dataset_name,
                    source_table="orders",
                    source_row_id=major["row_id"],
                    anchor=anchor,
                    order_time=major["order_time"],
                    start_time=major["start_time"],
                    available_time=major["start_time"],
                    confidence="EXACT",
                    availability_semantics="FIRST_ADMIN_TIME",
                    result={"status": "administered"},
                    action_id=f"OBSERVE_INTERVENTION_{slug(major['name']).upper()[:40]}",
                    arena_eligible=False,
                    state_changing=True,
                    exclusion_reason="STATE_CHANGING_INTERVENTION",
                    replay_mode="OBSERVED_FIXED_TIME",
                )
            )
        events.sort(key=lambda item: (item.order_min(), item.available_min(), item.event_id))
        diagnostic = [item for item in events if item.clinical_concept.modality in {"LAB", "IMAGING"}]
        eligible = [item for item in diagnostic if item.arena.arena_eligible]
        if len(eligible) < 4:
            raise ValueError("insufficient pre-intervention evidence")

        pmh = self._past_history(mrn, anchor)
        medications = self._home_medications(mrn, anchor)
        initial_state = {
            "age": _number(candidate.get("Age")),
            "sex": candidate.get("Gender"),
            "race": candidate.get("Race"),
            "ethnicity": candidate.get("Ethnicity"),
            "chief_complaint": candidate.get("CC"),
            "means_of_arrival": candidate.get("Means_of_arrival"),
            "triage_acuity": candidate.get("Triage_acuity"),
            "triage_vitals": {
                "temperature_c": _number(candidate.get("Triage_Temp")),
                "heart_rate": _number(candidate.get("Triage_HR")),
                "respiratory_rate": _number(candidate.get("Triage_RR")),
                "spo2": _number(candidate.get("Triage_SpO2")),
                "sbp": _number(candidate.get("Triage_SBP")),
                "dbp": _number(candidate.get("Triage_DBP")),
            },
        }
        reference = {
            "primary_diagnosis": candidate.get("Dx_name"),
            "diagnosis_codes": {
                "icd9": candidate.get("Dx_ICD9"),
                "icd10": candidate.get("Dx_ICD10"),
            },
            "reference_strength": "SOURCE_CODED_REVIEW_REQUIRED",
            "is_absolute_ground_truth": False,
        }
        warnings = []
        if intervention_min is not None:
            warnings.append("POST_MAJOR_INTERVENTION_EVENTS_EXCLUDED_FROM_FREE_REORDERING")
        quality = {
            "evidence_count": len(diagnostic),
            "modality_count": len({item.clinical_concept.modality for item in diagnostic}),
            "temporal_completeness": round(
                sum(item.time.relative_available_min is not None for item in diagnostic)
                / max(1, len(diagnostic)),
                3,
            ),
            "timeline_consistency": not any(
                item.available_min() < item.order_min() for item in events
            ),
            "branchability": min(1.0, len(eligible) / 8),
            "reference_quality": "REVIEW_REQUIRED",
            "pre_intervention_evidence_count": len(eligible),
            "checks": {
                "anchor_present": True,
                "initial_state_has_no_diagnosis": "diagnosis" not in initial_state,
                "real_results_only": all(
                    item.provenance.is_observed_real_result for item in events
                ),
                "order_and_availability_separated": all(
                    item.time.relative_available_min is not None for item in diagnostic
                ),
                "mvp_branchable": len(eligible) >= 4,
            },
        }
        trajectory = [
            {
                "sequence": index,
                "event_id": item.event_id,
                "action_id": item.action_id,
                "order_time_min": item.order_min(),
                "available_time_min": item.available_min(),
                "latency_min": round(max(0, item.available_min() - item.order_min()), 2),
            }
            for index, item in enumerate(events, 1)
        ]
        graph = build_temporal_graph(case_id, events, reference)
        return TemporalCase(
            case_id=case_id,
            task_type="ED_TEMPORAL_DIAGNOSIS",
            source={
                "dataset_family": "MC-MED",
                "dataset_version": "1.0.1",
                "source_case_id": csn,
                "source_tables": ["visits", "labs", "rads", "orders", "pmh", "meds"],
                "access_class": "RESTRICTED_LOCAL_ONLY",
            },
            anchor={
                "anchor_type": "ED_ARRIVAL",
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
                    "items": pmh,
                    "filter": "Noted_date <= Arrival_time",
                },
                {
                    "action_id": "REVIEW_HOME_MEDICATIONS",
                    "items": medications,
                    "filter": "Start_date <= Arrival_time <= End_date when available",
                },
            ],
            hidden_evidence_pool=[item.event_id for item in eligible],
            realized_trajectory=trajectory,
            reference=reference,
            case_quality=quality,
            temporal_quality={
                "anchor_confidence": "EXACT",
                "core_event_minimum_confidence": "HIGH",
                "warnings": warnings,
                "intervention_boundary_min": intervention_min,
            },
            arena_config={
                "time_mode": "WAIT_FOR_NEXT_RESULT",
                "time_bucket_min": 5,
                "unobserved_action_result": "UNOBSERVED_IN_RECORDED_EPISODE",
                "max_questions": 30,
                "free_reorder_scope": "PRE_MAJOR_INTERVENTION_ONLY",
            },
            temporal_graph=graph,
            mvp_simulations=build_mvp_simulations(events),
        )

    def _lab_events(
        self,
        case_id: str,
        csn: str,
        anchor: datetime,
        intervention_min: float | None,
    ):
        query = f"""
            SELECT Order_time, Result_time, Display_name, Abnormal,
                   list(struct_pack(name := Component_name, value := Component_value,
                                    text := Component_result, unit := Component_units,
                                    flag := Component_abnormal)
                        ORDER BY Component_name) components
            FROM read_csv_auto('{self.source / 'labs.csv'}', header=true, all_varchar=true)
            WHERE CSN = ? AND Order_time IS NOT NULL AND Result_time IS NOT NULL
              AND try_cast(Result_time AS TIMESTAMP) BETWEEN ? AND ?
            GROUP BY Order_time, Result_time, Display_name, Abnormal
            ORDER BY Order_time, Result_time
            LIMIT 18
        """
        rows = self.connection.execute(
            query, [csn, anchor, anchor + timedelta(hours=24)]
        ).fetchall()
        events = []
        for index, (order, result_time, display, abnormal, components) in enumerate(rows, 1):
            available_min = relative_minutes(result_time, anchor)
            after_intervention = (
                intervention_min is not None
                and available_min is not None
                and available_min > intervention_min
            )
            events.append(
                make_event(
                    case_id=case_id,
                    event_id=f"{case_id}::LAB::{index:02d}",
                    event_type="LAB_RESULT",
                    display=display or "Laboratory panel",
                    modality="LAB",
                    dataset=self.dataset_name,
                    source_table="labs",
                    source_row_id=f"{csn}:{order}:{display}",
                    anchor=anchor,
                    order_time=order,
                    available_time=result_time,
                    confidence="EXACT",
                    availability_semantics="MC_MED_RESULT_TIME",
                    result={
                        "panel_abnormal": abnormal,
                        "components": [
                            {key: clean(value) for key, value in dict(item).items()}
                            for item in components
                        ],
                    },
                    arena_eligible=not after_intervention,
                    intervention_before_result=after_intervention,
                    exclusion_reason=(
                        "RESULT_AFTER_MAJOR_INTERVENTION" if after_intervention else None
                    ),
                )
            )
        return events

    def _radiology_events(
        self,
        case_id: str,
        csn: str,
        anchor: datetime,
        intervention_min: float | None,
    ):
        rows = self.connection.execute(
            f"""SELECT Order_time,Result_time,Study,Impression
                FROM read_csv_auto('{self.source / 'rads.csv'}', header=true, all_varchar=true)
                WHERE CSN=? AND Order_time IS NOT NULL AND Result_time IS NOT NULL
                  AND try_cast(Result_time AS TIMESTAMP) BETWEEN ? AND ?
                ORDER BY Order_time,Result_time LIMIT 8""",
            [csn, anchor, anchor + timedelta(hours=24)],
        ).fetchall()
        events = []
        for index, (order, result_time, study, impression) in enumerate(rows, 1):
            available_min = relative_minutes(result_time, anchor)
            after_intervention = (
                intervention_min is not None
                and available_min is not None
                and available_min > intervention_min
            )
            events.append(
                make_event(
                    case_id=case_id,
                    event_id=f"{case_id}::RAD::{index:02d}",
                    event_type="IMAGING_RESULT",
                    display=study or "Radiology study",
                    modality="IMAGING",
                    dataset=self.dataset_name,
                    source_table="rads",
                    source_row_id=f"{csn}:{order}:{study}",
                    anchor=anchor,
                    order_time=order,
                    acquired_time=None,
                    available_time=result_time,
                    confidence="HIGH",
                    availability_semantics="RADIOLOGY_IMPRESSION_POSTED",
                    result={"impression": impression},
                    arena_eligible=not after_intervention,
                    intervention_before_result=after_intervention,
                    exclusion_reason=(
                        "RESULT_AFTER_MAJOR_INTERVENTION" if after_intervention else None
                    ),
                )
            )
        return events

    def _first_major_intervention(self, csn: str, anchor: datetime):
        row = self.connection.execute(
            f"""SELECT Order_time,First_admin_time,Procedure_name,Procedure_ID
                FROM read_csv_auto('{self.source / 'orders.csv'}', header=true, all_varchar=true)
                WHERE CSN=? AND First_admin_time IS NOT NULL
                  AND regexp_matches(upper(Procedure_name),
                    'NOREPINEPHRINE|EPINEPHRINE|VASOPRESSIN|CEFTRIAXONE|CEFEPIME|VANCOMYCIN|AZITHROMYCIN|PIPERACILLIN|INTUB|ROCURONIUM|HEPARIN IV|LR IV BOLUS - (1000|2000|30 ML)')
                ORDER BY First_admin_time LIMIT 1""",
            [csn],
        ).fetchone()
        if not row:
            return None
        return {
            "order_time": row[0],
            "start_time": row[1],
            "name": row[2],
            "row_id": row[3] or f"{csn}:{row[0]}",
            "relative_min": relative_minutes(row[1], anchor),
        }

    def _past_history(self, mrn: str, anchor: datetime):
        rows = self.connection.execute(
            f"""SELECT Noted_date,CodeType,Code,Desc10,DescCCS
                FROM read_csv_auto('{self.source / 'pmh.csv'}', header=true, all_varchar=true)
                WHERE MRN=? AND try_cast(Noted_date AS TIMESTAMP) <= ?
                ORDER BY Noted_date DESC LIMIT 12""",
            [mrn, anchor],
        ).fetchall()
        return [
            {"noted_time": iso(row[0]), "code_system": row[1], "code": row[2], "name": row[3], "group": row[4]}
            for row in rows
        ]

    def _home_medications(self, mrn: str, anchor: datetime):
        rows = self.connection.execute(
            f"""SELECT Name,Generic_name,Med_class,Start_date,End_date
                FROM read_csv_auto('{self.source / 'meds.csv'}', header=true, all_varchar=true)
                WHERE MRN=?
                  AND (Start_date IS NULL OR try_cast(Start_date AS TIMESTAMP) <= ?)
                  AND (End_date IS NULL OR End_date='' OR try_cast(End_date AS TIMESTAMP) >= ?)
                ORDER BY Start_date DESC LIMIT 12""",
            [mrn, anchor, anchor],
        ).fetchall()
        return [
            {"name": row[0], "generic_name": row[1], "class": row[2], "start_time": iso(row[3]), "end_time": iso(row[4])}
            for row in rows
        ]


def _number(value: Any):
    if value in (None, ""):
        return None
    try:
        number = float(value)
        return int(number) if number.is_integer() else number
    except (TypeError, ValueError):
        return value
