from __future__ import annotations

from backend.app.domain.action import ClinicalAction
from backend.app.domain.enums import ActionType
from backend.app.domain.environment import (
    DDXPlusEnvironment,
    FHIRClinicalEnvironment,
    SyntheaClinicalEnvironment,
)
from backend.app.repositories.base import ArenaRepository
from backend.app.services.case_service import CaseService


def replay_session(session_id: str, cases: CaseService, repository: ArenaRepository):
    session = repository.get_session(session_id)
    bundle = cases.get(session.case_id)
    environment_type = (
        SyntheaClinicalEnvironment
        if bundle.dataset.name == "Synthea"
        else FHIRClinicalEnvironment
        if bundle.dataset.name == "MedAgentBench"
        else DDXPlusEnvironment
    )
    environment = environment_type(
        cases.cases, cases.catalog_for_case(session.case_id)
    )
    environment.reset(session.case_id)
    for event in repository.events(session_id):
        if event.event_type != ActionType.ASK_EVIDENCE.value:
            continue
        result = environment.step(ClinicalAction.model_validate(event.action))
        if result.state_after_hash != event.state_after_hash:
            raise AssertionError(
                f"Replay diverged at sequence {event.sequence}: "
                f"{result.state_after_hash} != {event.state_after_hash}"
            )
    state = environment.get_state()
    if session.final_state_hash and state.state_hash != session.final_state_hash:
        raise AssertionError("Replayed final state hash does not match session")
    return state
