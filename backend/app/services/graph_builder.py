from __future__ import annotations

from collections import Counter, defaultdict
from math import log2
from typing import Dict, Iterable, List, Tuple

from backend.app.domain.enums import ActionResultType, ActionType, PlayerType, SessionStatus
from backend.app.domain.graph import CaseGraph, GraphEdge, GraphNode
from backend.app.domain.session import SessionEvent, SessionRecord, StateSnapshot


def branch_entropy(edges: Iterable[GraphEdge]) -> float:
    values = [edge.support for edge in edges]
    total = sum(values)
    return -sum((n / total) * log2(n / total) for n in values if n and total)


def build_case_graph(
    case_id: str,
    sessions: List[SessionRecord],
    events_by_session: Dict[str, List[SessionEvent]],
    states_by_session: Dict[str, List[StateSnapshot]],
) -> CaseGraph:
    case_sessions = [session for session in sessions if session.case_id == case_id]
    node_support = Counter()
    node_evidences: Dict[str, List[str]] = {}
    edge_support = Counter()
    subgroup_counts = defaultdict(Counter)
    for session in case_sessions:
        for snapshot in states_by_session.get(session.session_id, []):
            state_hash = snapshot.state.state_hash
            node_support[state_hash] += 1
            node_evidences[state_hash] = sorted(snapshot.state.revealed)
        for event in events_by_session.get(session.session_id, []):
            if event.event_type != ActionType.ASK_EVIDENCE.value or event.result_type != ActionResultType.OBSERVATION.value:
                continue
            key = (event.state_before_hash, event.state_after_hash, event.action["evidence_id"])
            edge_support[key] += 1
            subgroup_counts[key][session.player.player_type.value] += 1
    outgoing = Counter()
    for (source, _, _), support in edge_support.items():
        outgoing[source] += support
    nodes = [
        GraphNode(case_id=case_id, state_hash=key, support=value, revealed_evidence_ids=node_evidences[key])
        for key, value in sorted(node_support.items())
    ]
    edges = [
        GraphEdge(
            case_id=case_id, source_hash=source, target_hash=target,
            action_evidence_id=evidence_id, support=support,
            probability=support / outgoing[source],
            subgroup_counts=dict(subgroup_counts[(source, target, evidence_id)]),
        )
        for (source, target, evidence_id), support in sorted(edge_support.items())
    ]
    physician_sessions = [
        session
        for session in case_sessions
        if session.player.player_type == PlayerType.PHYSICIAN
    ]
    return CaseGraph(
        case_id=case_id,
        session_count=len(case_sessions),
        completed_session_count=sum(
            session.status == SessionStatus.COMPLETED for session in case_sessions
        ),
        participant_count=len(
            {session.player.player_id for session in case_sessions}
        ),
        physician_count=len(
            {session.player.player_id for session in physician_sessions}
        ),
        physician_session_count=len(physician_sessions),
        nodes=nodes,
        edges=edges,
    )
