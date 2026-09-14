from __future__ import annotations

from collections import defaultdict
from threading import RLock
from typing import Dict, List, Optional

from backend.app.domain.account import AuthSession, PhysicianAccount
from backend.app.domain.session import (
    BeliefSnapshot,
    SessionEvent,
    SessionRecord,
    StateSnapshot,
)
from backend.app.domain.model_run import ModelInteractionRecord, ModelRunRecord


class InMemoryArenaRepository:
    """Development repository with the same append-only semantics as PostgreSQL."""

    def __init__(self) -> None:
        self._accounts: Dict[str, PhysicianAccount] = {}
        self._auth_sessions: Dict[str, AuthSession] = {}
        self._sessions: Dict[str, SessionRecord] = {}
        self._events: Dict[str, List[SessionEvent]] = defaultdict(list)
        self._states: Dict[str, List[StateSnapshot]] = defaultdict(list)
        self._beliefs: Dict[str, List[BeliefSnapshot]] = defaultdict(list)
        self._event_ids: Dict[str, Dict[str, SessionEvent]] = defaultdict(dict)
        self._model_runs: Dict[str, ModelRunRecord] = {}
        self._model_interactions: Dict[str, List[ModelInteractionRecord]] = defaultdict(list)
        self._lock = RLock()

    def add_account(self, account: PhysicianAccount) -> None:
        with self._lock:
            if account.username in self._accounts:
                raise ValueError("Account already exists")
            self._accounts[account.username] = account.model_copy(deep=True)

    def get_account(self, username: str) -> Optional[PhysicianAccount]:
        with self._lock:
            account = self._accounts.get(username)
            return account.model_copy(deep=True) if account else None

    def all_accounts(self) -> List[PhysicianAccount]:
        with self._lock:
            return [item.model_copy(deep=True) for item in self._accounts.values()]

    def delete_account(self, username: str) -> None:
        with self._lock:
            if any(
                session.player.player_id == username
                for session in self._sessions.values()
            ):
                raise ValueError("Accounts with Arena sessions cannot be deleted")
            self._accounts.pop(username, None)
            self._auth_sessions = {
                token: session
                for token, session in self._auth_sessions.items()
                if session.username != username
            }

    def add_auth_session(self, session: AuthSession) -> None:
        with self._lock:
            self._auth_sessions[session.token] = session.model_copy(deep=True)

    def get_auth_session(self, token: str) -> Optional[AuthSession]:
        with self._lock:
            session = self._auth_sessions.get(token)
            return session.model_copy(deep=True) if session else None

    def delete_auth_session(self, token: str) -> None:
        with self._lock:
            self._auth_sessions.pop(token, None)

    def add_session(self, session: SessionRecord) -> None:
        with self._lock:
            if session.session_id in self._sessions:
                raise ValueError("Session already exists")
            self._sessions[session.session_id] = session.model_copy(deep=True)

    def get_session(self, session_id: str) -> SessionRecord:
        with self._lock:
            try:
                return self._sessions[session_id].model_copy(deep=True)
            except KeyError as exc:
                raise KeyError(f"Unknown session: {session_id}") from exc

    def update_session(self, session: SessionRecord) -> None:
        with self._lock:
            if session.session_id not in self._sessions:
                raise KeyError(f"Unknown session: {session.session_id}")
            self._sessions[session.session_id] = session.model_copy(deep=True)

    def append_event(self, event: SessionEvent) -> None:
        with self._lock:
            if event.client_event_id in self._event_ids[event.session_id]:
                raise ValueError("Duplicate client_event_id")
            expected = len(self._events[event.session_id]) + 1
            if event.sequence != expected:
                raise ValueError(f"Expected event sequence {expected}")
            stored = event.model_copy(deep=True)
            self._events[event.session_id].append(stored)
            self._event_ids[event.session_id][event.client_event_id] = stored

    def events(self, session_id: str) -> List[SessionEvent]:
        return [item.model_copy(deep=True) for item in self._events[session_id]]

    def find_event(
        self, session_id: str, client_event_id: str
    ) -> Optional[SessionEvent]:
        item = self._event_ids[session_id].get(client_event_id)
        return item.model_copy(deep=True) if item else None

    def append_state(self, state: StateSnapshot) -> None:
        with self._lock:
            self._states[state.session_id].append(state.model_copy(deep=True))

    def states(self, session_id: str) -> List[StateSnapshot]:
        return [item.model_copy(deep=True) for item in self._states[session_id]]

    def append_belief(self, belief: BeliefSnapshot) -> None:
        with self._lock:
            self._beliefs[belief.session_id].append(belief.model_copy(deep=True))

    def beliefs(self, session_id: str) -> List[BeliefSnapshot]:
        return [item.model_copy(deep=True) for item in self._beliefs[session_id]]

    def all_sessions(self) -> List[SessionRecord]:
        return [item.model_copy(deep=True) for item in self._sessions.values()]

    def add_model_run(self, run: ModelRunRecord) -> None:
        with self._lock:
            if run.run_id in self._model_runs:
                raise ValueError("Model run already exists")
            self._model_runs[run.run_id] = run.model_copy(deep=True)

    def get_model_run(self, run_id: str) -> ModelRunRecord:
        with self._lock:
            try:
                return self._model_runs[run_id].model_copy(deep=True)
            except KeyError as exc:
                raise KeyError(f"Unknown model run: {run_id}") from exc

    def update_model_run(self, run: ModelRunRecord) -> None:
        with self._lock:
            if run.run_id not in self._model_runs:
                raise KeyError(f"Unknown model run: {run.run_id}")
            self._model_runs[run.run_id] = run.model_copy(deep=True)

    def all_model_runs(self) -> List[ModelRunRecord]:
        with self._lock:
            return [item.model_copy(deep=True) for item in self._model_runs.values()]

    def append_model_interaction(self, interaction: ModelInteractionRecord) -> None:
        with self._lock:
            self._model_interactions[interaction.run_id].append(
                interaction.model_copy(deep=True)
            )

    def model_interactions(self, run_id: str) -> List[ModelInteractionRecord]:
        with self._lock:
            return [
                item.model_copy(deep=True)
                for item in self._model_interactions[run_id]
            ]
