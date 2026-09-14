from backend.app.domain.action import ClinicalAction
from backend.app.domain.enums import ActionType, TruthStatus
from backend.app.domain.environment import DDXPlusEnvironment


def test_canonical_state_hash_is_order_independent(cases):
    case_id = cases.case_ids()[0]
    available = [
        item for item in cases.evidence_catalog.values()
        if item.parent_evidence_id is None and item.evidence_id != cases.get(case_id).initial_evidence.evidence_id
    ][:2]
    first = DDXPlusEnvironment(cases.cases, cases.evidence_catalog)
    second = DDXPlusEnvironment(cases.cases, cases.evidence_catalog)
    first.reset(case_id)
    second.reset(case_id)
    first.step(ClinicalAction(action_type=ActionType.ASK_EVIDENCE, evidence_id=available[0].evidence_id, client_event_id="a"))
    first.step(ClinicalAction(action_type=ActionType.ASK_EVIDENCE, evidence_id=available[1].evidence_id, client_event_id="b"))
    second.step(ClinicalAction(action_type=ActionType.ASK_EVIDENCE, evidence_id=available[1].evidence_id, client_event_id="c"))
    second.step(ClinicalAction(action_type=ActionType.ASK_EVIDENCE, evidence_id=available[0].evidence_id, client_event_id="d"))
    assert first.get_state().state_hash == second.get_state().state_hash


def test_response_is_deterministic(cases):
    case_id = cases.case_ids()[0]
    evidence_id = next(key for key, value in cases.evidence_catalog.items() if value.parent_evidence_id is None and key != cases.get(case_id).initial_evidence.evidence_id)
    answers = []
    for suffix in ("a", "b"):
        environment = DDXPlusEnvironment(cases.cases, cases.evidence_catalog)
        environment.reset(case_id)
        answers.append(environment.step(ClinicalAction(action_type=ActionType.ASK_EVIDENCE, evidence_id=evidence_id, client_event_id=suffix)).observation)
    assert answers[0] == answers[1]

