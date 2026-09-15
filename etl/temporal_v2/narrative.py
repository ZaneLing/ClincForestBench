from __future__ import annotations

import ast
import csv
import re
import xml.etree.ElementTree as ET
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


def _sentences(text: str) -> List[str]:
    return [
        part.strip()
        for part in re.split(r"(?<=[.!?])\s+(?=[A-Z0-9])", text.strip())
        if len(part.strip()) >= 25
    ]


def _modality(sentence: str) -> str:
    value = sentence.lower()
    if re.search(r"\b(ct|mri|x-ray|radiograph|ultrasound|sonograph|imaging)\b", value):
        return "IMAGING"
    if re.search(r"\b(ecg|ekg|electrocardio|echocardi)\w*\b", value):
        return "ECG"
    if re.search(r"\b(laboratory|blood|serum|level|count|culture|biopsy|test)\w*\b", value):
        return "LAB"
    if re.search(r"\b(examination|exam|palpation|auscultation)\w*\b", value):
        return "EXAM"
    if re.search(r"\b(treated|therapy|surgery|operation|medication|administered)\w*\b", value):
        return "INTERVENTION"
    return "HISTORY"


def _label(sentence: str, modality: str) -> str:
    names = {
        "IMAGING": "Review imaging finding",
        "ECG": "Review cardiology finding",
        "LAB": "Review diagnostic test",
        "EXAM": "Review examination finding",
        "INTERVENTION": "Recorded intervention",
        "HISTORY": "Review clinical course",
    }
    detail = re.sub(r"\s+", " ", sentence).strip()
    return f"{names[modality]} · {detail[:58]}{'…' if len(detail) > 58 else ''}"


def _time_proxy(sentence: str, sequence: int, previous: float) -> tuple[float, str]:
    value = sentence.lower()
    match = re.search(r"\b(?:day|hospital day)\s*(\d{1,3})\b", value)
    if match:
        return max(previous + 1, float(match.group(1)) * 1440), "MEDIUM"
    match = re.search(r"\b(\d{1,3})\s*(hours?|days?|weeks?)\s+later\b", value)
    if match:
        amount = float(match.group(1))
        unit = match.group(2)
        multiplier = 60 if unit.startswith("hour") else 1440 if unit.startswith("day") else 10080
        return previous + amount * multiplier, "MEDIUM"
    # A monotonic proxy preserves source sentence order, never claimed elapsed time.
    return max(previous + 1, float(sequence)), "LOW"


def _diagnosis_from_text(text: str, fallback: str) -> str:
    patterns = (
        r"(?:final diagnosis|diagnosed with|diagnosis was|diagnosis of)\s+([^.;]{3,120})",
        r"(?:consistent with|confirmed)\s+([^.;]{3,100})",
    )
    for pattern in patterns:
        matches = re.findall(pattern, text, flags=re.I)
        if matches:
            value = re.sub(r"\s+", " ", matches[-1]).strip(" ,:")
            return value[:140]
    return fallback[:180]


class NarrativeTemporalAdapter(TemporalAdapter):
    access_class = "PUBLIC_NARRATIVE_LOCAL_COPY"

    def _build_case(
        self,
        *,
        case_id: str,
        raw: Dict[str, Any],
        text: str,
        reference_diagnosis: str,
        source_id: str,
        source_table: str,
        initial_state: Dict[str, Any],
        reference_extra: Dict[str, Any] | None = None,
    ) -> TemporalCase:
        parts = _sentences(text)
        if len(parts) < 2:
            raise ValueError("Narrative does not contain a playable sequence")
        presentation_index = next(
            (
                index
                for index, sentence in enumerate(parts)
                if re.search(r"presented|admitted|hospitalized|referred", sentence, re.I)
            ),
            0,
        )
        initial_state = {
            **initial_state,
            "presentation": parts[presentation_index],
            "time_semantics": "Narrative order; explicit intervals retained when present",
        }
        events = []
        previous = 0.0
        candidates = [
            (index, sentence)
            for index, sentence in enumerate(parts)
            if index != presentation_index
            and not re.search(r"final diagnosis|diagnosed with|diagnosis was", sentence, re.I)
        ][:12]
        for output_index, (source_index, sentence) in enumerate(candidates, 1):
            modality = _modality(sentence)
            available, confidence = _time_proxy(sentence, output_index, previous)
            order = previous
            previous = available
            state_changing = modality == "INTERVENTION"
            events.append(
                make_event(
                    case_id=case_id,
                    event_id=f"{case_id}::NARRATIVE::{output_index:02d}",
                    event_type=(
                        "IMAGING_RESULT"
                        if modality == "IMAGING"
                        else "NARRATIVE_CLINICAL_EVENT"
                    ),
                    display=_label(sentence, modality),
                    modality=modality,
                    dataset=self.dataset_name,
                    source_table=source_table,
                    source_row_id=f"{source_id}:sentence:{source_index}",
                    relative_order_min=order,
                    relative_available_min=available,
                    confidence=confidence,
                    availability_semantics=(
                        "NARRATIVE_EXPLICIT_INTERVAL"
                        if confidence == "MEDIUM"
                        else "NARRATIVE_SEQUENCE_PROXY_NOT_ELAPSED_MINUTES"
                    ),
                    result={
                        "narrative_text": sentence,
                        "source_sentence_index": source_index,
                        "time_is_sequence_proxy": confidence == "LOW",
                    },
                    action_id=f"REVIEW_{modality}_{slug(sentence).upper()[:42]}",
                    arena_eligible=not state_changing,
                    state_changing=state_changing,
                    exclusion_reason=(
                        "STATE_CHANGING_INTERVENTION" if state_changing else None
                    ),
                    replay_mode=(
                        "OBSERVED_FIXED_TIME"
                        if confidence == "LOW"
                        else "OBSERVED_RESULT_WITH_SHIFTED_TAT"
                    ),
                )
            )
        eligible = [event for event in events if event.arena.arena_eligible]
        if not eligible:
            raise ValueError("Narrative has no revealable evidence")
        reference = {
            "reference_diagnosis": reference_diagnosis,
            "reference_strength": "NARRATIVE_METADATA_PROXY_REQUIRES_CLINICIAN_REVIEW",
            "is_absolute_ground_truth": False,
            **(reference_extra or {}),
        }
        graph = build_temporal_graph(case_id, events, reference)
        return TemporalCase(
            case_id=case_id,
            task_type="NARRATIVE_TEMPORAL_DIAGNOSIS",
            source={
                "dataset_family": self.dataset_name,
                "dataset_version": "LOCAL_SNAPSHOT",
                "source_case_id": source_id,
                "source_tables": [source_table],
                "access_class": self.access_class,
                "time_semantics": "NARRATIVE_SEQUENCE_WITH_EXPLICIT_INTERVALS_WHEN_AVAILABLE",
            },
            raw_source=raw,
            transformation={
                "schema_version": "clincforestbench.narrative-temporal-conversion.v2",
                "steps": [
                    {"step": 1, "name": "Preserve source record", "output": "raw_source"},
                    {"step": 2, "name": "Locate presentation sentence", "output": "initial_state"},
                    {"step": 3, "name": "Split narrative without rewriting text", "output": "timeline_events"},
                    {"step": 4, "name": "Classify each source sentence by modality", "output": "clinical_concept.modality"},
                    {"step": 5, "name": "Retain explicit intervals; mark ordinal fallback LOW", "output": "time + temporal_confidence"},
                    {"step": 6, "name": "Create action/result nodes and hide reference", "output": "temporal_graph"},
                ],
                "limitations": [
                    "Narrative sentence order is not equivalent to EHR event time.",
                    "LOW-confidence minute values are display-order proxies only.",
                    "Reference diagnosis requires clinician adjudication before benchmark release.",
                ],
                "safety_invariants": [
                    "NO_SYNTHETIC_CLINICAL_RESULTS",
                    "SOURCE_SENTENCES_PRESERVED_VERBATIM_IN_LOCAL_ARTIFACT",
                    "REFERENCE_HIDDEN_UNTIL_FINALIZATION",
                ],
            },
            anchor={
                "anchor_type": "NARRATIVE_PRESENTATION",
                "absolute_time": None,
                "relative_zero": 0,
                "time_system": "NARRATIVE_SEQUENCE",
                "timezone_policy": "NOT_APPLICABLE",
            },
            initial_state=initial_state,
            timeline_events=events,
            hidden_evidence_pool=[event.event_id for event in eligible],
            realized_trajectory=[
                {
                    "sequence": index,
                    "event_id": event.event_id,
                    "action_id": event.action_id,
                    "available_time_min": event.available_min(),
                    "time_semantics": event.time.availability_semantics,
                }
                for index, event in enumerate(events, 1)
            ],
            reference=reference,
            case_quality={
                "evidence_count": len(eligible),
                "modality_count": len({event.clinical_concept.modality for event in eligible}),
                "reference_quality": "HUMAN_REVIEW_REQUIRED",
                "checks": {
                    "anchor_present": True,
                    "source_text_preserved": True,
                    "real_results_only": True,
                    "narrative_time_limit_explicit": True,
                    "mvp_branchable": len(eligible) >= 1,
                },
            },
            temporal_quality={
                "anchor_confidence": "MEDIUM",
                "core_event_minimum_confidence": min(
                    (event.time.temporal_confidence.value for event in eligible),
                    default="LOW",
                ),
                "warnings": [
                    "NARRATIVE_SEQUENCE_IS_NOT_EXACT_EVENT_TIME",
                    "LOW_CONFIDENCE_MINUTES_ARE_ORDER_PROXIES",
                    "REFERENCE_REQUIRES_CLINICIAN_REVIEW",
                ],
            },
            arena_config={
                "time_mode": "WAIT_FOR_NEXT_RESULT",
                "time_bucket_min": 1,
                "unobserved_action_result": "UNOBSERVED_IN_RECORDED_EPISODE",
                "max_questions": 30,
                "narrative_sequence_mode": True,
            },
            temporal_graph=graph,
            mvp_simulations=build_mvp_simulations(events),
        )


class PMCTemporalAdapter(NarrativeTemporalAdapter):
    dataset_slug = "pmc"
    dataset_name = "PMC Case Reports"

    def __init__(self, root: Path = ROOT):
        super().__init__(root)
        self.source = root / "dataset/pmc_case_reports/PMC-Patients.csv"

    def list_cases(self, limit: int = 20) -> List[Dict[str, Any]]:
        result = []
        with self.source.open(encoding="utf-8", errors="replace", newline="") as handle:
            for row in csv.DictReader(handle):
                patient = row.get("patient", "")
                if not (450 <= len(patient) <= 8000):
                    continue
                if not re.search(r"presented|admitted|hospitalized|referred", patient, re.I):
                    continue
                if not re.search(r"diagnos|consistent with|confirmed", patient, re.I):
                    continue
                result.append(row)
                if len(result) >= limit:
                    break
        return result

    def load_case(self, candidate: Dict[str, Any]) -> TemporalCase:
        patient = candidate["patient"]
        uid = candidate["patient_uid"]
        title = candidate.get("title") or "PMC case report"
        try:
            age = ast.literal_eval(candidate.get("age") or "[]")
        except (SyntaxError, ValueError):
            age = candidate.get("age")
        return self._build_case(
            case_id=f"CFB_PMC_{slug(uid).upper()}",
            raw={
                "patient_uid": uid,
                "pmid": candidate.get("PMID"),
                "title": title,
                "file_path": candidate.get("file_path"),
                "patient_narrative": patient,
                "age_source": candidate.get("age"),
                "gender_source": candidate.get("gender"),
            },
            text=patient,
            reference_diagnosis=_diagnosis_from_text(patient, title),
            source_id=uid,
            source_table="PMC-Patients.csv",
            initial_state={"age": age, "sex": candidate.get("gender")},
            reference_extra={"article_title": title, "pmid": candidate.get("PMID")},
        )


class NEJMTemporalAdapter(NarrativeTemporalAdapter):
    dataset_slug = "nejm"
    dataset_name = "NEJM CPC"

    def __init__(self, root: Path = ROOT):
        super().__init__(root)
        self.source = root / "dataset/nejm_cpc/pubmed_records.xml"

    def list_cases(self, limit: int = 20) -> List[Dict[str, Any]]:
        result = []
        root = ET.parse(self.source).getroot()
        for article in root.findall(".//PubmedArticle"):
            title_node = article.find(".//ArticleTitle")
            title = "" if title_node is None else "".join(title_node.itertext())
            abstract = " ".join(
                "".join(node.itertext())
                for node in article.findall(".//Abstract/AbstractText")
            ).strip()
            if "case record" not in title.lower() or len(abstract) < 150:
                continue
            mesh = []
            for heading in article.findall(".//MeshHeading"):
                descriptor = heading.find("DescriptorName")
                if descriptor is None:
                    continue
                mesh.append(
                    {
                        "term": "".join(descriptor.itertext()),
                        "major_topic": descriptor.attrib.get("MajorTopicYN") == "Y"
                        or any(
                            qualifier.attrib.get("MajorTopicYN") == "Y"
                            for qualifier in heading.findall("QualifierName")
                        ),
                    }
                )
            result.append(
                {
                    "pmid": article.findtext(".//PMID"),
                    "doi": next(
                        (
                            node.text
                            for node in article.findall(".//ArticleId")
                            if node.attrib.get("IdType") == "doi"
                        ),
                        None,
                    ),
                    "title": title,
                    "abstract": abstract,
                    "mesh_terms": mesh,
                }
            )
            if len(result) >= limit:
                break
        return result

    def load_case(self, candidate: Dict[str, Any]) -> TemporalCase:
        mesh = [
            item["term"]
            for item in candidate["mesh_terms"]
            if item["major_topic"]
            and item["term"]
            not in {
                "Aged",
                "Adult",
                "Female",
                "Humans",
                "Male",
                "Diagnosis, Differential",
            }
        ]
        reference = " / ".join(mesh[:3]) or candidate["title"]
        return self._build_case(
            case_id=f"CFB_NEJM_{candidate['pmid']}",
            raw={
                "pmid": candidate["pmid"],
                "doi": candidate["doi"],
                "title": candidate["title"],
                "abstract": candidate["abstract"],
                "mesh_terms": candidate["mesh_terms"],
            },
            text=candidate["abstract"],
            reference_diagnosis=reference,
            source_id=str(candidate["pmid"]),
            source_table="PubMed XML",
            initial_state={"article_title": candidate["title"]},
            reference_extra={
                "pmid": candidate["pmid"],
                "doi": candidate["doi"],
                "mesh_diagnosis_proxy": mesh,
            },
        )
