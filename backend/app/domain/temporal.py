from __future__ import annotations

import hashlib
import json
from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field, model_validator


class TemporalConfidence(str, Enum):
    EXACT = "EXACT"
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"
    UNKNOWN = "UNKNOWN"


class TemporalReplayMode(str, Enum):
    OBSERVED_FIXED_TIME = "OBSERVED_FIXED_TIME"
    OBSERVED_RESULT_WITH_SHIFTED_TAT = "OBSERVED_RESULT_WITH_SHIFTED_TAT"
    UNOBSERVED = "UNOBSERVED"


class PendingStatus(str, Enum):
    PENDING = "PENDING"
    AVAILABLE = "AVAILABLE"
    REVIEWED = "REVIEWED"
    CANCELLED = "CANCELLED"
    UNOBSERVED = "UNOBSERVED"


class TemporalPoint(BaseModel):
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
    temporal_confidence: TemporalConfidence
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


class EventArenaPolicy(BaseModel):
    arena_eligible: bool
    state_changing_intervention: bool = False
    state_changing_intervention_before_result: bool = False
    leakage_risk: str = "LOW"
    exclusion_reason: Optional[str] = None
    temporal_replay_mode: TemporalReplayMode


class CanonicalTemporalEvent(BaseModel):
    case_id: str
    event_id: str
    event_type: str
    clinical_concept: ClinicalConcept
    action_id: Optional[str] = None
    time: TemporalPoint
    result: Dict[str, Any] = Field(default_factory=dict)
    provenance: EventProvenance
    arena: EventArenaPolicy

    def order_min(self) -> float:
        for value in (
            self.time.relative_order_min,
            self.time.relative_start_min,
            self.time.relative_acquired_min,
            self.time.relative_available_min,
            self.time.relative_documented_min,
        ):
            if value is not None:
                return float(value)
        return 0.0

    def available_min(self) -> float:
        for value in (
            self.time.relative_available_min,
            self.time.relative_documented_min,
            self.time.relative_acquired_min,
            self.time.relative_end_min,
            self.time.relative_start_min,
            self.time.relative_order_min,
        ):
            if value is not None:
                return float(value)
        return self.order_min()


class TemporalGraphNode(BaseModel):
    node_id: str
    node_type: str
    label: str
    subtitle: str = ""
    game_time_min: float
    reveal_time_min: float
    lane: str
    event_id: Optional[str] = None
    temporal_confidence: TemporalConfidence = TemporalConfidence.HIGH
    data: Dict[str, Any] = Field(default_factory=dict)


class TemporalGraphEdge(BaseModel):
    edge_id: str
    source_node: str
    target_node: str
    edge_type: str
    action_id: Optional[str] = None
    action_time_min: Optional[float] = None
    result_available_time_min: Optional[float] = None
    latency_min: Optional[float] = None
    result_status: str = "OBSERVED"
    source_event_id: Optional[str] = None


class TemporalGraph(BaseModel):
    schema_version: str = "clincforestbench.temporal-graph.v2"
    root_id: str
    nodes: List[TemporalGraphNode]
    edges: List[TemporalGraphEdge]


class TemporalCase(BaseModel):
    case_id: str
    case_version: str = "2.0.0"
    task_type: str
    source: Dict[str, Any]
    raw_source: Dict[str, Any] = Field(default_factory=dict)
    transformation: Dict[str, Any] = Field(default_factory=dict)
    anchor: Dict[str, Any]
    initial_state: Dict[str, Any]
    timeline_events: List[CanonicalTemporalEvent]
    queryable_context: List[Dict[str, Any]] = Field(default_factory=list)
    hidden_evidence_pool: List[str] = Field(default_factory=list)
    realized_trajectory: List[Dict[str, Any]] = Field(default_factory=list)
    reference: Dict[str, Any]
    case_quality: Dict[str, Any]
    temporal_quality: Dict[str, Any]
    arena_config: Dict[str, Any]
    temporal_graph: TemporalGraph
    mvp_simulations: List[Dict[str, Any]] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_temporal_contract(self) -> "TemporalCase":
        ids = [event.event_id for event in self.timeline_events]
        if len(ids) != len(set(ids)):
            raise ValueError("Temporal event ids must be unique")
        if set(self.hidden_evidence_pool) - set(ids):
            raise ValueError("Hidden evidence pool contains unknown event ids")
        for event in self.timeline_events:
            order = event.time.relative_order_min
            available = event.time.relative_available_min
            if order is not None and available is not None and available < order:
                if "TEMPORAL_INCONSISTENCY" not in self.temporal_quality.get(
                    "warnings", []
                ):
                    raise ValueError(
                        f"{event.event_id}: available time precedes order time"
                    )
        return self


class PendingAction(BaseModel):
    pending_id: str
    action_id: str
    ordered_game_time: float
    expected_available_game_time: Optional[float]
    source_event_id: Optional[str]
    temporal_replay_mode: TemporalReplayMode
    status: PendingStatus


class TemporalState(BaseModel):
    case_id: str
    current_time_min: float = 0
    revealed_event_ids: List[str] = Field(default_factory=list)
    pending_actions: List[PendingAction] = Field(default_factory=list)
    state_hash: str = ""

    def refreshed(self, bucket_minutes: int = 5) -> "TemporalState":
        return self.model_copy(
            update={
                "state_hash": compute_temporal_state_hash(
                    self.case_id,
                    self.revealed_event_ids,
                    self.pending_actions,
                    self.current_time_min,
                    bucket_minutes,
                )
            }
        )


def compute_temporal_state_hash(
    case_id: str,
    revealed_event_ids: List[str],
    pending_actions: List[PendingAction],
    current_time_min: float,
    bucket_minutes: int = 5,
) -> str:
    if bucket_minutes <= 0:
        raise ValueError("bucket_minutes must be positive")
    pending = sorted(
        (
            item.action_id,
            None
            if item.expected_available_game_time is None
            else int(item.expected_available_game_time // bucket_minutes),
            item.status.value,
        )
        for item in pending_actions
        if item.status in {PendingStatus.PENDING, PendingStatus.AVAILABLE}
    )
    payload = {
        "case_id": case_id,
        "revealed_event_ids": sorted(set(revealed_event_ids)),
        "pending": pending,
        "time_bucket": int(current_time_min // bucket_minutes),
    }
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()
