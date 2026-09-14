from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Dict

from .action import AvailableAction, AvailableActions, ClinicalAction, StepResult
from .case import CaseBundle
from .enums import ActionResultType, ActionType, SessionStatus, TruthStatus
from .evidence import EvidenceDefinition, EvidenceResponse, human_readable_response
from .state import ObservationState


class ClinicalEnvironment(ABC):
    @abstractmethod
    def reset(self, case_id: str) -> ObservationState:
        raise NotImplementedError

    @abstractmethod
    def get_state(self) -> ObservationState:
        raise NotImplementedError

    @abstractmethod
    def get_available_actions(self) -> AvailableActions:
        raise NotImplementedError

    @abstractmethod
    def step(self, action: ClinicalAction) -> StepResult:
        raise NotImplementedError

    @abstractmethod
    def finalize(self) -> ObservationState:
        raise NotImplementedError


class DDXPlusEnvironment(ClinicalEnvironment):
    """Deterministic, partially observable DDXPlus environment."""

    def __init__(
        self,
        cases: Dict[str, CaseBundle],
        evidence_catalog: Dict[str, EvidenceDefinition],
    ):
        self._cases = cases
        self._catalog = evidence_catalog
        self._case: CaseBundle | None = None
        self._state: ObservationState | None = None
        self.status = SessionStatus.READY

    def reset(self, case_id: str) -> ObservationState:
        if case_id not in self._cases:
            raise KeyError(f"Unknown case: {case_id}")
        self._case = self._cases[case_id]
        initial = self._case.initial_evidence
        self._state = ObservationState(
            case_id=case_id,
            age=self._case.demographics.age,
            sex=self._case.demographics.sex,
            dataset_name=self._case.dataset.name,
            case_type=self._case.case_type,
            generation_mode=self._case.generation_mode,
            initial_context=self._case.initial_context,
            initial_evidence_id=initial.evidence_id,
            initial_evidence_question=self._catalog[initial.evidence_id].question_en,
            initial_evidence_answer=human_readable_response(
                initial, self._catalog[initial.evidence_id]
            ),
            revealed={initial.evidence_id: initial},
        ).refreshed()
        self.status = SessionStatus.ACTIVE
        return self._state.model_copy(deep=True)

    def get_state(self) -> ObservationState:
        if self._state is None:
            raise RuntimeError("Environment has not been reset")
        return self._state.model_copy(deep=True)

    def get_available_actions(self) -> AvailableActions:
        state = self.get_state()
        actions = []
        for evidence_id, definition in sorted(self._catalog.items()):
            if evidence_id in state.revealed:
                continue
            parent_id = definition.parent_evidence_id
            dependency_met = parent_id is None or parent_id in state.revealed
            actions.append(
                AvailableAction(
                    action_type=ActionType.ASK_EVIDENCE,
                    evidence_id=evidence_id,
                    question_en=definition.question_en,
                    dependency_met=dependency_met,
                    semantic_role=definition.semantic_role,
                    clinical_domain=definition.clinical_domain or (
                        "ANTECEDENT" if definition.is_antecedent else "SYMPTOM"
                    ),
                    data_type=definition.data_type.value,
                    exposure_tier=definition.exposure_tier,
                    parent_evidence_id=parent_id,
                    parent_question_en=(
                        self._catalog[parent_id].question_en if parent_id else None
                    ),
                    action_kind=definition.action_kind,
                    resource_type=definition.resource_type,
                    mutates_state=definition.mutates_state,
                )
            )
        return AvailableActions(actions=actions)

    def step(self, action: ClinicalAction) -> StepResult:
        if self.status != SessionStatus.ACTIVE or self._case is None:
            raise RuntimeError("Environment is not active")
        state = self.get_state()
        before = state.state_hash

        if action.action_type != ActionType.ASK_EVIDENCE or not action.evidence_id:
            return StepResult(
                result_type=ActionResultType.INVALID_ACTION,
                action=action,
                state_before_hash=before,
                state_after_hash=before,
                state=state,
                message="Only ASK_EVIDENCE changes observation state",
            )
        if action.evidence_id not in self._catalog:
            return StepResult(
                result_type=ActionResultType.INVALID_ACTION,
                action=action,
                state_before_hash=before,
                state_after_hash=before,
                state=state,
                message="Unknown evidence",
            )
        if action.evidence_id in state.revealed:
            return StepResult(
                result_type=ActionResultType.REPEATED_QUERY,
                action=action,
                observation=state.revealed[action.evidence_id],
                state_before_hash=before,
                state_after_hash=before,
                state=state,
                message="Evidence was already revealed",
            )

        definition = self._catalog[action.evidence_id]
        parent_id = definition.parent_evidence_id
        if parent_id and parent_id not in state.revealed:
            return StepResult(
                result_type=ActionResultType.DEPENDENCY_NOT_MET,
                action=action,
                state_before_hash=before,
                state_after_hash=before,
                state=state,
                message=f"Ask parent evidence {parent_id} first",
            )

        truth = self._case.truth_map()[action.evidence_id]
        if parent_id:
            parent = state.revealed[parent_id]
            if parent.status not in {TruthStatus.PRESENT, TruthStatus.VALUE}:
                truth = EvidenceResponse(
                    evidence_id=action.evidence_id,
                    status=TruthStatus.NOT_APPLICABLE,
                    data_type=definition.data_type,
                )

        state.revealed[action.evidence_id] = truth
        state.question_count += 1
        state = state.refreshed()
        self._state = state
        return StepResult(
            result_type=ActionResultType.OBSERVATION,
            action=action,
            observation=truth,
            state_before_hash=before,
            state_after_hash=state.state_hash,
            state=state.model_copy(deep=True),
        )

    def finalize(self) -> ObservationState:
        state = self.get_state()
        self.status = SessionStatus.COMPLETED
        return state


class SyntheaClinicalEnvironment(DDXPlusEnvironment):
    """Encounter-scoped Synthea evidence-review environment.

    The deterministic response comes from the source CSV record attached to
    the case.  It does not reinterpret a procedure as a narrative report.
    """


class FHIRClinicalEnvironment(DDXPlusEnvironment):
    """FHIR-compatible workflow environment with explicit offline semantics.

    Guidance2 MVP cases use ``OFFLINE_TASK_REPLAY`` and therefore have no
    mutating definitions.  The created-resource portion of state hashing is
    implemented here so a future live adapter can record real POST results
    without changing the Arena event contract.
    """

    def step(self, action: ClinicalAction) -> StepResult:
        result = super().step(action)
        if (
            result.result_type == ActionResultType.OBSERVATION
            and action.evidence_id
            and self._catalog[action.evidence_id].mutates_state
        ):
            state = result.state.model_copy(deep=True)
            resource_id = f"{self._catalog[action.evidence_id].resource_type or 'Resource'}/{action.evidence_id}"
            if resource_id not in state.created_resource_ids:
                state.created_resource_ids.append(resource_id)
            state = state.refreshed()
            self._state = state
            return result.model_copy(
                update={"state": state, "state_after_hash": state.state_hash}
            )
        return result
