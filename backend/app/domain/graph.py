from typing import Dict, List

from pydantic import BaseModel, Field


class GraphNode(BaseModel):
    case_id: str
    state_hash: str
    support: int = 0
    revealed_evidence_ids: List[str] = Field(default_factory=list)


class GraphEdge(BaseModel):
    case_id: str
    source_hash: str
    target_hash: str
    action_evidence_id: str
    support: int = 0
    probability: float = 0.0
    subgroup_counts: Dict[str, int] = Field(default_factory=dict)


class CaseGraph(BaseModel):
    case_id: str
    session_count: int = 0
    completed_session_count: int = 0
    participant_count: int = 0
    physician_count: int = 0
    physician_session_count: int = 0
    nodes: List[GraphNode]
    edges: List[GraphEdge]
