from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional
from uuid import uuid4

from pydantic import BaseModel, Field

from .session import utc_now


class ModelDecision(BaseModel):
    diagnoses: List[str] = Field(min_length=1)
    next_action_id: Optional[str] = None
    final: bool = False
    final_condition_id: Optional[str] = None
    rationale: str = ""


class ModelRunRecord(BaseModel):
    run_id: str = Field(default_factory=lambda: str(uuid4()))
    session_id: str
    model_id: str
    provider: str
    case_id: str
    dataset_name: str
    status: str = "ACTIVE"
    max_questions: int = Field(default=30, ge=1, le=30)
    forced_final: bool = False
    last_error: Optional[str] = None
    created_at: datetime = Field(default_factory=utc_now)
    completed_at: Optional[datetime] = None


class ModelInteractionRecord(BaseModel):
    interaction_id: str = Field(default_factory=lambda: str(uuid4()))
    run_id: str
    step: int
    request_payload: Dict[str, Any]
    response_payload: Optional[Dict[str, Any]] = None
    assistant_content: Optional[str] = None
    parsed_decision: Optional[Dict[str, Any]] = None
    application_result: Optional[Dict[str, Any]] = None
    error: Optional[str] = None
    latency_ms: Optional[int] = None
    created_at: datetime = Field(default_factory=utc_now)
