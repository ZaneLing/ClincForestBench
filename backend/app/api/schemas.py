from __future__ import annotations

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field

from backend.app.domain.belief import BeliefSubmission
from backend.app.domain.enums import ArenaMode, BeliefCaptureMode, PlayerType


class CreateSessionRequest(BaseModel):
    case_id: Optional[str] = None
    player_id: str = "local-researcher"
    player_type: PlayerType = PlayerType.RESEARCHER
    specialty: Optional[str] = None
    training_level: Optional[str] = None
    years_experience: Optional[float] = None
    site: Optional[str] = None
    country: Optional[str] = None
    arena_mode: ArenaMode = ArenaMode.FREE_EXPLORATION
    belief_capture_mode: BeliefCaptureMode = BeliefCaptureMode.EVERY_STEP
    random_seed: int = 0


class EvidenceActionRequest(BaseModel):
    evidence_id: str
    client_event_id: str = Field(min_length=1)
    client_timestamp: Optional[datetime] = None
    latency_ms: Optional[int] = Field(default=None, ge=0)


class BeliefRequest(BaseModel):
    belief: BeliefSubmission
    client_event_id: str = Field(min_length=1)
    client_timestamp: Optional[datetime] = None


class FinalizeRequest(BaseModel):
    belief: BeliefSubmission
    client_event_id: str = Field(min_length=1)


class ExportRequest(BaseModel):
    session_id: Optional[str] = None


class AccountCredentials(BaseModel):
    username: str = Field(min_length=3, max_length=64)
    password: str = Field(min_length=4, max_length=128)


class CreateModelRunRequest(BaseModel):
    model_id: str = Field(min_length=3, max_length=256)
    case_id: str = Field(min_length=1, max_length=128)
    max_questions: int = Field(default=30, ge=1, le=30)
