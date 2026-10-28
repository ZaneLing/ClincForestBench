from __future__ import annotations

import math
import re
from abc import ABC, abstractmethod
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import duckdb

from etl.common import dump_json
from .schema import (
    ClinicalConcept, EvidencePolicy, EventProvenance, SourceCase,
    SourceConfidence, SourceEvidence, SourceTime,
)

ROOT = Path(__file__).resolve().parents[2]
SOURCE_ROOT = ROOT / "data/processed/sources"


def parse_time(value):
    if value in (None, "", "NaT"):
        return None
    if isinstance(value, datetime):
        return value.replace(tzinfo=None)
    try:
        parsed = datetime.fromisoformat(str(value).strip().replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo:
        parsed = parsed.astimezone(timezone.utc).replace(tzinfo=None)
    return parsed


def iso(value):
    parsed = parse_time(value)
    return parsed.isoformat(timespec="seconds") if parsed else None


def relative_minutes(value, anchor):
    parsed = parse_time(value)
    return round((parsed - anchor).total_seconds() / 60, 2) if parsed else None


def clean(value):
    if isinstance(value, float) and (math.isnan(value) or math.isinf(value)):
        return None
    if isinstance(value, datetime):
        return value.isoformat(timespec="seconds")
    return value


def slug(value):
    return re.sub(r"[^a-z0-9]+", "_", value.lower()).strip("_")[:72] or "unknown"


def canonical_action(display, modality):
    upper = display.upper()
    rules = (
        (("TROPONIN",), "ORDER_TROPONIN"),
        (("D-DIMER", "D DIMER"), "ORDER_D_DIMER"),
        (("BLOOD GAS", "ABG", "PH, BLOOD"), "ORDER_BLOOD_GAS"),
        (("COMPLETE BLOOD", "CBC", "HEMOGRAM"), "ORDER_CBC"),
        (("COMPREHENSIVE METABOLIC", "CMP"), "ORDER_CMP"),
        (("BASIC METABOLIC", "BMP"), "ORDER_BMP"),
        (("CTA", "CT ANGIO"), "ORDER_CTA"),
        (("CT CHEST",), "ORDER_CT_CHEST"),
        (("CT ABD",), "ORDER_CT_ABDOMEN"),
        (("CHEST", "CXR"), "ORDER_CHEST_XRAY"),
        (("ULTRASOUND", " US "), "ORDER_ULTRASOUND"),
        (("ECG", "EKG", "ELECTROCARD"), "ORDER_ECG"),
    )
    for needles, action in rules:
        if any(needle in upper for needle in needles):
            return action
    prefix = {"LAB": "ORDER_LAB", "IMAGING": "ORDER_IMAGING", "ECG": "ORDER_ECG",
              "HISTORY": "REVIEW_HISTORY", "VITALS": "REVIEW_VITAL_TREND",
              "INTERVENTION": "OBSERVE_INTERVENTION", "DIAGNOSIS": "REVIEW_DIAGNOSIS"}.get(modality, "REVIEW_EVENT")
    return f"{prefix}_{slug(display).upper()[:48]}"


def make_event(*, case_id, event_id, event_type, display, modality, dataset,
               source_table, source_row_id, availability_semantics, anchor=None,
               confidence="HIGH", result=None, action_id=None, arena_eligible=True,
               state_changing=False, intervention_before_result=False,
               leakage_risk="LOW", exclusion_reason=None, **source_dates) -> SourceEvidence:
    dates = {}
    for prefix in ("order", "acquired", "available", "documented", "start", "end"):
        absolute = source_dates.get(f"{prefix}_time")
        relative = source_dates.get(f"relative_{prefix}_min")
        dates[f"{prefix}_time"] = iso(absolute)
        dates[f"relative_{prefix}_min"] = (
            relative if relative is not None else relative_minutes(absolute, anchor) if anchor else None
        )
    action = action_id or canonical_action(display, modality)
    return SourceEvidence(
        case_id=case_id, event_id=event_id, event_type=event_type, action_id=action,
        clinical_concept=ClinicalConcept(
            canonical_id=action.replace("ORDER_", "").replace("REVIEW_", ""), display=display,
            source_code=str(source_row_id), source_system=dataset, modality=modality,
        ),
        time=SourceTime(**dates, source_confidence=SourceConfidence(confidence),
                        availability_semantics=availability_semantics),
        result={key: clean(value) for key, value in (result or {}).items()},
        provenance=EventProvenance(dataset=dataset, source_table=source_table,
                                   source_row_id=str(source_row_id), is_observed_real_result=True),
        arena=EvidencePolicy(arena_eligible=arena_eligible, state_changing_intervention=state_changing,
                             state_changing_intervention_before_result=intervention_before_result,
                             leakage_risk=leakage_risk, exclusion_reason=exclusion_reason),
    )


def attach_conversion_audit(case: SourceCase, candidate: dict[str, Any]) -> SourceCase:
    raw = case.raw_source or {
        "candidate_row": {key: clean(value) for key, value in candidate.items()},
        "event_source_extracts": [
            {"source_table": event.provenance.source_table,
             "source_row_id": event.provenance.source_row_id,
             "source_time_fields": event.time.model_dump(mode="json"),
             "source_result_fields": event.result}
            for event in case.evidence_events
        ],
    }
    return case.model_copy(update={"raw_source": raw})


class SourceAdapter(ABC):
    dataset_slug: str
    dataset_name: str

    def __init__(self, root: Path = ROOT):
        self.root = root
        self.connection = duckdb.connect()
        self.connection.execute("PRAGMA threads=4")

    @abstractmethod
    def list_cases(self, limit=20):
        raise NotImplementedError

    @abstractmethod
    def load_case(self, candidate) -> SourceCase:
        raise NotImplementedError

    def write_case(self, case: SourceCase):
        folder = self.root / "data/processed/sources/case_bundles" / self.dataset_slug / case.case_id
        dump_json(folder / "case.json", case.model_dump(mode="json"))
        return {
            "case_id": case.case_id, "dataset_name": self.dataset_name, "task_type": case.task_type,
            "reference_label": case.reference.get("adjudicated_primary_diagnosis")
            or case.reference.get("primary_diagnosis") or case.reference.get("hospital_principal_diagnosis")
            or case.reference.get("reference_diagnosis"),
            "event_count": len(case.evidence_events),
            "eligible_event_count": sum(event.arena.arena_eligible for event in case.evidence_events),
            "path": str(folder.relative_to(self.root) / "case.json"),
            "checks": case.case_quality.get("checks", {}),
        }
