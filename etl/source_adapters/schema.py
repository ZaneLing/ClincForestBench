"""Ingestion records. Source dates are audit metadata, never runtime gates."""
from __future__ import annotations

from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel, Field, model_validator


class SourceConfidence(str, Enum):
    EXACT = "EXACT"
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"
    UNKNOWN = "UNKNOWN"


class SourceTime(BaseModel):
    order_time: Optional[str] = None
    acquired_time: Optional[str] = None
    available_time: Optional[str] = None
    documented_time: Optional[str] = None
    start_time: Optional[str] = None
    end_time: Optional[str] = None
    relative_order_min: Optional[float] = None
    relative_acquired_min: Optional[float] = None
    relative_available_min: Optional[float] = None
    relative_documented_min: Optional[float] = None
    relative_start_min: Optional[float] = None
    relative_end_min: Optional[float] = None
    source_confidence: SourceConfidence = SourceConfidence.UNKNOWN
    availability_semantics: str


class ClinicalConcept(BaseModel):
    canonical_id: str
    display: str
    source_code: Optional[str] = None
    source_system: str
    modality: str


class EventProvenance(BaseModel):
    dataset: str
    source_table: str
    source_row_id: str
    is_observed_real_result: bool


class EvidencePolicy(BaseModel):
    arena_eligible: bool
    state_changing_intervention: bool = False
    state_changing_intervention_before_result: bool = False
    leakage_risk: str = "LOW"
    exclusion_reason: Optional[str] = None


class SourceEvidence(BaseModel):
    case_id: str
    event_id: str
    event_type: str
    clinical_concept: ClinicalConcept
    action_id: Optional[str] = None
    time: SourceTime
    result: dict[str, Any] = Field(default_factory=dict)
    provenance: EventProvenance
    arena: EvidencePolicy

    def order_min(self) -> float:
        """Source offset used only to select a consistent source result."""
        for field in ("relative_order_min", "relative_start_min", "relative_acquired_min",
                      "relative_available_min", "relative_documented_min"):
            value = getattr(self.time, field)
            if value is not None:
                return float(value)
        return 0.0

    def available_min(self) -> float:
        """Source result offset for auditing and intervention filtering."""
        for field in ("relative_available_min", "relative_documented_min", "relative_acquired_min",
                      "relative_end_min", "relative_start_min", "relative_order_min"):
            value = getattr(self.time, field)
            if value is not None:
                return float(value)
        return self.order_min()


class SourceCase(BaseModel):
    case_id: str
    task_type: str
    source: dict[str, Any]
    raw_source: dict[str, Any] = Field(default_factory=dict)
    anchor: dict[str, Any]
    initial_state: dict[str, Any]
    evidence_events: list[SourceEvidence]
    queryable_context: list[dict[str, Any]] = Field(default_factory=list)
    hidden_evidence_pool: list[str] = Field(default_factory=list)
    reference: dict[str, Any]
    case_quality: dict[str, Any]

    @model_validator(mode="after")
    def validate_evidence_ids(self) -> "SourceCase":
        ids = [event.event_id for event in self.evidence_events]
        if len(ids) != len(set(ids)):
            raise ValueError("Source evidence ids must be unique")
        if set(self.hidden_evidence_pool) - set(ids):
            raise ValueError("Evidence pool contains unknown event ids")
        # Reject contradictory source records during ingestion. This does not
        # impose an acquisition order or a delay on the runnable environment.
        for event in self.evidence_events:
            ordered = event.time.relative_order_min
            resulted = event.time.relative_available_min
            if ordered is not None and resulted is not None and resulted < ordered:
                raise ValueError(f"{event.event_id}: source result date precedes its order date")
        return self
