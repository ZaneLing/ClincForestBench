from typing import List, Optional

from pydantic import BaseModel, Field

from .enums import ActionResultType, ActionType
from .evidence import EvidenceResponse
from .state import ObservationState


class ClinicalAction(BaseModel):
    action_type: ActionType
    client_event_id: str
    evidence_id: Optional[str] = None


class StepResult(BaseModel):
    result_type: ActionResultType
    action: ClinicalAction
    observation: Optional[EvidenceResponse] = None
    state_before_hash: str
    state_after_hash: str
    state: ObservationState
    message: str = ""


class AvailableAction(BaseModel):
    action_type: ActionType
    evidence_id: Optional[str] = None
    question_en: Optional[str] = None
    dependency_met: bool = True
    semantic_role: Optional[str] = None
    clinical_domain: Optional[str] = None
    data_type: Optional[str] = None
    exposure_tier: Optional[int] = None
    suggested_by: List[str] = Field(default_factory=list)
    parent_evidence_id: Optional[str] = None
    parent_question_en: Optional[str] = None
    action_kind: str = "ASK_QUESTION"
    resource_type: Optional[str] = None
    mutates_state: bool = False


class AvailableActions(BaseModel):
    actions: List[AvailableAction] = Field(default_factory=list)
