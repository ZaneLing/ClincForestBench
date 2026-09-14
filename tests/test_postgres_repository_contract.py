from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from backend.app.db.base import Base
from backend.app.domain.belief import BeliefSubmission, DiagnosisBelief
from backend.app.domain.session import Player
from backend.app.repositories.sqlalchemy import SqlAlchemyArenaRepository
from backend.app.services.arena_service import ArenaService
from backend.app.services.database_seed import seed_benchmark
from backend.app.services.state_reducer import replay_session


def test_persistent_repository_contract_and_seed(cases, tmp_path):
    # SQLite is used only as a fast contract test; production configuration is PostgreSQL.
    engine = create_engine(f"sqlite:///{tmp_path / 'contract.db'}")
    Base.metadata.create_all(engine)
    seed_benchmark(engine, cases)
    seed_benchmark(engine, cases)
    repository = SqlAlchemyArenaRepository(sessionmaker(bind=engine, expire_on_commit=False))
    arena = ArenaService(cases, repository)
    session = arena.create_session(cases.case_ids()[0], Player(player_id="persistent"))
    condition = sorted(cases.condition_catalog)[0]
    belief = BeliefSubmission(
        diagnoses=[DiagnosisBelief(condition_id=condition, rank=1, probability=1.0)],
        overall_confidence=0.9,
    )
    arena.submit_belief(session.session_id, belief, "persistent-belief")
    evidence = next(item for item in arena.available_actions(session.session_id).actions if item.dependency_met)
    arena.ask_evidence(session.session_id, evidence.evidence_id, "persistent-ask")
    completed = arena.finalize(session.session_id, belief, "persistent-final")
    assert replay_session(session.session_id, cases, repository).state_hash == completed.final_state_hash
    assert len(repository.events(session.session_id)) == 4
    assert len(repository.states(session.session_id)) == 2
    assert len(repository.beliefs(session.session_id)) == 2
