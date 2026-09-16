from backend.app.domain.belief import BeliefSubmission, DiagnosisBelief
from backend.app.domain.session import Player
from backend.app.repositories.memory import InMemoryArenaRepository
from backend.app.services.arena_service import ArenaService
from backend.app.services.case_service import CaseService
from backend.app.services.graph_builder import build_case_graph
from backend.app.services.state_reducer import replay_session


def main() -> None:
    cases = CaseService()
    repository = InMemoryArenaRepository()
    arena = ArenaService(cases, repository)
    case_id = cases.case_ids()[0]
    case = cases.get(case_id)
    condition_id = case.oracle.pathology
    belief = BeliefSubmission(
        diagnoses=[
            DiagnosisBelief(
                condition_id=condition_id, rank=1, probability=0.6
            )
        ],
        overall_confidence=0.5,
    )
    initial_id = case.initial_evidence.evidence_id
    scoped_ids = set(cases.question_scope([condition_id], initial_id))
    positive_ids = [
        item.evidence_id
        for item in case.truth
        if item.evidence_id in scoped_ids
        and item.status.value in {"PRESENT", "VALUE"}
    ]
    roots = positive_ids[:3] or sorted(scoped_ids)[:3]
    strategies = {
        "fast": roots[:2],
        "broad": list(reversed(roots[:2])),
        "alternative": [roots[2]],
    }
    completed_sessions = []
    for name, evidence_ids in strategies.items():
        session = arena.create_session(
            case_id, Player(player_id=f"cli-{name}")
        )
        arena.submit_belief(
            session.session_id, belief, f"{name}-belief-0"
        )
        print(f"\n{name.upper()} · {session.session_id[:8]}")
        for index, evidence_id in enumerate(evidence_ids, start=1):
            result = arena.ask_evidence(
                session.session_id,
                evidence_id,
                f"{name}-ask-{index}",
            )
            print(f"  {evidence_id} → {result.observation.status.value}")
            # EVERY_STEP is the default protocol: the player must commit a
            # new differential after each newly revealed observation.
            arena.submit_belief(
                session.session_id,
                belief,
                f"{name}-belief-{index}",
            )
        completed = arena.finalize(
            session.session_id, belief, f"{name}-final"
        )
        replayed = replay_session(session.session_id, cases, repository)
        assert replayed.state_hash == completed.final_state_hash
        completed_sessions.append(completed)

    events = {
        session.session_id: repository.events(session.session_id)
        for session in completed_sessions
    }
    states = {
        session.session_id: repository.states(session.session_id)
        for session in completed_sessions
    }
    graph = build_case_graph(case_id, completed_sessions, events, states)
    merge_verified = (
        completed_sessions[0].final_state_hash
        == completed_sessions[1].final_state_hash
    )
    print(f"\nCase {case_id}: {len(graph.nodes)} canonical nodes, {len(graph.edges)} edges")
    print(f"Opposite-order state merge verified: {merge_verified}")
    print("All three sessions replayed successfully.")


if __name__ == "__main__":
    main()
