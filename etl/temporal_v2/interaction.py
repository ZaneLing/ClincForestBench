from __future__ import annotations

import csv
import hashlib
import json
import re
import xml.etree.ElementTree as ET
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Iterable, List, Sequence
from zipfile import ZipFile

import pyarrow.parquet as pq

from backend.app.domain.temporal import TemporalCase

from .common import (
    ROOT,
    TEMPORAL_ROOT,
    TemporalAdapter,
    build_mvp_simulations,
    build_temporal_graph,
    make_event,
    slug,
)


INTERACTION_ROOT = ROOT / "dataset/interaction"


def parse_speaker_turns(text: str) -> List[Dict[str, str]]:
    """Parse the explicit Chinese speaker labels used by MediScope."""
    cleaned = text.replace("<attachment>.jpg<attachment>", "[已上传检查报告]")
    pattern = re.compile(
        r"(?:^|\n\s*\n)(患者|医生)\s*[:：]\s*(.*?)(?=(?:\n\s*\n)(?:患者|医生)\s*[:：]|\Z)",
        re.S,
    )
    return [
        {"role": "patient" if role == "患者" else "doctor", "content": content.strip()}
        for role, content in pattern.findall(cleaned)
        if content.strip()
    ]


def extract_questions(text: str, limit: int = 2) -> str:
    """Keep only source-authored interrogative clauses for an Arena action."""
    clauses = re.findall(r"[^。.!！?？\n]{2,220}[?？]", text)
    questions = [re.sub(r"^.*?[，,:：]\s*", "", item).strip() for item in clauses]
    questions = [item for item in questions if item]
    if not questions:
        return ""
    return " ".join(questions[-limit:])


def consultation_pairs(
    messages: Sequence[Dict[str, Any]],
    doctor_roles: Iterable[str] = ("assistant", "doctor"),
    patient_roles: Iterable[str] = ("user", "patient"),
) -> tuple[str, List[Dict[str, Any]]]:
    """Return the first substantial patient statement and observed Q/A pairs."""
    doctor = set(doctor_roles)
    patient = set(patient_roles)
    initial_index = next(
        (
            index
            for index, item in enumerate(messages)
            if item.get("role") in patient
            and len(str(item.get("content") or "").strip()) >= 20
        ),
        next(
            (index for index, item in enumerate(messages) if item.get("role") in patient),
            0,
        ),
    )
    initial = str(messages[initial_index].get("content") or "").strip()
    pairs: List[Dict[str, Any]] = []
    for index, item in enumerate(messages[:-1]):
        if item.get("role") not in doctor:
            continue
        question = extract_questions(str(item.get("content") or ""))
        if not question:
            continue
        answer_index = next(
            (
                offset
                for offset in range(index + 1, len(messages))
                if messages[offset].get("role") in patient
            ),
            None,
        )
        if answer_index is None or answer_index == initial_index:
            continue
        answer = str(messages[answer_index].get("content") or "").strip()
        if answer:
            pairs.append(
                {
                    "doctor_turn_index": index,
                    "patient_turn_index": answer_index,
                    "question": question,
                    "answer": answer,
                }
            )
    return initial, pairs


def _make_interaction_case(
    *,
    adapter: TemporalAdapter,
    case_id: str,
    source_id: str,
    task_type: str,
    source_tables: List[str],
    raw_source: Dict[str, Any],
    initial_state: Dict[str, Any],
    event_specs: Sequence[Dict[str, Any]],
    reference_diagnosis: str,
    reference_strength: str,
    transformation_steps: List[Dict[str, Any]],
    limitations: List[str],
    queryable_context: List[Dict[str, Any]] | None = None,
    sequential_actions: bool = False,
    dataset_version: str = "PUBLIC_MVP_SNAPSHOT",
) -> TemporalCase:
    events = []
    for index, spec in enumerate(event_specs, 1):
        order_min = float(spec.get("order_min", index * 2))
        available_min = float(spec.get("available_min", order_min + 1))
        event_id = f"{case_id}::E{index:03d}"
        events.append(
            make_event(
                case_id=case_id,
                event_id=event_id,
                event_type=str(spec.get("event_type") or "CONSULTATION_TURN"),
                display=str(spec["display"]),
                modality=str(spec.get("modality") or "HISTORY"),
                dataset=adapter.dataset_name,
                source_table=str(spec.get("source_table") or source_tables[0]),
                source_row_id=str(spec.get("source_row_id") or index),
                relative_order_min=order_min,
                relative_available_min=available_min,
                confidence=str(spec.get("confidence") or "HIGH"),
                availability_semantics=str(
                    spec.get("availability_semantics")
                    or "RECORDED_TURN_OR_EVENT_ORDER"
                ),
                result=dict(spec.get("result") or {}),
                action_id=str(spec.get("action_id") or f"ASK_{slug(case_id).upper()}_{index:03d}"),
                arena_eligible=bool(spec.get("arena_eligible", True)),
                state_changing=bool(spec.get("state_changing", False)),
                leakage_risk=str(spec.get("leakage_risk") or "LOW"),
                replay_mode=str(
                    spec.get("replay_mode") or "OBSERVED_RESULT_WITH_SHIFTED_TAT"
                ),
            )
        )
    if not events:
        raise ValueError("interaction case has no source-backed revealable events")
    reference = {
        "reference_diagnosis": reference_diagnosis,
        "reference_strength": reference_strength,
        "is_absolute_ground_truth": reference_strength.startswith("ADJUDICATED"),
    }
    graph = build_temporal_graph(case_id, events, reference)
    eligible = [event for event in events if event.arena.arena_eligible]
    return TemporalCase(
        case_id=case_id,
        task_type=task_type,
        source={
            "dataset_family": adapter.dataset_name,
            "dataset_version": dataset_version,
            "source_case_id": source_id,
            "source_tables": source_tables,
            "access_class": getattr(adapter, "access_class", "PUBLIC"),
            "time_semantics": "SOURCE_SEQUENCE_OR_RECORDED_DATE",
        },
        raw_source=raw_source,
        transformation={
            "schema_version": "clincforestbench.interaction-conversion.v1",
            "steps": transformation_steps,
            "limitations": limitations,
            "safety_invariants": [
                "SOURCE_CONTENT_PRESERVED_IN_RAW_AUDIT",
                "NO_UNRECORDED_PATIENT_ANSWER_IS_GENERATED",
                "REFERENCE_HIDDEN_UNTIL_FINALIZATION",
                "PROXY_LABELS_ARE_NOT_PRESENTED_AS_ADJUDICATED_TRUTH",
            ],
        },
        anchor={
            "anchor_type": "CONSULTATION_OR_PERSONA_START",
            "absolute_time": None,
            "relative_zero": 0,
            "time_system": "SOURCE_SEQUENCE",
            "timezone_policy": "NOT_APPLICABLE_UNLESS_EVENT_DATE_IS_PRESENT",
        },
        initial_state=initial_state,
        timeline_events=events,
        queryable_context=queryable_context or [],
        hidden_evidence_pool=[event.event_id for event in eligible],
        realized_trajectory=[
            {
                "sequence": index,
                "event_id": event.event_id,
                "action_id": event.action_id,
                "available_time_min": event.available_min(),
                "result_origin": "PUBLISHED_SOURCE_RECORD",
            }
            for index, event in enumerate(events, 1)
        ],
        reference=reference,
        case_quality={
            "evidence_count": len(eligible),
            "modality_count": len(
                {event.clinical_concept.modality for event in eligible}
            ),
            "reference_quality": reference_strength,
            "checks": {
                "anchor_present": True,
                "source_content_preserved": True,
                "source_backed_results_only": True,
                "reference_strength_explicit": True,
                "mvp_branchable": len(eligible) >= 1,
            },
        },
        temporal_quality={
            "anchor_confidence": "MEDIUM",
            "core_event_minimum_confidence": min(
                (event.time.temporal_confidence.value for event in eligible),
                default="UNKNOWN",
            ),
            "warnings": limitations,
        },
        arena_config={
            "time_mode": "SYNCHRONOUS_SOURCE_REPLAY",
            "time_bucket_min": 1,
            "unobserved_action_result": "UNOBSERVED_IN_RECORDED_EPISODE",
            "max_questions": min(30, max(1, len(eligible))),
            "action_catalog_scope": "CASE",
            "sequential_actions": sequential_actions,
            "interaction_mvp": True,
        },
        temporal_graph=graph,
        mvp_simulations=build_mvp_simulations(events),
    )


class MediScopeTemporalAdapter(TemporalAdapter):
    dataset_slug = "mediscope"
    dataset_name = "MediScope"
    access_class = "PUBLIC_MIT_CURATED_SUBSET"

    def __init__(self, root: Path = ROOT):
        super().__init__(root)
        self.source = INTERACTION_ROOT / "mediscope/MedDiagnose.parquet"
        self._table = None
        self._media: Dict[str, bytes] = {}

    def list_cases(self, limit: int = 20) -> List[Dict[str, Any]]:
        rows = pq.read_table(self.source, columns=["diagnose"]).to_pylist()
        candidates = []
        for index, row in enumerate(rows):
            text = str(row.get("diagnose") or "")
            reference = _mediscope_reference(text)
            turns = parse_speaker_turns(text)
            _, pairs = consultation_pairs(
                turns, doctor_roles=("doctor",), patient_roles=("patient",)
            )
            if reference and len(pairs) >= 2:
                candidates.append(
                    {
                        "source_row": index,
                        "reference": reference,
                        "turn_count": len(turns),
                        "question_answer_pairs": len(pairs),
                    }
                )
            if len(candidates) >= limit:
                break
        return candidates

    def load_case(self, candidate: Dict[str, Any]) -> TemporalCase:
        if self._table is None:
            self._table = pq.read_table(self.source)
        source_row = int(candidate["source_row"])
        row = self._table.slice(source_row, 1).to_pylist()[0]
        dialogue = str(row["diagnose"])
        image = bytes((row.get("image") or {}).get("bytes") or b"")
        turns = parse_speaker_turns(dialogue)
        initial, pairs = consultation_pairs(
            turns, doctor_roles=("doctor",), patient_roles=("patient",)
        )
        case_id = f"CFB_MEDISCOPE_{source_row:04d}"
        asset_name = "source_report.jpg"
        self._media[case_id] = image
        specs: List[Dict[str, Any]] = [
            {
                "display": "查看患者上传的检查报告原图",
                "modality": "IMAGING",
                "event_type": "SOURCE_IMAGE_REVIEW",
                "action_id": f"REVIEW_{case_id}_SOURCE_IMAGE",
                "source_table": "MedDiagnose.parquet:image",
                "source_row_id": source_row,
                "order_min": 0,
                "available_min": 1,
                "result": {
                    "media_asset": asset_name,
                    "media_type": "image/jpeg",
                    "caption": "MediScope 发布行中与该对话配对的原始检查报告图像",
                    "narrative_text": "患者已上传原始检查报告，请直接查看本节点中的图像。",
                },
            }
        ]
        for pair in pairs[:10]:
            specs.append(
                {
                    "display": pair["question"],
                    "modality": "HISTORY",
                    "event_type": "CONSULTATION_QUESTION_ANSWER",
                    "source_table": "MedDiagnose.parquet:diagnose",
                    "source_row_id": f"{source_row}:{pair['doctor_turn_index']}",
                    "result": {
                        "patient_answer": pair["answer"],
                        "source_patient_turn": pair["patient_turn_index"],
                    },
                }
            )
        return _make_interaction_case(
            adapter=self,
            case_id=case_id,
            source_id=str(source_row),
            task_type="MULTIMODAL_CONSULTATION_REPLAY",
            source_tables=["MedDiagnose.parquet"],
            raw_source={
                "source_row": source_row,
                "dialogue": dialogue,
                "parsed_turns": turns,
                "image": {
                    "asset": asset_name,
                    "byte_length": len(image),
                    "sha256": hashlib.sha256(image).hexdigest(),
                },
            },
            initial_state={
                "presentation": initial,
                "attachment_available": True,
                "language": "zh",
            },
            event_specs=specs,
            reference_diagnosis=str(candidate["reference"]),
            reference_strength="SOURCE_DIALOGUE_DIAGNOSTIC_CONCLUSION_PROXY",
            transformation_steps=[
                {"step": 1, "name": "读取图像对话行", "output": "raw_source"},
                {"step": 2, "name": "按患者/医生标签切分轮次", "output": "parsed_turns"},
                {"step": 3, "name": "首个患者陈述作为 S0", "output": "initial_state"},
                {"step": 4, "name": "医生问句与下一患者回答配对", "output": "timeline_events"},
                {"step": 5, "name": "JPEG 写入可视化结果节点", "output": "media/source_report.jpg"},
                {"step": 6, "name": "对话中的诊断结论隔离到 reference", "output": "temporal_graph"},
            ],
            limitations=[
                "PUBLIC_RELEASE_IS_A_CURATED_SUBSET_NOT_THE_FULL_MEDISCOPE_CORPUS",
                "TURN_ORDER_IS_NOT_A_CLINICAL_TIMESTAMP",
                "REFERENCE_IS_EXTRACTED_FROM_THE_SOURCE_DIALOGUE_NOT_INDEPENDENTLY_ADJUDICATED",
            ],
            dataset_version="PULSEMIND_PUBLIC_MEDDIAGNOSE_SNAPSHOT",
        )

    def write_case(self, case: TemporalCase) -> Dict[str, Any]:
        entry = super().write_case(case)
        media = TEMPORAL_ROOT / "case_bundles" / self.dataset_slug / case.case_id / "media"
        media.mkdir(parents=True, exist_ok=True)
        payload = self._media.get(case.case_id, b"")
        if payload:
            (media / "source_report.jpg").write_bytes(payload)
            entry["media_count"] = 1
        return entry


class MedPITemporalAdapter(TemporalAdapter):
    dataset_slug = "medpi"
    dataset_name = "MedPI"
    access_class = "PUBLIC_RESEARCH_CONSERVATIVE_NONCOMMERCIAL"

    def __init__(self, root: Path = ROOT):
        super().__init__(root)
        self.source = INTERACTION_ROOT / "medpi"
        self.patients = _csv_map(self.source / "patients.csv", "id")
        self.conversations = _csv_map(self.source / "conversations.csv", "id")
        self.dimensions = list(
            csv.DictReader(
                (self.source / "dimensions.csv").open(encoding="utf-8", newline="")
            )
        )

    def list_cases(self, limit: int = 20) -> List[Dict[str, Any]]:
        candidates = []
        seen_patients = set()
        with (self.source / "conversations_messages.jsonl").open(encoding="utf-8") as handle:
            for line in handle:
                row = json.loads(line)
                metadata = self.conversations.get(row.get("conversation_id"), {})
                patient = self.patients.get(metadata.get("patient_id"), {})
                if (
                    not patient
                    or metadata.get("completed") != "True"
                    or patient.get("encounter_objective") != "diagnosis"
                    or patient.get("id") in seen_patients
                ):
                    continue
                initial, pairs = consultation_pairs(row.get("messages") or [])
                if len(initial) < 20 or len(pairs) < 3:
                    continue
                candidates.append(
                    {
                        "conversation_id": row["conversation_id"],
                        "patient_id": patient["id"],
                        "reference": patient["encounter_reason"],
                        "messages": row["messages"],
                    }
                )
                seen_patients.add(patient["id"])
                if len(candidates) >= limit:
                    break
        return candidates

    def load_case(self, candidate: Dict[str, Any]) -> TemporalCase:
        conversation_id = str(candidate["conversation_id"])
        patient = self.patients[str(candidate["patient_id"])]
        metadata = self.conversations[conversation_id]
        messages = list(candidate["messages"])
        initial, pairs = consultation_pairs(messages)
        case_id = f"CFB_MEDPI_{slug(conversation_id).upper()}"
        specs = [
            {
                "display": pair["question"],
                "modality": "HISTORY",
                "event_type": "CONSULTATION_QUESTION_ANSWER",
                "source_table": "conversations_messages.jsonl",
                "source_row_id": f"{conversation_id}:{pair['doctor_turn_index']}",
                "result": {
                    "patient_answer": pair["answer"],
                    "source_patient_turn": pair["patient_turn_index"],
                },
            }
            for pair in pairs[:12]
        ]
        applicable_dimensions = [
            row
            for row in self.dimensions
            if not row.get("encounter_objective")
            or patient["encounter_objective"] in row.get("encounter_objective", "")
        ][:20]
        return _make_interaction_case(
            adapter=self,
            case_id=case_id,
            source_id=conversation_id,
            task_type="MULTI_TURN_CONSULTATION_REPLAY",
            source_tables=[
                "patients.csv",
                "conversations.csv",
                "conversations_messages.jsonl",
                "dimensions.csv",
            ],
            raw_source={
                "patient": patient,
                "conversation": metadata,
                "messages": messages,
            },
            initial_state={
                "age": patient.get("age"),
                "sex": patient.get("gender"),
                "presentation": initial,
                "medical_speciality": patient.get("medical_speciality"),
                "encounter_objective": patient.get("encounter_objective"),
            },
            event_specs=specs,
            reference_diagnosis=patient["encounter_reason"],
            reference_strength="SYNTHETIC_ENCOUNTER_REASON_NOT_ADJUDICATED_DIAGNOSIS",
            transformation_steps=[
                {"step": 1, "name": "连接 patient 与 conversation 外键", "output": "raw_source"},
                {"step": 2, "name": "寻找首个实质患者陈述", "output": "initial_state"},
                {"step": 3, "name": "抽取原医生问句", "output": "action catalog"},
                {"step": 4, "name": "绑定下一条真实患者回答", "output": "timeline_events"},
                {"step": 5, "name": "连接适用评测维度", "output": "queryable_context"},
                {"step": 6, "name": "隔离 encounter reason", "output": "reference"},
            ],
            limitations=[
                "SYNTHETIC_CONVERSATIONS",
                "ENCOUNTER_REASON_IS_A_TASK_LABEL_NOT_AN_INDEPENDENTLY_ADJUDICATED_DIAGNOSIS",
                "ONE_SOURCE_DOCTOR_TURN_CAN_CONTAIN_MULTIPLE_QUESTIONS",
                "UPSTREAM_LICENSE_METADATA_CONFLICT_REQUIRES_CONSERVATIVE_USE",
            ],
            queryable_context=[{"evaluation_dimensions": applicable_dimensions}],
            dataset_version="MEDPI_2025_08_14",
        )


class PatientSimTemporalAdapter(TemporalAdapter):
    dataset_slug = "patientsim"
    dataset_name = "PatientSim"
    access_class = "PUBLIC_DEMO_ONLY_FULL_DATA_PHYSIONET_DUA"

    def __init__(self, root: Path = ROOT):
        super().__init__(root)
        self.source = INTERACTION_ROOT / "patientsim/source/demo/demo_data.json"

    def list_cases(self, limit: int = 20) -> List[Dict[str, Any]]:
        return json.loads(self.source.read_text(encoding="utf-8"))[:limit]

    def load_case(self, candidate: Dict[str, Any]) -> TemporalCase:
        source_id = str(candidate["hadm_id"])
        case_id = f"CFB_PATIENTSIM_{slug(source_id).upper()}"
        fields = [
            ("请描述这次不适还伴有哪些症状？", "present_illness_positive", "HISTORY"),
            ("有哪些相关症状明确没有出现？", "present_illness_negative", "HISTORY"),
            ("既往有哪些疾病？", "medical_history", "HISTORY"),
            ("目前在使用哪些药物？", "medication", "HISTORY"),
            ("有无药物或其他过敏？", "allergies", "HISTORY"),
            ("是否吸烟、饮酒或使用其他物质？", "tobacco", "HISTORY"),
            ("家族中有哪些重要疾病？", "family_medical_history", "HISTORY"),
            ("平时与谁同住，谁能提供支持？", "living_situation", "HISTORY"),
        ]
        specs = [
            {
                "display": question,
                "modality": modality,
                "event_type": "PERSONA_PROFILE_ANSWER",
                "source_table": "demo/demo_data.json",
                "source_row_id": f"{source_id}:{field}",
                "result": {"patient_answer": candidate.get(field), "profile_field": field},
            }
            for question, field, modality in fields
            if candidate.get(field)
        ]
        persona_policy = {
            "personality": "plain",
            "language_proficiency": "C",
            "medical_history_recall": "high",
            "cognitive_confusion": "normal",
            "selection_note": "Static MVP policy using official PatientSim option names; not an upstream profile assignment.",
        }
        return _make_interaction_case(
            adapter=self,
            case_id=case_id,
            source_id=source_id,
            task_type="PERSONA_CONSULTATION_MVP",
            source_tables=["demo/demo_data.json", "src/prompts/simulation/*.json"],
            raw_source={"demo_profile": candidate, "mvp_persona_policy": persona_policy},
            initial_state={
                "age": candidate.get("age"),
                "sex": candidate.get("gender"),
                "chief_complaint": candidate.get("chiefcomplaint"),
                "arrival_transport": candidate.get("arrival_transport"),
                "persona": persona_policy,
            },
            event_specs=specs,
            reference_diagnosis=str(candidate.get("diagnosis") or "Unknown"),
            reference_strength="PUBLIC_DEMO_PROFILE_DIAGNOSIS",
            transformation_steps=[
                {"step": 1, "name": "读取官方公开 demo profile", "output": "raw_source"},
                {"step": 2, "name": "主诉与人口学信息作为 S0", "output": "initial_state"},
                {"step": 3, "name": "profile 字段映射为可问询动作", "output": "timeline_events"},
                {"step": 4, "name": "固定静态 MVP persona 轴", "output": "queryable_context"},
                {"step": 5, "name": "隔离 demo diagnosis", "output": "reference"},
            ],
            limitations=[
                "FULL_PATIENTSIM_DATA_REQUIRES_PHYSIONET_CREDENTIALS_AND_DUA",
                "STATIC_MVP_REPLAYS_PROFILE_FIELDS_AND_DOES_NOT_RUN_A_GENERATIVE_PATIENT_AGENT",
                "PERSONA_AXIS_ASSIGNMENT_IS_AN_MVP_POLICY_NOT_AN_UPSTREAM_PAIRING",
            ],
            queryable_context=[{"persona_policy": persona_policy}],
            dataset_version="PATIENTSIM_PUBLIC_DEMO_2026_03",
        )


class MeddiesTemporalAdapter(TemporalAdapter):
    dataset_slug = "meddies_persona_vie"
    dataset_name = "Meddies Persona VIE"
    access_class = "PUBLIC_CC_BY_NC_4_0"

    def __init__(self, root: Path = ROOT):
        super().__init__(root)
        self.source = INTERACTION_ROOT / "meddies-persona-vie/mvp_rows.json"

    def list_cases(self, limit: int = 20) -> List[Dict[str, Any]]:
        rows = json.loads(self.source.read_text(encoding="utf-8")).get("rows", [])
        return [item["row"] for item in rows[:limit]]

    def load_case(self, candidate: Dict[str, Any]) -> TemporalCase:
        demographics = candidate.get("demographics") or {}
        medical = candidate.get("medical_history") or {}
        llm = candidate.get("llm_fields") or {}
        source_id = str(demographics.get("patient_id"))
        case_id = f"CFB_MEDDIES_{slug(source_id).upper()}"
        specs: List[Dict[str, Any]] = []
        for index, symptom in enumerate(llm.get("presenting_symptoms") or [], 1):
            name = str(symptom.get("symptom_name") or f"triệu chứng {index}")
            specs.append(
                {
                    "display": f"Hãy mô tả chi tiết về {name}.",
                    "modality": "HISTORY",
                    "event_type": "PERSONA_SYMPTOM_DETAIL",
                    "source_table": "mvp_rows.json:llm_fields.presenting_symptoms",
                    "source_row_id": f"{source_id}:symptom:{index}",
                    "result": {
                        "patient_answer": _meddies_symptom_answer(symptom),
                        "structured_symptom": symptom,
                    },
                }
            )
        sections = [
            ("Tiền sử bệnh của bạn gồm những gì?", "medical_history", medical),
            ("Hiện tại bạn đang dùng thuốc gì?", "medications", candidate.get("medications")),
            ("Lối sống hằng ngày của bạn như thế nào?", "lifestyle", candidate.get("lifestyle")),
            ("Bạn gặp trở ngại gì khi đi khám hoặc điều trị?", "social_barriers", llm.get("social_barriers")),
            ("Bạn thường tìm kiếm và lựa chọn chăm sóc y tế như thế nào?", "healthcare_behavior", candidate.get("healthcare_behavior")),
        ]
        for question, field, value in sections:
            if value:
                specs.append(
                    {
                        "display": question,
                        "modality": "HISTORY",
                        "event_type": "PERSONA_CONTEXT_REVEAL",
                        "source_table": f"mvp_rows.json:{field}",
                        "source_row_id": f"{source_id}:{field}",
                        "result": {"patient_answer": value, "profile_field": field},
                    }
                )
        chronic = [str(value) for value in medical.get("chronic_conditions") or []]
        reference = " / ".join(chronic[:3]) or "No coded chronic condition"
        persona = {
            "communication_style": llm.get("communication_style"),
            "primary_language": demographics.get("primary_language"),
            "dialect": demographics.get("dialect"),
            "ethnicity": demographics.get("ethnicity"),
            "health_literacy_level": (candidate.get("healthcare_behavior") or {}).get("health_literacy_level"),
        }
        return _make_interaction_case(
            adapter=self,
            case_id=case_id,
            source_id=source_id,
            task_type="PERSONA_CONSULTATION_REPLAY",
            source_tables=["Dataset Viewer rows: default/train"],
            raw_source=candidate,
            initial_state={
                "age": demographics.get("age"),
                "sex": demographics.get("gender"),
                "ethnicity": demographics.get("ethnicity"),
                "chief_complaint": llm.get("chief_complaint"),
                "communication_profile": persona,
            },
            event_specs=specs[:12],
            reference_diagnosis=reference,
            reference_strength="PROFILE_CHRONIC_CONDITION_CODES_NOT_CURRENT_ADJUDICATION",
            transformation_steps=[
                {"step": 1, "name": "保留完整合成 persona", "output": "raw_source"},
                {"step": 2, "name": "主诉与沟通特征作为 S0", "output": "initial_state"},
                {"step": 3, "name": "逐项展开症状持续时间/严重度/进展", "output": "timeline_events"},
                {"step": 4, "name": "病史、用药、行为与障碍形成独立分支", "output": "timeline_events"},
                {"step": 5, "name": "慢病编码仅作为 profile reference", "output": "reference"},
            ],
            limitations=[
                "SYNTHETIC_VIETNAMESE_PERSONAS",
                "STATIC_FIELD_REPLAY_DOES_NOT_FULLY_EMULATE_COMMUNICATION_STYLE",
                "CHRONIC_CONDITION_CODES_ARE_NOT_AN_ADJUDICATED_CURRENT_DIAGNOSIS",
            ],
            queryable_context=[{"persona": persona}],
            dataset_version="MEDDIES_PERSONA_VIE_VIEWER_MVP",
        )


class MedMemoryBenchTemporalAdapter(TemporalAdapter):
    dataset_slug = "medmemorybench"
    dataset_name = "MedMemoryBench"
    access_class = "PUBLIC_RESEARCH_CONSERVATIVE_NONCOMMERCIAL_SHAREALIKE"

    def __init__(self, root: Path = ROOT):
        super().__init__(root)
        self.source = INTERACTION_ROOT / "medmemorybench"
        self.personas = {
            int(row["persona_id"]): row
            for row in pq.read_table(self.source / "personas.parquet").to_pylist()
        }
        self.events = pq.read_table(self.source / "events.parquet").to_pylist()
        self.traps = pq.read_table(self.source / "trap_events.parquet").to_pylist()
        self.queries = pq.read_table(self.source / "queries.parquet").to_pylist()
        self.reports = {
            int(row["persona_id"]): row
            for row in pq.read_table(self.source / "clinical_reports.parquet").to_pylist()
        }

    def list_cases(self, limit: int = 20) -> List[Dict[str, Any]]:
        return [
            {
                "persona_id": persona_id,
                "reference": self.personas[persona_id]["type_name"],
                "event_count": sum(
                    int(row["persona_id"]) == persona_id for row in self.events
                ),
            }
            for persona_id in sorted(self.personas)[:limit]
        ]

    def load_case(self, candidate: Dict[str, Any]) -> TemporalCase:
        persona_id = int(candidate["persona_id"])
        persona = self.personas[persona_id]
        events = sorted(
            [row for row in self.events if int(row["persona_id"]) == persona_id],
            key=lambda row: (str(row.get("event_date") or ""), int(row["event_id"])),
        )
        if len(events) < 2:
            raise ValueError("longitudinal persona has insufficient events")
        anchor_date = datetime.fromisoformat(str(events[0]["event_date"]))
        case_id = f"CFB_MEDMEMORY_{persona_id:02d}"
        specs = []
        for row in events[1:31]:
            event_date = datetime.fromisoformat(str(row["event_date"]))
            offset = (event_date - anchor_date).total_seconds() / 60
            specs.append(
                {
                    "display": (
                        f"调阅 {row['event_date']} 纵向事件："
                        f"{str(row.get('event') or '').strip()[:72]}"
                    ),
                    "modality": "RECORD",
                    "event_type": "LONGITUDINAL_HEALTH_EVENT",
                    "source_table": "events.parquet",
                    "source_row_id": f"{persona_id}:{row['event_id']}",
                    "order_min": offset,
                    "available_min": offset,
                    "confidence": "EXACT",
                    "availability_semantics": "RECORDED_EVENT_DATE",
                    "replay_mode": "OBSERVED_FIXED_TIME",
                    "result": {
                        "narrative_text": row.get("event"),
                        "event_date": row.get("event_date"),
                        "event_type": row.get("type"),
                        "triggered_by": _json_value(row.get("triggered_by")),
                    },
                }
            )
        traps = [row for row in self.traps if int(row["persona_id"]) == persona_id]
        queries = [row for row in self.queries if int(row["persona_id"]) == persona_id]
        report = self.reports.get(persona_id, {})
        return _make_interaction_case(
            adapter=self,
            case_id=case_id,
            source_id=str(persona_id),
            task_type="LONGITUDINAL_MEMORY_REPLAY",
            source_tables=[
                "personas.parquet",
                "events.parquet",
                "trap_events.parquet",
                "queries.parquet",
                "clinical_reports.parquet",
            ],
            raw_source={
                "persona": persona,
                "events": events,
                "trap_events": traps,
                "evaluation_queries": queries,
                "clinical_report": report,
            },
            initial_state={
                "sex": persona.get("gender"),
                "age_range": persona.get("age_range"),
                "occupation": persona.get("occupation_detail"),
                "presentation": events[0].get("event"),
                "event_date": events[0].get("event_date"),
                "health_goals": _json_value(persona.get("health_goals")),
            },
            event_specs=specs,
            reference_diagnosis=str(persona["type_name"]),
            reference_strength="SYNTHETIC_PERSONA_DISEASE_TYPE",
            transformation_steps=[
                {"step": 1, "name": "按 persona_id 连接五张核心表", "output": "raw_source"},
                {"step": 2, "name": "最早健康事件定义纵向 T0", "output": "initial_state"},
                {"step": 3, "name": "event_date 转为距 T0 的真实日历分钟", "output": "timeline_events.time"},
                {"step": 4, "name": "triggered_by 保留因果引用", "output": "timeline_events.result"},
                {"step": 5, "name": "trap 与 query 保留为记忆评测上下文", "output": "queryable_context"},
                {"step": 6, "name": "疾病类型隔离为回顾性 reference", "output": "temporal_graph"},
            ],
            limitations=[
                "SYNTHETIC_LONGITUDINAL_DIALOGUES_AND_EVENTS",
                "MVP_USES_STRUCTURED_EVENTS_NOT_THE_LARGE_DIALOGUE_PARQUET",
                "SOURCE_DISEASE_TYPE_IS_A_PERSONA_LABEL_NOT_REAL_WORLD_ADJUDICATION",
                "UPSTREAM_LICENSE_METADATA_CONFLICT_REQUIRES_CONSERVATIVE_USE",
            ],
            queryable_context=[
                {
                    "trap_events": traps,
                    "evaluation_queries": queries[:25],
                    "clinical_report": report,
                }
            ],
            sequential_actions=True,
            dataset_version="MEDMEMORYBENCH_V1_EN_MVP",
        )


class MedDialogRubricsTemporalAdapter(TemporalAdapter):
    dataset_slug = "meddialogrubrics"
    dataset_name = "MedDialogRubrics"
    access_class = "PUBLIC_FILE_LICENSE_UNDECLARED_NO_REDISTRIBUTION"

    def __init__(self, root: Path = ROOT):
        super().__init__(root)
        self.source = INTERACTION_ROOT / "meddialogrubrics/MedDialogRubrics_v1.xlsx"
        self.rows = _read_xlsx_rows(self.source)

    def list_cases(self, limit: int = 20) -> List[Dict[str, Any]]:
        candidates = []
        for source_row, row in enumerate(self.rows, 2):
            rubrics = _json_value(row.get("问诊要点"))
            if row.get("主诉") and row.get("病历") and row.get("诊断") and isinstance(rubrics, list):
                candidates.append(
                    {
                        "source_row": source_row,
                        "diagnosis": row["诊断"],
                        "department": row.get("科室"),
                        "rubric_count": len(rubrics),
                        "row": row,
                    }
                )
            if len(candidates) >= limit:
                break
        return candidates

    def load_case(self, candidate: Dict[str, Any]) -> TemporalCase:
        row = candidate["row"]
        source_row = int(candidate["source_row"])
        case_id = f"CFB_MDR_{source_row:04d}"
        rubrics = _json_value(row["问诊要点"])
        facts = _medical_record_facts(str(row["病历"]))
        specs = []
        rubric_context = []
        for index, rubric in enumerate(rubrics[:15], 1):
            criterion = re.sub(r"^\s*\d+[.、]\s*", "", str(rubric)).strip()
            response, score = _best_fact(criterion, facts)
            if score < 0.04:
                response = "该病例原文未记录这一要点的明确回答。"
            category = _rubric_category(criterion)
            rubric_context.append(
                {
                    "rubric_id": f"R{index:02d}",
                    "category": category,
                    "criterion": criterion,
                    "weight": 1,
                    "source_fact": response,
                    "lexical_match_score": round(score, 3),
                }
            )
            specs.append(
                {
                    "display": criterion,
                    "modality": "HISTORY",
                    "event_type": "EXPERT_REFERENCE_INQUIRY",
                    "source_table": "MedDialogRubrics_v1.xlsx:Sheet1",
                    "source_row_id": f"{source_row}:rubric:{index}",
                    "result": {
                        "patient_answer": response,
                        "expert_reference": criterion,
                        "rubric_category": category,
                        "rubric_weight": 1,
                        "source_fact_match_method": "CHARACTER_BIGRAM_OVERLAP",
                        "source_fact_match_score": round(score, 3),
                    },
                }
            )
        return _make_interaction_case(
            adapter=self,
            case_id=case_id,
            source_id=str(source_row),
            task_type="EXPERT_ACTION_REFERENCE_REPLAY",
            source_tables=["MedDialogRubrics_v1.xlsx:Sheet1"],
            raw_source={"excel_row": source_row, **row},
            initial_state={
                "chief_complaint": row.get("主诉"),
                "medical_speciality": row.get("科室"),
            },
            event_specs=specs,
            reference_diagnosis=str(row["诊断"]),
            reference_strength="EXPERT_REFINED_SYNTHETIC_CASE_LABEL",
            transformation_steps=[
                {"step": 1, "name": "读取真实工作簿行", "output": "raw_source"},
                {"step": 2, "name": "主诉作为 S0，完整病历保持隐藏", "output": "initial_state"},
                {"step": 3, "name": "解析问诊要点 JSON 数组", "output": "expert rubric catalog"},
                {"step": 4, "name": "病历切成原子事实", "output": "source facts"},
                {"step": 5, "name": "字符 bigram 绑定最相关原文事实", "output": "patient answers"},
                {"step": 6, "name": "专家要点成为参考动作分支", "output": "temporal_graph"},
            ],
            limitations=[
                "SYNTHETIC_CASES",
                "UPSTREAM_FILE_HAS_NO_DECLARED_DATA_LICENSE",
                "RUBRIC_CATEGORIES_AND_FACT_BINDING_ARE_DETERMINISTIC_MVP_DERIVATIONS",
                "FACT_BINDING_REQUIRES_CLINICIAN_REVIEW_BEFORE_FORMAL_SCORING",
            ],
            queryable_context=[{"expert_action_reference": rubric_context}],
            dataset_version="MEDDIALOGRUBRICS_V1",
        )


def _mediscope_reference(text: str) -> str:
    patterns = (
        r"考虑是([^，。；\n]{2,32}?)(?:的)?可能性(?:比较)?(?:大|高)",
        r"诊断为([^，。；\n]{2,32})",
        r"考虑([^，。；\n]{2,32}?)(?:的)?可能性(?:比较)?(?:大|高)",
    )
    for pattern in patterns:
        matches = re.findall(pattern, text)
        if matches:
            value = re.sub(r"^(?:有|存在)", "", matches[-1]).strip()
            return value
    return ""


def _csv_map(path: Path, key: str) -> Dict[str, Dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as handle:
        return {row[key]: row for row in csv.DictReader(handle)}


def _json_value(value: Any) -> Any:
    if not isinstance(value, str):
        return value
    try:
        return json.loads(value)
    except json.JSONDecodeError:
        return value


def _meddies_symptom_answer(symptom: Dict[str, Any]) -> str:
    parts = [str(symptom.get("symptom_name") or "").strip()]
    for label, key in (("kéo dài", "duration"), ("mức độ", "severity"), ("diễn tiến", "progression")):
        value = symptom.get(key)
        if value:
            parts.append(f"{label}: {value}")
    return "; ".join(part for part in parts if part)


def _read_xlsx_rows(path: Path) -> List[Dict[str, str]]:
    namespace = {"m": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
    with ZipFile(path) as archive:
        strings_root = ET.fromstring(archive.read("xl/sharedStrings.xml"))
        strings = [
            "".join(node.text or "" for node in item.iterfind(".//m:t", namespace))
            for item in strings_root.findall("m:si", namespace)
        ]
        sheet = ET.fromstring(archive.read("xl/worksheets/sheet1.xml"))
    matrix: List[Dict[str, str]] = []
    for row in sheet.findall(".//m:sheetData/m:row", namespace):
        values: Dict[str, str] = {}
        for cell in row.findall("m:c", namespace):
            column = re.match(r"[A-Z]+", cell.attrib.get("r", ""))
            value_node = cell.find("m:v", namespace)
            value = "" if value_node is None else value_node.text or ""
            if cell.attrib.get("t") == "s" and value:
                value = strings[int(value)]
            if column:
                values[column.group(0)] = value
        matrix.append(values)
    if not matrix:
        return []
    columns = {column: value for column, value in matrix[0].items() if value}
    return [
        {header: row.get(column, "") for column, header in columns.items()}
        for row in matrix[1:]
    ]


def _medical_record_facts(text: str) -> List[str]:
    facts = [
        value.strip()
        for value in re.split(
            r"\s+(?=(?:患者|双侧|叩击痛|弯腰|热敷|无|否认|直腿|近\d|每日|每周|自行|日常|办公室|工作座椅|20\d{2}-\d{2}-\d{2}|诊断为))",
            text,
        )
        if len(value.strip()) >= 4
        and not re.match(r"^(?:患者)?诊断为", value.strip())
    ]
    return facts or [text.strip()]


def _bigrams(text: str) -> set[str]:
    substitutions = {
        "发热": "体温",
        "热型": "体温",
        "职业性质": "工作",
        "化学原料": "原料",
        "重金属类物质": "汞",
        "防护措施": "防护",
        "有无": "是否",
    }
    for source, target in substitutions.items():
        text = text.replace(source, target)
    normalized = re.sub(r"[、，。（）()：:\s\d]", "", text)
    for phrase in (
        "患者",
        "具体",
        "了解",
        "明确",
        "询问",
        "确认",
        "是否",
        "情况",
        "相关",
        "进行",
        "评估",
    ):
        normalized = normalized.replace(phrase, "")
    return {normalized[index : index + 2] for index in range(max(0, len(normalized) - 1))}


def _best_fact(criterion: str, facts: Sequence[str]) -> tuple[str, float]:
    target = _bigrams(criterion)
    ranked = []
    for fact in facts:
        source = _bigrams(fact)
        score = len(target & source) / max(1, len(target))
        ranked.append((score, fact))
    score, fact = max(ranked, key=lambda item: item[0])
    return fact, score


def _rubric_category(criterion: str) -> str:
    rules = (
        ("URGENCY_TRIAGE", ("危险", "急诊", "意识", "呼吸困难", "大小便", "高热")),
        ("MEDICATION_ALLERGY", ("用药", "药物", "过敏", "疗效")),
        ("SOCIAL_EXPOSURE", ("职业", "工作", "暴露", "吸烟", "饮酒", "旅行", "同事")),
        ("PAST_FAMILY_HISTORY", ("既往", "家族", "亲属", "手术")),
        ("FUNCTIONAL_IMPACT", ("日常", "睡眠", "食欲", "活动", "工作影响")),
        ("DIFFERENTIAL_EXPLORATION", ("排除", "鉴别", "伴随")),
    )
    for category, words in rules:
        if any(word in criterion for word in words):
            return category
    return "SYMPTOM_CHARACTERIZATION"


__all__ = [
    "MediScopeTemporalAdapter",
    "MedPITemporalAdapter",
    "PatientSimTemporalAdapter",
    "MeddiesTemporalAdapter",
    "MedMemoryBenchTemporalAdapter",
    "MedDialogRubricsTemporalAdapter",
    "consultation_pairs",
    "extract_questions",
    "parse_speaker_turns",
]
