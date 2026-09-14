from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field

from .belief import BeliefSubmission
from .enums import ArenaMode, BeliefCaptureMode, PlayerType, SessionStatus
from .state import ObservationState


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class Player(BaseModel):
    player_id: str
    player_type: PlayerType = PlayerType.RESEARCHER
    specialty: Optional[str] = None
    training_level: Optional[str] = None
    years_experience: Optional[float] = None
    site: Optional[str] = None
    country: Optional[str] = None
    model_metadata: Optional[Dict[str, Any]] = None


class SessionRecord(BaseModel):
    session_id: str
    case_id: str
    case_hash: str
    player: Player
    arena_mode: ArenaMode
    belief_capture_mode: BeliefCaptureMode
    dataset_version: str
    case_version: str
    arena_version: str
    ui_version: str
    random_seed: int
    status: SessionStatus = SessionStatus.ACTIVE
    started_at: datetime = Field(default_factory=utc_now)
    completed_at: Optional[datetime] = None
    final_state_hash: Optional[str] = None


class SessionEvent(BaseModel):
    event_id: str
    session_id: str
    sequence: int
    event_type: str
    client_event_id: str
    action: Dict[str, Any] = Field(default_factory=dict)
    observation: Optional[Dict[str, Any]] = None
    state_before_hash: str
    state_after_hash: str
    server_timestamp: datetime = Field(default_factory=utc_now)
    client_timestamp: Optional[datetime] = None
    latency_ms: Optional[int] = None
    schema_version: str = "1.0"
    result_type: Optional[str] = None


class StateSnapshot(BaseModel):
    session_id: str
    step: int
    state: ObservationState
    created_at: datetime = Field(default_factory=utc_now)


class BeliefSnapshot(BaseModel):
    belief_id: str
    session_id: str
    step: int
    state_hash: str
    belief: BeliefSubmission
    is_final: bool = False
    timestamp: datetime = Field(default_factory=utc_now)
