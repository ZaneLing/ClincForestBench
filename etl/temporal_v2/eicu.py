from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List

from backend.app.domain.temporal import TemporalCase

from .common import (
    ROOT,
    TemporalAdapter,
    build_mvp_simulations,
    build_temporal_graph,
    make_event,
    slug,
)


_WORKFLOW_VALUES = {
    "performed",
    "performed - structured",
    "scored",
    "completed",
    "obtained",
    "other",
}


def _clinical_leaf(path: Any, value: Any, *, exam: bool = False) -> str:
    parts = [part.strip() for part in str(path or "").split("/") if part.strip()]
    leaf = parts[-1] if parts else str(value or "Clinical finding").strip()
    replacements = {
        "HR Current": "当前心率",
        "HR Lowest": "最低心率",
        "HR Highest": "最高心率",
        "RR Current": "当前呼吸频率",
        "Resp Current": "当前呼吸频率",
        "Resp Lowest": "最低呼吸频率",
        "Resp Highest": "最高呼吸频率",
        "O2 Sat Current": "当前血氧饱和度",
        "O2 Sat% Current": "当前血氧饱和度",
        "O2 Sat% Lowest": "最低血氧饱和度",
        "O2 Sat% Highest": "最高血氧饱和度",
        "BP (systolic) Current": "当前收缩压",
        "BP (systolic) Lowest": "最低收缩压",
        "BP (systolic) Highest": "最高收缩压",
        "BP (diastolic) Current": "当前舒张压",
        "BP (diastolic) Lowest": "最低舒张压",
        "BP (diastolic) Highest": "最高舒张压",
        "Admission": "入院体重",
        "Current": "当前体重",
        "Delta": "体重变化",
        "FiO2%": "吸入氧浓度",
        "PEEP": "呼气末正压",
        "Vent Rate Current": "当前呼吸机频率",
        "Intake Total": "累计入量",
        "Output Total": "累计出量",
        "Dialysis Net": "透析净出量",
        "Total Net": "液体净平衡",
        "chemotherapy within past mo.": "近一个月接受过化疗",
        "melanoma": "黑色素瘤病史",
        "liver": "肝转移病史",
        "lung": "肺转移病史",
        "colon": "结肠癌病史",
        "clinical diagnosis": "肝硬化病史（临床诊断）",
        ">= 20 mg prednisone per day or equivalent": "近 6 个月使用泼尼松≥20 mg/日或等效剂量",
        "COPD  - no limitations": "慢性阻塞性肺病（活动不受限）",
        "home oxygen": "长期家庭氧疗",
        "hypertension requiring treatment": "需药物治疗的高血压",
        "insulin dependent diabetes": "胰岛素依赖型糖尿病",
        "MI - date unknown": "心肌梗死病史（时间不详）",
        "MI - remote": "陈旧性心肌梗死",
        "procedural coronary intervention - remote": "既往冠状动脉介入治疗",
        "procedural coronary intervention - within 5 years": "近 5 年冠状动脉介入治疗",
        "renal failure- not currently dialyzed": "肾衰竭（目前未透析）",
        "renal insufficiency - creatinine 1-2": "肾功能不全（肌酐 1–2 mg/dL）",
    }
    label = replacements.get(leaf, leaf)
    if exam and "GCS" in parts:
        score_type = next(
            (
                part
                for part in parts
                if part in {"Motor Score", "Eyes Score", "Verbal Score"}
            ),
            "总评分",
        )
        score_label = {
            "Motor Score": "运动反应",
            "Eyes Score": "睁眼反应",
            "Verbal Score": "言语反应",
        }.get(score_type, score_type)
        label = f"GCS {score_label}评分"
    return label


def _meaningful_clinical_row(path: Any, value: Any) -> bool:
    path_text = str(path or "").casefold()
    leaf = _clinical_leaf(path, value).casefold()
    value_text = str(value or "").strip().casefold()
    return bool(
        leaf
        and value_text
        and leaf not in _WORKFLOW_VALUES
        and value_text not in _WORKFLOW_VALUES
        and "obtain options" not in path_text
    )


def _lab_panel_label(names: List[Any]) -> str:
    normalized = {str(name or "").strip().casefold() for name in names}
    if any("urinary" in name or "urine" in name for name in normalized):
        return "尿液检查"
    if {"ph", "paco2", "pao2"} & normalized or any(
        name in normalized for name in ("base deficit", "hco3")
    ):
        return "血气分析"
    if any("wbc" in name or "platelet" in name or "hemoglobin" in name for name in normalized):
        return "血常规及分类"
    if any(name in normalized for name in ("inr", "pt", "ptt", "fibrinogen")):
        return "凝血功能"
    if any(name in normalized for name in ("creatinine", "sodium", "potassium", "alt (sgpt)", "ast (sgot)")):
        return "综合代谢及肝肾功能"
    if any("glucose" in name for name in normalized):
        return "血糖"
    short = [str(name).strip() for name in names if str(name or "").strip()][:3]
    return "、".join(short) or "实验室检验"


def _lab_action_base(label: str, names: List[Any]) -> str:
    code = {
        "尿液检查": "URINALYSIS",
        "血气分析": "BLOOD_GAS",
        "血常规及分类": "CBC_WITH_DIFFERENTIAL",
        "凝血功能": "COAGULATION",
        "综合代谢及肝肾功能": "METABOLIC_LIVER_RENAL_PANEL",
        "血糖": "GLUCOSE",
    }.get(label)
    if code:
        return f"ORDER_LAB_{code}"
    source_key = slug("_".join(str(name or "") for name in names[:3])).upper()[:44]
    return f"ORDER_LAB_{source_key}"


def _physical_modality(path: Any) -> str:
    text = str(path or "").casefold()
    if "vital sign and physiological data" in text or "weight and i&o" in text:
        return "VITALS"
    return "EXAM"


def _physical_priority(path: Any) -> int:
    text = str(path or "").casefold()
    if "/gcs/" in text:
        return 0
    if text.endswith(" current"):
        return 1
    if any(token in text for token in ("fio2", "peep", "vent rate")):
        return 2
    return 3


def _physical_action_token(path: Any, value: Any) -> str:
    parts = [part.strip() for part in str(path or "").split("/") if part.strip()]
    if "GCS" in parts:
        score_type = next(
            (
                part
                for part in parts
                if part in {"Motor Score", "Eyes Score", "Verbal Score"}
            ),
            "Total Score",
        )
        return f"GCS_{slug(score_type).upper()}"
    leaf = parts[-1] if parts else str(value or "Clinical finding")
    return slug(leaf).upper()


def _physical_unit(path: Any) -> str | None:
    text = str(path or "").casefold()
    if "/hr/" in text:
        return "次/分"
    if "bp (systolic)" in text or "bp (diastolic)" in text:
        return "mmHg"
    if "resp rate" in text or "vent rate" in text:
        return "次/分"
    if "o2 sat" in text or "fio2" in text:
        return "%"
    if "weight (kg)" in text:
        return "kg"
    if "i&&o (ml)" in text:
        return "mL"
    if "peep" in text:
        return "cmH₂O"
    return None


class EICUTemporalAdapter(TemporalAdapter):
    dataset_slug = "eicu"
    dataset_name = "eICU-CRD v2.0"

    def __init__(self, root: Path = ROOT):
        super().__init__(root)
        self.source = root / "dataset/restricted/eicu-crd-v2.0"
        self._prepared = False

    def list_cases(self, limit: int = 20) -> List[Dict[str, Any]]:
        self._prepare_candidates(max(limit * 5, 100))
        cursor = self.connection.execute(
            f"""SELECT c.*,count(distinct l.labid) FILTER (WHERE l.labresultoffset BETWEEN 0 AND 360) early_labs,
                       count(distinct l.labname) FILTER (WHERE l.labresultoffset BETWEEN 0 AND 360) lab_types,
                       count(distinct d.diagnosisid) FILTER (WHERE d.diagnosisoffset BETWEEN 0 AND 360) early_diagnoses
                FROM temporal_eicu_candidates c
                LEFT JOIN temporal_eicu_lab l USING(patientunitstayid)
                LEFT JOIN temporal_eicu_diagnosis d USING(patientunitstayid)
                GROUP BY ALL
                HAVING early_labs >= 12 AND lab_types >= 8 AND early_diagnoses >= 1
                ORDER BY lab_types DESC,early_labs DESC,c.patientunitstayid
                LIMIT {int(limit)}"""
        )
        columns = [item[0] for item in cursor.description]
        return [dict(zip(columns, row)) for row in cursor.fetchall()]

    def _prepare_candidates(self, limit: int) -> None:
        if self._prepared:
            return
        self.connection.execute(
            f"""CREATE TEMP TABLE temporal_eicu_candidates AS
                SELECT patientunitstayid,patienthealthsystemstayid,gender,age,ethnicity,
                       hospitalid,wardid,apacheadmissiondx,hospitaladmitsource,unittype,
                       unitadmitsource,unitstaytype,unitdischargeoffset,unitdischargestatus
                FROM read_csv_auto('{self.source / 'patient.csv.gz'}',header=true)
                WHERE apacheadmissiondx IS NOT NULL
                  AND regexp_matches(lower(apacheadmissiondx),'respir|pneum|sepsis|infection')
                ORDER BY CASE WHEN unitadmitsource='Emergency Department' THEN 0 ELSE 1 END,
                         patientunitstayid
                LIMIT {int(limit)}"""
        )
        for name, filename in (
            ("lab", "lab.csv.gz"),
            ("diagnosis", "diagnosis.csv.gz"),
            ("treatment", "treatment.csv.gz"),
            ("vital", "vitalPeriodic.csv.gz"),
            ("history", "pastHistory.csv.gz"),
            ("physical", "physicalExam.csv.gz"),
        ):
            self.connection.execute(
                f"""CREATE TEMP TABLE temporal_eicu_{name} AS
                    SELECT source.*
                    FROM read_csv_auto('{self.source / filename}',header=true,strict_mode=false) source
                    JOIN temporal_eicu_candidates USING(patientunitstayid)"""
            )
        self._prepared = True

    def load_case(self, candidate: Dict[str, Any]) -> TemporalCase:
        stay_id = int(candidate["patientunitstayid"])
        case_id = f"CFB_EICU_{stay_id}"
        boundary = self._first_major_intervention(stay_id)
        boundary_min = boundary["offset"] if boundary else None
        events = self._lab_events(case_id, stay_id, boundary_min)
        events.extend(self._history_events(case_id, stay_id))
        events.extend(self._physical_events(case_id, stay_id))
        if boundary:
            events.append(
                make_event(
                    case_id=case_id,
                    event_id=f"{case_id}::INTERVENTION::{slug(boundary['name'])}",
                    event_type="INTERVENTION_START",
                    display=boundary["name"],
                    modality="INTERVENTION",
                    dataset=self.dataset_name,
                    source_table="treatment",
                    source_row_id=str(boundary["id"]),
                    relative_start_min=float(boundary["offset"]),
                    relative_available_min=float(boundary["offset"]),
                    confidence="EXACT",
                    availability_semantics="EICU_TREATMENT_OFFSET",
                    result={"active_upon_discharge": boundary["active"]},
                    action_id=f"OBSERVE_INTERVENTION_{slug(boundary['name']).upper()[:40]}",
                    arena_eligible=False,
                    state_changing=True,
                    exclusion_reason="STATE_CHANGING_INTERVENTION",
                    replay_mode="OBSERVED_FIXED_TIME",
                )
            )
        events.extend(self._diagnosis_events(case_id, stay_id))
        events.sort(key=lambda item: (item.order_min(), item.available_min(), item.event_id))
        eligible = [item for item in events if item.arena.arena_eligible]
        if len(eligible) < 4:
            raise ValueError("insufficient early eICU evidence")

        diagnoses = self._diagnosis_labels(stay_id)
        reference = {
            "admission_diagnosis": candidate.get("apacheadmissiondx"),
            "recorded_diagnoses": diagnoses,
            "adjudicated_primary_diagnosis": candidate.get("apacheadmissiondx"),
            "reference_strength": "RECORDED_ICU_DIAGNOSIS_REVIEW_REQUIRED",
            "is_absolute_ground_truth": False,
        }
        initial_state = {
            "age": candidate.get("age"),
            "sex": candidate.get("gender"),
            "ethnicity": candidate.get("ethnicity"),
            "icu_unit": candidate.get("unittype"),
            "admission_source": candidate.get("unitadmitsource"),
            "unit_stay_type": candidate.get("unitstaytype"),
            "first_15_min_vitals": self._vital_segment(stay_id, 0, 15),
        }
        warnings = [
            "MISSINGNESS_IS_INTERFACE_DEPENDENT_NOT_TEST_NOT_PERFORMED",
            "LAB_ORDER_TIME_UNAVAILABLE_RESULTS_REPLAY_AT_FIXED_RECORDED_OFFSET",
        ]
        if boundary_min is not None:
            warnings.append("POST_MAJOR_INTERVENTION_EVENTS_EXCLUDED_FROM_FREE_REORDERING")
        diagnostic = [
            item
            for item in events
            if item.clinical_concept.modality
            in {"LAB", "HISTORY", "EXAM", "VITALS"}
        ]
        trajectory = [
            {
                "sequence": index,
                "event_id": item.event_id,
                "action_id": item.action_id,
                "order_time_min": item.time.relative_order_min,
                "available_time_min": item.time.relative_available_min,
                "source_offset_semantics": item.time.availability_semantics,
            }
            for index, item in enumerate(events, 1)
        ]
        graph = build_temporal_graph(case_id, events, reference)
        return TemporalCase(
            case_id=case_id,
            task_type="ICU_EARLY_CLINICAL_ASSESSMENT",
            source={
                "dataset_family": "eICU-CRD",
                "dataset_version": "2.0",
                "source_case_id": str(stay_id),
                "source_tables": ["patient", "lab", "vitalPeriodic", "pastHistory", "physicalExam", "diagnosis", "treatment"],
                "access_class": "PHYSIONET_CREDENTIALLED_LOCAL_ONLY",
                "missingness_semantics": "INTERFACE_DEPENDENT",
            },
            anchor={
                "anchor_type": "ICU_ADMISSION",
                "absolute_time": None,
                "relative_zero": 0,
                "time_system": "MINUTES_FROM_ICU_ADMISSION",
                "timezone_policy": "NOT_APPLICABLE",
            },
            initial_state=initial_state,
            timeline_events=events,
            queryable_context=[
                {
                    "action_id": "REVIEW_PAST_MEDICAL_HISTORY",
                    "items": self._history_items(stay_id),
                    "missingness_semantics": "INTERFACE_DEPENDENT",
                },
                {
                    "action_id": "REVIEW_PHYSICAL_EXAM",
                    "items": self._physical_items(stay_id),
                    "missingness_semantics": "INTERFACE_DEPENDENT",
                },
            ],
            hidden_evidence_pool=[item.event_id for item in eligible],
            realized_trajectory=trajectory,
            reference=reference,
            case_quality={
                "evidence_count": len(diagnostic),
                "modality_count": len({item.clinical_concept.modality for item in diagnostic}),
                "temporal_completeness": round(
                    sum(item.time.relative_available_min is not None for item in diagnostic) / max(1, len(diagnostic)),
                    3,
                ),
                "timeline_consistency": all(item.available_min() >= item.order_min() for item in events),
                "branchability": min(1.0, len(eligible) / 8),
                "reference_quality": "HUMAN_REVIEW_REQUIRED",
                "pre_intervention_evidence_count": len(eligible),
                "checks": {
                    "anchor_present": True,
                    "relative_offsets_preserved": all(item.available_min() >= 0 for item in diagnostic),
                    "real_results_only": all(item.provenance.is_observed_real_result for item in events),
                    "missingness_semantics_explicit": True,
                    "mvp_branchable": len(eligible) >= 4,
                },
            },
            temporal_quality={
                "anchor_confidence": "EXACT_RELATIVE_OFFSET",
                "core_event_minimum_confidence": "HIGH",
                "warnings": warnings,
                "intervention_boundary_min": boundary_min,
            },
            arena_config={
                "time_mode": "WAIT_FOR_NEXT_RESULT",
                "time_bucket_min": 5,
                "unobserved_action_result": "UNOBSERVED_IN_RECORDED_EPISODE",
                "max_questions": 30,
                "evidence_window_min": min(360, boundary_min) if boundary_min is not None else 360,
                "free_reorder_scope": "FIXED_TIME_REVIEW_ONLY_WHEN_ORDER_OFFSET_IS_UNKNOWN",
            },
            temporal_graph=graph,
            mvp_simulations=build_mvp_simulations(events),
        )

    def _lab_events(self, case_id: str, stay_id: int, boundary_min: float | None):
        rows = self.connection.execute(
            """SELECT labresultoffset,
                      list(struct_pack(name := labname,value := labresult,text := labresulttext,
                                       unit := labmeasurenameinterface,revised_offset := labresultrevisedoffset)
                           ORDER BY labname) components
               FROM temporal_eicu_lab
               WHERE patientunitstayid=? AND labresultoffset BETWEEN 0 AND 360
               GROUP BY labresultoffset ORDER BY labresultoffset LIMIT 14""",
            [stay_id],
        ).fetchall()
        events = []
        seen_actions: Dict[str, int] = {}
        for index, (offset, components) in enumerate(rows, 1):
            after = boundary_min is not None and float(offset) > boundary_min
            names = [dict(item).get("name") for item in components]
            label = _lab_panel_label(names)
            base_action = _lab_action_base(label, names)
            repeat = seen_actions.get(base_action, 0) + 1
            seen_actions[base_action] = repeat
            action_id = base_action if repeat == 1 else f"{base_action}_REPEAT_{repeat}"
            display = label if repeat == 1 else f"{label}（第 {repeat} 次复查）"
            events.append(
                make_event(
                    case_id=case_id,
                    event_id=f"{case_id}::LAB::{index:02d}",
                    event_type="LAB_RESULT",
                    display=display or "实验室检验",
                    modality="LAB",
                    dataset=self.dataset_name,
                    source_table="lab",
                    source_row_id=f"{stay_id}:{offset}",
                    relative_available_min=float(offset),
                    relative_documented_min=float(offset),
                    confidence="HIGH",
                    availability_semantics="EICU_RECORDED_RESULT_OFFSET",
                    result={"components": [dict(item) for item in components]},
                    action_id=action_id,
                    arena_eligible=not after,
                    intervention_before_result=after,
                    exclusion_reason="RESULT_AFTER_MAJOR_INTERVENTION" if after else None,
                    replay_mode="OBSERVED_FIXED_TIME",
                )
            )
        return events

    def _history_events(self, case_id: str, stay_id: int):
        rows = self.connection.execute(
            """SELECT pasthistoryid,pasthistoryenteredoffset,pasthistorypath,pasthistoryvaluetext
               FROM temporal_eicu_history WHERE patientunitstayid=?
                 AND pasthistoryenteredoffset BETWEEN 0 AND 360
               ORDER BY pasthistoryenteredoffset LIMIT 32""",
            [stay_id],
        ).fetchall()
        events = []
        seen_actions = set()
        for row in rows:
            if not _meaningful_clinical_row(row[2], row[3]):
                continue
            label = _clinical_leaf(row[2], row[3])
            source_leaf = str(row[2] or row[3]).split("/")[-1]
            action_id = f"ASK_HISTORY_{slug(source_leaf).upper()[:48]}"
            if action_id in seen_actions:
                continue
            seen_actions.add(action_id)
            events.append(make_event(
                case_id=case_id,
                event_id=f"{case_id}::HISTORY::{len(events) + 1:02d}",
                event_type="HISTORY_REVIEW",
                display=label,
                modality="HISTORY",
                dataset=self.dataset_name,
                source_table="pastHistory",
                source_row_id=str(row[0]),
                relative_available_min=float(row[1]),
                confidence="HIGH",
                availability_semantics="EICU_HISTORY_ENTERED_OFFSET",
                result={
                    "finding": label,
                    "value": "是",
                    "source_value": row[3],
                    "source_path": row[2],
                },
                action_id=action_id,
                replay_mode="OBSERVED_FIXED_TIME",
            ))
            if len(events) >= 8:
                break
        return events

    def _physical_events(self, case_id: str, stay_id: int):
        rows = self.connection.execute(
            """SELECT physicalexamid,physicalexamoffset,physicalexampath,physicalexamtext
               FROM temporal_eicu_physical WHERE patientunitstayid=?
                 AND physicalexamoffset BETWEEN 0 AND 360
               ORDER BY physicalexamoffset LIMIT 64""",
            [stay_id],
        ).fetchall()
        rows = [
            row
            for row in rows
            if _meaningful_clinical_row(row[2], row[3])
            and not any(
                token in str(row[2] or "").casefold()
                for token in (" lowest", " highest")
            )
        ]
        rows.sort(
            key=lambda row: (_physical_priority(row[2]), float(row[1]), row[0])
        )
        events = []
        seen_actions = set()
        for row in rows:
            label = _clinical_leaf(row[2], row[3], exam=True)
            modality = _physical_modality(row[2])
            prefix = "REVIEW_BEDSIDE" if modality == "VITALS" else "PERFORM_EXAM"
            action_id = f"{prefix}_{_physical_action_token(row[2], row[3])[:48]}"
            if action_id in seen_actions:
                continue
            seen_actions.add(action_id)
            events.append(make_event(
                case_id=case_id,
                event_id=f"{case_id}::EXAM::{len(events) + 1:02d}",
                event_type=(
                    "BEDSIDE_OBSERVATION"
                    if modality == "VITALS"
                    else "PHYSICAL_EXAM"
                ),
                display=label,
                modality=modality,
                dataset=self.dataset_name,
                source_table="physicalExam",
                source_row_id=str(row[0]),
                relative_available_min=float(row[1]),
                confidence="HIGH",
                availability_semantics="EICU_PHYSICAL_EXAM_OFFSET",
                result={
                    "finding": label,
                    "value": row[3],
                    "unit": _physical_unit(row[2]),
                    "source_path": row[2],
                },
                action_id=action_id,
                replay_mode="OBSERVED_FIXED_TIME",
            ))
            if len(events) >= 8:
                break
        return events

    def _diagnosis_events(self, case_id: str, stay_id: int):
        rows = self.connection.execute(
            """SELECT diagnosisid,diagnosisoffset,diagnosisstring,icd9code,diagnosispriority
               FROM temporal_eicu_diagnosis WHERE patientunitstayid=?
                 AND diagnosisoffset BETWEEN 0 AND 360
               ORDER BY diagnosisoffset LIMIT 5""",
            [stay_id],
        ).fetchall()
        return [
            make_event(
                case_id=case_id,
                event_id=f"{case_id}::DIAGNOSIS::{index:02d}",
                event_type="DIAGNOSIS_DOCUMENTED",
                display=(row[2] or "Recorded diagnosis").split("|")[-1],
                modality="DIAGNOSIS",
                dataset=self.dataset_name,
                source_table="diagnosis",
                source_row_id=str(row[0]),
                relative_documented_min=float(row[1]),
                relative_available_min=float(row[1]),
                confidence="HIGH",
                availability_semantics="EICU_DIAGNOSIS_OFFSET",
                result={"diagnosis_path": row[2], "icd9_code": row[3], "priority": row[4]},
                action_id="REVIEW_RECORDED_DIAGNOSIS",
                arena_eligible=False,
                leakage_risk="HIGH",
                exclusion_reason="REFERENCE_DIAGNOSIS_LEAKAGE",
                replay_mode="OBSERVED_FIXED_TIME",
            )
            for index, row in enumerate(rows, 1)
        ]

    def _first_major_intervention(self, stay_id: int):
        row = self.connection.execute(
            """SELECT treatmentid,treatmentoffset,treatmentstring,activeupondischarge
               FROM temporal_eicu_treatment WHERE patientunitstayid=? AND treatmentoffset>=0
                 AND regexp_matches(lower(treatmentstring),
                   'vasopressor|norepinephrine|epinephrine|antibiotic|intubat|mechanical ventilation|surgery|fluid resuscitation|anticoag')
               ORDER BY treatmentoffset LIMIT 1""",
            [stay_id],
        ).fetchone()
        return None if not row else {"id": row[0], "offset": float(row[1]), "name": row[2], "active": row[3]}

    def _vital_segment(self, stay_id: int, start: int, end: int):
        row = self.connection.execute(
            """SELECT median(temperature),min(temperature),max(temperature),arg_max(temperature,observationoffset),
                      median(sao2),min(sao2),max(sao2),arg_max(sao2,observationoffset),
                      median(heartrate),min(heartrate),max(heartrate),arg_max(heartrate,observationoffset),
                      median(respiration),min(respiration),max(respiration),arg_max(respiration,observationoffset)
               FROM temporal_eicu_vital WHERE patientunitstayid=? AND observationoffset BETWEEN ? AND ?""",
            [stay_id, start, end],
        ).fetchone()
        names = ("temperature", "spo2", "heart_rate", "respiratory_rate")
        result = {}
        for index, name in enumerate(names):
            values = {
                "median": row[index * 4],
                "min": row[index * 4 + 1],
                "max": row[index * 4 + 2],
                "last": row[index * 4 + 3],
            }
            if any(value is not None for value in values.values()):
                result[name] = values
        return result

    def _diagnosis_labels(self, stay_id: int):
        return [
            row[0].split("|")[-1]
            for row in self.connection.execute(
                """SELECT diagnosisstring FROM temporal_eicu_diagnosis
                   WHERE patientunitstayid=? ORDER BY diagnosispriority,diagnosisoffset LIMIT 12""",
                [stay_id],
            ).fetchall()
            if row[0]
        ]

    def _history_items(self, stay_id: int):
        return [
            {
                "available_time_min": row[0],
                "finding": _clinical_leaf(row[1], row[2]),
                "value": row[2],
                "source_path": row[1],
            }
            for row in self.connection.execute(
                """SELECT pasthistoryenteredoffset,pasthistorypath,pasthistoryvaluetext
                   FROM temporal_eicu_history WHERE patientunitstayid=? ORDER BY pasthistoryenteredoffset LIMIT 12""",
                [stay_id],
            ).fetchall()
            if _meaningful_clinical_row(row[1], row[2])
        ]

    def _physical_items(self, stay_id: int):
        return [
            {
                "available_time_min": row[0],
                "finding": _clinical_leaf(row[1], row[2], exam=True),
                "value": row[2],
                "source_path": row[1],
            }
            for row in self.connection.execute(
                """SELECT physicalexamoffset,physicalexampath,physicalexamtext
                   FROM temporal_eicu_physical WHERE patientunitstayid=? ORDER BY physicalexamoffset LIMIT 12""",
                [stay_id],
            ).fetchall()
            if _meaningful_clinical_row(row[1], row[2])
        ]
