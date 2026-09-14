from __future__ import annotations

from collections import defaultdict
from typing import List, Optional

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session, sessionmaker

from backend.app.db import models as db
from backend.app.domain.account import AuthSession, PhysicianAccount
from backend.app.domain.belief import BeliefSubmission, DiagnosisBelief
from backend.app.domain.enums import (
    ArenaMode,
    BeliefCaptureMode,
    PlayerType,
    SessionStatus,
)
from backend.app.domain.session import (
    BeliefSnapshot,
    Player,
    SessionEvent,
    SessionRecord,
    StateSnapshot,
)
from backend.app.domain.model_run import ModelInteractionRecord, ModelRunRecord
from backend.app.domain.state import ObservationState


class SqlAlchemyArenaRepository:
    """Persistent PostgreSQL repository preserving append-only event semantics."""

    def __init__(self, session_factory: sessionmaker[Session]) -> None:
        self.session_factory = session_factory

    def add_account(self, account: PhysicianAccount) -> None:
        with self.session_factory.begin() as database:
            if database.get(db.PhysicianAccount, account.username):
                raise ValueError("Account already exists")
            database.add(
                db.PhysicianAccount(**account.model_dump(mode="python"))
            )

    def get_account(self, username: str) -> Optional[PhysicianAccount]:
        with self.session_factory() as database:
            row = database.get(db.PhysicianAccount, username)
            if row is None:
                return None
            return PhysicianAccount(
                username=row.username,
                password_plaintext=row.password_plaintext,
                created_at=row.created_at,
            )

    def all_accounts(self) -> List[PhysicianAccount]:
        with self.session_factory() as database:
            rows = database.scalars(
                select(db.PhysicianAccount).order_by(db.PhysicianAccount.created_at)
            ).all()
            return [
                PhysicianAccount(
                    username=row.username,
                    password_plaintext=row.password_plaintext,
                    created_at=row.created_at,
                )
                for row in rows
            ]

    def delete_account(self, username: str) -> None:
        with self.session_factory.begin() as database:
            session_count = database.scalar(
                select(func.count())
                .select_from(db.ArenaSession)
                .where(db.ArenaSession.player_id == username)
            )
            if session_count:
                raise ValueError("Accounts with Arena sessions cannot be deleted")
            database.execute(
                delete(db.AuthSession).where(db.AuthSession.username == username)
            )
            account = database.get(db.PhysicianAccount, username)
            if account is not None:
                database.delete(account)

    def add_auth_session(self, session: AuthSession) -> None:
        with self.session_factory.begin() as database:
            database.add(db.AuthSession(**session.model_dump(mode="python")))

    def get_auth_session(self, token: str) -> Optional[AuthSession]:
        with self.session_factory() as database:
            row = database.get(db.AuthSession, token)
            if row is None:
                return None
            return AuthSession(
                token=row.token,
                username=row.username,
                created_at=row.created_at,
            )

    def delete_auth_session(self, token: str) -> None:
        with self.session_factory.begin() as database:
            row = database.get(db.AuthSession, token)
            if row is not None:
                database.delete(row)

    def add_session(self, session: SessionRecord) -> None:
        with self.session_factory.begin() as database:
            player = database.get(db.Player, session.player.player_id)
            if player is None:
                database.add(
                    db.Player(
                        player_id=session.player.player_id,
                        player_type=session.player.player_type.value,
                        specialty=session.player.specialty,
                        training_level=session.player.training_level,
                        years_experience=session.player.years_experience,
                        site=session.player.site,
                        country=session.player.country,
                        model_metadata=session.player.model_metadata,
                    )
                )
            database.add(
                db.ArenaSession(
                    session_id=session.session_id,
                    case_id=session.case_id,
                    case_hash=session.case_hash,
                    player_id=session.player.player_id,
                    arena_mode=session.arena_mode.value,
                    belief_capture_mode=session.belief_capture_mode.value,
                    started_at=session.started_at,
                    completed_at=session.completed_at,
                    dataset_version=session.dataset_version,
                    case_version=session.case_version,
                    arena_version=session.arena_version,
                    ui_version=session.ui_version,
                    random_seed=session.random_seed,
                    status=session.status.value,
                    final_state_hash=session.final_state_hash,
                )
            )

    def get_session(self, session_id: str) -> SessionRecord:
        with self.session_factory() as database:
            row = database.get(db.ArenaSession, session_id)
            if row is None:
                raise KeyError(f"Unknown session: {session_id}")
            player = database.get(db.Player, row.player_id)
            return self._session_record(row, player)

    def update_session(self, session: SessionRecord) -> None:
        with self.session_factory.begin() as database:
            row = database.get(db.ArenaSession, session.session_id)
            if row is None:
                raise KeyError(f"Unknown session: {session.session_id}")
            row.status = session.status.value
            row.completed_at = session.completed_at
            row.final_state_hash = session.final_state_hash

    def append_event(self, event: SessionEvent) -> None:
        with self.session_factory.begin() as database:
            database.add(db.SessionEvent(**event.model_dump(mode="python")))

    def events(self, session_id: str) -> List[SessionEvent]:
        with self.session_factory() as database:
            rows = database.scalars(
                select(db.SessionEvent)
                .where(db.SessionEvent.session_id == session_id)
                .order_by(db.SessionEvent.sequence)
            ).all()
            return [
                SessionEvent(
                    event_id=row.event_id,
                    session_id=row.session_id,
                    sequence=row.sequence,
                    event_type=row.event_type,
                    client_event_id=row.client_event_id,
                    action=row.action,
                    observation=row.observation,
                    state_before_hash=row.state_before_hash,
                    state_after_hash=row.state_after_hash,
                    server_timestamp=row.server_timestamp,
                    client_timestamp=row.client_timestamp,
                    latency_ms=row.latency_ms,
                    schema_version=row.schema_version,
                    result_type=row.result_type,
                )
                for row in rows
            ]

    def find_event(self, session_id: str, client_event_id: str) -> Optional[SessionEvent]:
        with self.session_factory() as database:
            row = database.scalar(
                select(db.SessionEvent).where(
                    db.SessionEvent.session_id == session_id,
                    db.SessionEvent.client_event_id == client_event_id,
                )
            )
            if row is None:
                return None
        return next(
            event for event in self.events(session_id)
            if event.client_event_id == client_event_id
        )

    def append_state(self, state: StateSnapshot) -> None:
        payload = state.state.model_dump(mode="json")
        with self.session_factory.begin() as database:
            database.add(
                db.StateSnapshot(
                    session_id=state.session_id,
                    step=state.step,
                    state_hash=state.state.state_hash,
                    revealed_evidence_ids=sorted(state.state.revealed),
                    revealed_evidence_values={
                        key: value.model_dump(mode="json")
                        for key, value in state.state.revealed.items()
                    },
                    state_payload=payload,
                    created_at=state.created_at,
                )
            )

    def states(self, session_id: str) -> List[StateSnapshot]:
        with self.session_factory() as database:
            rows = database.scalars(
                select(db.StateSnapshot)
                .where(db.StateSnapshot.session_id == session_id)
                .order_by(db.StateSnapshot.step)
            ).all()
            return [
                StateSnapshot(
                    session_id=row.session_id,
                    step=row.step,
                    state=ObservationState.model_validate(row.state_payload),
                    created_at=row.created_at,
                )
                for row in rows
            ]

    def append_belief(self, belief: BeliefSnapshot) -> None:
        with self.session_factory.begin() as database:
            for diagnosis in belief.belief.diagnoses:
                database.add(
                    db.BeliefSnapshot(
                        belief_id=belief.belief_id,
                        session_id=belief.session_id,
                        step=belief.step,
                        state_hash=belief.state_hash,
                        diagnosis_id=diagnosis.condition_id,
                        rank=diagnosis.rank,
                        probability=diagnosis.probability,
                        overall_confidence=belief.belief.overall_confidence,
                        is_final=belief.is_final,
                        timestamp=belief.timestamp,
                    )
                )

    def beliefs(self, session_id: str) -> List[BeliefSnapshot]:
        with self.session_factory() as database:
            rows = database.scalars(
                select(db.BeliefSnapshot)
                .where(db.BeliefSnapshot.session_id == session_id)
                .order_by(db.BeliefSnapshot.timestamp, db.BeliefSnapshot.rank)
            ).all()
            groups = defaultdict(list)
            for row in rows:
                groups[row.belief_id].append(row)
            return [
                BeliefSnapshot(
                    belief_id=belief_id,
                    session_id=group[0].session_id,
                    step=group[0].step,
                    state_hash=group[0].state_hash,
                    belief=BeliefSubmission(
                        diagnoses=[
                            DiagnosisBelief(
                                condition_id=row.diagnosis_id,
                                rank=row.rank,
                                probability=row.probability,
                            )
                            for row in group
                        ],
                        overall_confidence=group[0].overall_confidence,
                    ),
                    is_final=group[0].is_final,
                    timestamp=group[0].timestamp,
                )
                for belief_id, group in groups.items()
            ]

    def all_sessions(self) -> List[SessionRecord]:
        with self.session_factory() as database:
            rows = database.scalars(select(db.ArenaSession)).all()
            players = {
                row.player_id: database.get(db.Player, row.player_id) for row in rows
            }
            return [self._session_record(row, players[row.player_id]) for row in rows]

    def add_model_run(self, run: ModelRunRecord) -> None:
        with self.session_factory.begin() as database:
            database.add(db.ModelArenaRun(**run.model_dump(mode="python")))

    def get_model_run(self, run_id: str) -> ModelRunRecord:
        with self.session_factory() as database:
            row = database.get(db.ModelArenaRun, run_id)
            if row is None:
                raise KeyError(f"Unknown model run: {run_id}")
            return self._model_run_record(row)

    def update_model_run(self, run: ModelRunRecord) -> None:
        with self.session_factory.begin() as database:
            row = database.get(db.ModelArenaRun, run.run_id)
            if row is None:
                raise KeyError(f"Unknown model run: {run.run_id}")
            row.status = run.status
            row.forced_final = run.forced_final
            row.last_error = run.last_error
            row.completed_at = run.completed_at

    def all_model_runs(self) -> List[ModelRunRecord]:
        with self.session_factory() as database:
            rows = database.scalars(
                select(db.ModelArenaRun).order_by(db.ModelArenaRun.created_at.desc())
            ).all()
            return [self._model_run_record(row) for row in rows]

    def append_model_interaction(self, interaction: ModelInteractionRecord) -> None:
        with self.session_factory.begin() as database:
            database.add(
                db.ModelInteraction(**interaction.model_dump(mode="python"))
            )

    def model_interactions(self, run_id: str) -> List[ModelInteractionRecord]:
        with self.session_factory() as database:
            rows = database.scalars(
                select(db.ModelInteraction)
                .where(db.ModelInteraction.run_id == run_id)
                .order_by(db.ModelInteraction.step)
            ).all()
            return [
                ModelInteractionRecord(
                    interaction_id=row.interaction_id,
                    run_id=row.run_id,
                    step=row.step,
                    request_payload=row.request_payload,
                    response_payload=row.response_payload,
                    assistant_content=row.assistant_content,
                    parsed_decision=row.parsed_decision,
                    application_result=row.application_result,
                    error=row.error,
                    latency_ms=row.latency_ms,
                    created_at=row.created_at,
                )
                for row in rows
            ]

    @staticmethod
    def _session_record(row: db.ArenaSession, player: db.Player) -> SessionRecord:
        return SessionRecord(
            session_id=row.session_id,
            case_id=row.case_id,
            case_hash=row.case_hash,
            player=Player(
                player_id=player.player_id,
                player_type=PlayerType(player.player_type),
                specialty=player.specialty,
                training_level=player.training_level,
                years_experience=player.years_experience,
                site=player.site,
                country=player.country,
                model_metadata=player.model_metadata,
            ),
            arena_mode=ArenaMode(row.arena_mode),
            belief_capture_mode=BeliefCaptureMode(row.belief_capture_mode),
            dataset_version=row.dataset_version,
            case_version=row.case_version,
            arena_version=row.arena_version,
            ui_version=row.ui_version,
            random_seed=row.random_seed,
            status=SessionStatus(row.status),
            started_at=row.started_at,
            completed_at=row.completed_at,
            final_state_hash=row.final_state_hash,
        )

    @staticmethod
    def _model_run_record(row: db.ModelArenaRun) -> ModelRunRecord:
        return ModelRunRecord(
            run_id=row.run_id,
            session_id=row.session_id,
            model_id=row.model_id,
            provider=row.provider,
            case_id=row.case_id,
            dataset_name=row.dataset_name,
            status=row.status,
            max_questions=row.max_questions,
            forced_final=row.forced_final,
            last_error=row.last_error,
            created_at=row.created_at,
            completed_at=row.completed_at,
        )
