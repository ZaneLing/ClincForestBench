from backend.app.domain.belief import BeliefSubmission, DiagnosisBelief
from backend.app.domain.session import Player
from backend.app.repositories.memory import InMemoryArenaRepository
from backend.app.services.arena_service import ArenaService
from backend.app.services.graph_builder import build_case_graph
from backend.app.services.export_service import ExportService
from backend.app.services.state_reducer import replay_session


def test_event_idempotency_replay_and_graph(cases):
    repository = InMemoryArenaRepository()
    arena = ArenaService(cases, repository)
    session = arena.create_session(cases.case_ids()[0], Player(player_id="tester"))
    condition = sorted(cases.condition_catalog)[0]
    belief = BeliefSubmission(diagnoses=[DiagnosisBelief(condition_id=condition, rank=1, probability=0.8)], overall_confidence=0.7)
    arena.submit_belief(session.session_id, belief, "belief-0")
    evidence = next(item for item in arena.available_actions(session.session_id).actions if item.dependency_met)
    first = arena.ask_evidence(session.session_id, evidence.evidence_id, "ask-1")
    duplicate = arena.ask_evidence(session.session_id, evidence.evidence_id, "ask-1")
    assert first.state_after_hash == duplicate.state_after_hash
    assert len(repository.events(session.session_id)) == 2
    completed = arena.finalize(session.session_id, belief, "final-1")
    replayed = replay_session(session.session_id, cases, repository)
    assert replayed.state_hash == completed.final_state_hash
    graph = build_case_graph(
        session.case_id,
        repository.all_sessions(),
        {session.session_id: repository.events(session.session_id)},
        {session.session_id: repository.states(session.session_id)},
    )
    assert len(graph.nodes) == 2
    assert len(graph.edges) == 1
    assert graph.session_count == 1
    assert graph.completed_session_count == 1
    assert graph.participant_count == 1
    assert graph.physician_count == 0


def test_completed_session_exports_all_research_tables(cases, tmp_path):
    repository = InMemoryArenaRepository()
    arena = ArenaService(cases, repository)
    session = arena.create_session(cases.case_ids()[0], Player(player_id="exporter"))
    condition = sorted(cases.condition_catalog)[0]
    belief = BeliefSubmission(
        diagnoses=[DiagnosisBelief(condition_id=condition, rank=1, probability=1.0)],
        overall_confidence=0.8,
    )
    arena.submit_belief(session.session_id, belief, "belief-export")
    arena.finalize(session.session_id, belief, "final-export")
    output = ExportService(cases, repository, tmp_path).export(session.session_id)
    expected = {
        "cases.parquet", "sessions.parquet", "events.parquet", "states.parquet",
        "beliefs.parquet", "graph_nodes.parquet", "graph_edges.parquet",
    }
    assert expected <= {path.name for path in output.iterdir()}
    assert list(output.glob("session_bundle_*.json"))
