from __future__ import annotations

from datetime import datetime
from typing import Dict, Optional
from uuid import uuid4

from backend.app.domain.action import ClinicalAction, StepResult
from backend.app.domain.belief import BeliefSubmission
from backend.app.domain.enums import (
    ActionResultType,
    ActionType,
    ArenaMode,
    BeliefCaptureMode,
    SessionStatus,
)
from backend.app.domain.environment import (
    ClinicalEnvironment,
    DDXPlusEnvironment,
    FHIRClinicalEnvironment,
    SyntheaClinicalEnvironment,
)
from backend.app.domain.session import (
    BeliefSnapshot,
    Player,
    SessionEvent,
    SessionRecord,
    StateSnapshot,
    utc_now,
)
from backend.app.repositories.base import ArenaRepository
from backend.app.services.case_service import CaseService


class ArenaService:
    def __init__(self, cases: CaseService, repository: ArenaRepository) -> None:
        self.cases = cases
        self.repository = repository
        self._environments: Dict[str, ClinicalEnvironment] = {}

    def create_session(
        self,
        case_id: str,
        player: Player,
        arena_mode: ArenaMode = ArenaMode.FREE_EXPLORATION,
        belief_capture_mode: BeliefCaptureMode = BeliefCaptureMode.EVERY_STEP,
        random_seed: int = 0,
    ) -> SessionRecord:
        case = self.cases.get(case_id)
        session_id = str(uuid4())
        session = SessionRecord(
            session_id=session_id,
            case_id=case_id,
            case_hash=case.case_hash,
            player=player,
            arena_mode=arena_mode,
            belief_capture_mode=belief_capture_mode,
            dataset_version=case.dataset.dataset_version,
            case_version=case.dataset.case_manifest_version,
            arena_version="0.1.0",
            ui_version="0.1.0",
            random_seed=random_seed,
        )
        environment = self._new_environment(case_id)
        state = environment.reset(case_id)
        self._environments[session_id] = environment
        self.repository.add_session(session)
        self.repository.append_state(StateSnapshot(session_id=session_id, step=0, state=state))
        return session

    def get_session(self, session_id: str) -> SessionRecord:
        return self.repository.get_session(session_id)

    def state(self, session_id: str):
        self._assert_active_or_completed(session_id)
        return self._environment(session_id).get_state()

    def available_actions(self, session_id: str):
        session = self._assert_active(session_id)
        available = self._environment(session_id).get_available_actions()
        beliefs = self.repository.beliefs(session_id)
        if not beliefs:
            return available.model_copy(update={"actions": []})
        state = self.state(session_id)
        latest_conditions = [
            diagnosis.condition_id
            for diagnosis in beliefs[-1].belief.diagnoses
        ]
        relevance_hints = self.cases.question_scope(
            latest_conditions, state.initial_evidence_id, session.case_id
        )
        # DDXPlus case truth is dense across the complete 223-evidence
        # dictionary: asserted tokens resolve positively, while unasserted
        # root evidence resolves negatively (and inactive child attributes are
        # not applicable).  The Arena therefore exposes the whole unanswered
        # public catalog after a belief checkpoint instead of limiting the
        # clinician to findings suggested by the current differential.
        available = available.model_copy(
            update={
                "actions": [
                    item.model_copy(
                        update={
                            "suggested_by": relevance_hints.get(
                                item.evidence_id,
                                [
                                    "Full evidence catalog"
                                    if state.dataset_name == "DDXPlus"
                                    else "Case action space"
                                ],
                            )
                        }
                    )
                    for item in available.actions
                ]
            }
        )
        if session.arena_mode == ArenaMode.ANCHOR_STATE and state.question_count:
            return available.model_copy(update={"actions": []})
        if session.arena_mode == ArenaMode.LAYERED_EXPOSURE:
            eligible = [item for item in available.actions if item.dependency_met]
            if eligible:
                tier = min(
                    self.cases.catalog_for_case(session.case_id)[
                        item.evidence_id
                    ].exposure_tier
                    for item in eligible
                )
                return available.model_copy(
                    update={
                        "actions": [
                            item for item in eligible
                            if self.cases.catalog_for_case(session.case_id)[
                                item.evidence_id
                            ].exposure_tier
                            == tier
                        ]
                    }
                )
        return available

    def candidate_actions(self, session_id: str):
        """Return dependency-aware actions without the belief checkpoint gate.

        Model Arena uses this to ask for a belief and its following action in
        one structured response. ``ask_evidence`` still performs the canonical
        checkpoint and availability validation before mutating state.
        """
        self._assert_active(session_id)
        return self._environment(session_id).get_available_actions()

    def submit_belief(
        self,
        session_id: str,
        belief: BeliefSubmission,
        client_event_id: str,
        client_timestamp: Optional[datetime] = None,
        is_final: bool = False,
    ) -> BeliefSnapshot:
        self._assert_active(session_id)
        existing = self.repository.find_event(session_id, client_event_id)
        if existing:
            matches = [b for b in self.repository.beliefs(session_id) if b.belief_id == existing.action.get("belief_id")]
            if matches:
                return matches[0]
            raise ValueError("client_event_id was already used for another action")
        session = self.repository.get_session(session_id)
        unknown = sorted(
            {d.condition_id for d in belief.diagnoses}
            - set(self.cases.condition_catalog_for_case(session.case_id))
        )
        if unknown:
            raise ValueError(f"Unknown case outcomes: {', '.join(unknown)}")
        state = self.state(session_id)
        sequence = len(self.repository.events(session_id)) + 1
        snapshot = BeliefSnapshot(
            belief_id=str(uuid4()), session_id=session_id, step=state.question_count,
            state_hash=state.state_hash, belief=belief, is_final=is_final,
        )
        event = SessionEvent(
            event_id=str(uuid4()), session_id=session_id, sequence=sequence,
            event_type=ActionType.SUBMIT_BELIEF.value, client_event_id=client_event_id,
            action={"belief_id": snapshot.belief_id},
            state_before_hash=state.state_hash, state_after_hash=state.state_hash,
            client_timestamp=client_timestamp,
        )
        self.repository.append_event(event)
        self.repository.append_belief(snapshot)
        return snapshot

    def ask_evidence(
        self,
        session_id: str,
        evidence_id: str,
        client_event_id: str,
        client_timestamp: Optional[datetime] = None,
        latency_ms: Optional[int] = None,
    ) -> StepResult:
        session = self._assert_active(session_id)
        existing = self.repository.find_event(session_id, client_event_id)
        if existing:
            if existing.event_type != ActionType.ASK_EVIDENCE.value:
                raise ValueError("client_event_id was already used for another action")
            return self._result_from_event(existing)
        if not self.repository.beliefs(session_id):
            raise ValueError("An initial differential is required before asking evidence")
        state = self.state(session_id)
        if session.arena_mode == ArenaMode.ANCHOR_STATE and state.question_count:
            raise ValueError("Anchor-state sessions capture exactly one next-evidence choice")
        if session.belief_capture_mode == BeliefCaptureMode.EVERY_STEP:
            latest = self.repository.beliefs(session_id)[-1]
            if latest.step < state.question_count:
                raise ValueError("This protocol requires a belief update after every observation")
        scoped_ids = {
            item.evidence_id for item in self.available_actions(session_id).actions
        }
        if evidence_id not in scoped_ids:
            raise ValueError(
                "Evidence is unavailable, already revealed, or blocked by the session mode"
            )
        action = ClinicalAction(
            action_type=ActionType.ASK_EVIDENCE,
            evidence_id=evidence_id,
            client_event_id=client_event_id,
        )
        result = self._environment(session_id).step(action)
        event = SessionEvent(
            event_id=str(uuid4()), session_id=session_id,
            sequence=len(self.repository.events(session_id)) + 1,
            event_type=ActionType.ASK_EVIDENCE.value,
            client_event_id=client_event_id,
            action=action.model_dump(mode="json"),
            observation=result.observation.model_dump(mode="json") if result.observation else None,
            state_before_hash=result.state_before_hash,
            state_after_hash=result.state_after_hash,
            client_timestamp=client_timestamp,
            latency_ms=latency_ms,
            result_type=result.result_type.value,
        )
        self.repository.append_event(event)
        if result.state_after_hash != result.state_before_hash:
            self.repository.append_state(
                StateSnapshot(
                    session_id=session_id,
                    step=result.state.question_count,
                    state=result.state,
                )
            )
        return result

    def finalize(
        self,
        session_id: str,
        belief: BeliefSubmission,
        client_event_id: str,
    ) -> SessionRecord:
        session = self._assert_active(session_id)
        existing = self.repository.find_event(session_id, client_event_id)
        if existing:
            return self.repository.get_session(session_id)
        snapshot = self.submit_belief(
            session_id, belief, f"{client_event_id}:belief", is_final=True
        )
        state = self._environment(session_id).finalize()
        event = SessionEvent(
            event_id=str(uuid4()), session_id=session_id,
            sequence=len(self.repository.events(session_id)) + 1,
            event_type=ActionType.FINAL_DIAGNOSIS.value,
            client_event_id=client_event_id,
            action={"belief_id": snapshot.belief_id},
            state_before_hash=state.state_hash,
            state_after_hash=state.state_hash,
        )
        self.repository.append_event(event)
        completed = session.model_copy(
            update={
                "status": SessionStatus.COMPLETED,
                "completed_at": utc_now(),
                "final_state_hash": state.state_hash,
            }
        )
        self.repository.update_session(completed)
        return completed

    def _environment(self, session_id: str) -> ClinicalEnvironment:
        if session_id in self._environments:
            return self._environments[session_id]
        # Rehydrate a development process from its append-only event history.
        session = self.repository.get_session(session_id)
        environment = self._new_environment(session.case_id)
        environment.reset(session.case_id)
        for event in self.repository.events(session_id):
            if event.event_type == ActionType.ASK_EVIDENCE.value:
                environment.step(ClinicalAction.model_validate(event.action))
        if session.status == SessionStatus.COMPLETED:
            environment.finalize()
        self._environments[session_id] = environment
        return environment

    def _new_environment(self, case_id: str) -> ClinicalEnvironment:
        bundle = self.cases.get(case_id)
        environment_type: type[DDXPlusEnvironment]
        if bundle.dataset.name == "Synthea":
            environment_type = SyntheaClinicalEnvironment
        elif bundle.dataset.name == "MedAgentBench":
            environment_type = FHIRClinicalEnvironment
        else:
            environment_type = DDXPlusEnvironment
        return environment_type(
            self.cases.cases,
            self.cases.catalog_for_case(case_id),
        )

    def _assert_active(self, session_id: str) -> SessionRecord:
        session = self.repository.get_session(session_id)
        if session.status != SessionStatus.ACTIVE:
            raise ValueError("Session is not active")
        return session

    def _assert_active_or_completed(self, session_id: str) -> SessionRecord:
        session = self.repository.get_session(session_id)
        if session.status not in {SessionStatus.ACTIVE, SessionStatus.COMPLETED}:
            raise ValueError("Session cannot be read")
        return session

    def _result_from_event(self, event: SessionEvent) -> StepResult:
        state = self.state(event.session_id)
        observation = None
        if event.observation:
            from backend.app.domain.evidence import EvidenceResponse
            observation = EvidenceResponse.model_validate(event.observation)
        return StepResult(
            result_type=ActionResultType(event.result_type),
            action=ClinicalAction.model_validate(event.action),
            observation=observation,
            state_before_hash=event.state_before_hash,
            state_after_hash=event.state_after_hash,
            state=state,
            message="Idempotent replay of an existing action",
        )
