from backend.app.domain.enums import ActionType
from backend.app.domain.action import ClinicalAction
from backend.app.domain.environment import (
    FHIRClinicalEnvironment,
    SyntheaClinicalEnvironment,
)
from fastapi.testclient import TestClient

from backend.app.main import create_app


def test_guidance2_case_counts_and_native_semantics(cases):
    synthea = [item for item in cases.cases.values() if item.dataset.name == "Synthea"]
    medagent = [
        item for item in cases.cases.values() if item.dataset.name == "MedAgentBench"
    ]
    assert len(synthea) == 50
    assert len(medagent) == 30
    assert all(item.case_type == "DIAGNOSTIC_EVIDENCE_ACQUISITION" for item in synthea)
    assert all(item.generation_mode == "NATURAL_CSV_EXPORT" for item in synthea)
    assert all(item.case_type == "WORKFLOW_FOREST" for item in medagent)
    assert all(item.generation_mode == "OFFLINE_TASK_REPLAY" for item in medagent)
    assert all("does not fabricate" in item.fidelity_note for item in medagent)


def test_synthea_and_medagent_environments_reveal_case_local_actions(cases):
    for dataset_name, environment_type in (
        ("Synthea", SyntheaClinicalEnvironment),
        ("MedAgentBench", FHIRClinicalEnvironment),
    ):
        bundle = next(
            item for item in cases.cases.values() if item.dataset.name == dataset_name
        )
        catalog = cases.catalog_for_case(bundle.case_id)
        environment = environment_type(cases.cases, catalog)
        state = environment.reset(bundle.case_id)
        assert state.dataset_name == dataset_name
        action = next(
            item for item in environment.get_available_actions().actions
            if item.dependency_met
        )
        result = environment.step(
            ClinicalAction(
                action_type=ActionType.ASK_EVIDENCE,
                evidence_id=action.evidence_id,
                client_event_id="native-action",
            )
        )
        assert result.observation == bundle.truth_map()[action.evidence_id]
        if dataset_name == "MedAgentBench":
            assert result.state.created_resource_ids == []


def test_case_tree_audits_cover_new_tracks(cases):
    from backend.app.services.case_tree_service import CaseTreeService

    service = CaseTreeService(cases.root)
    for case_id in ("SYN_ENC_0001", "MAB_TASK4_1", "MAB_TASK5_1", "MAB_TASK8_1"):
        audit = service.get(case_id)
        assert audit["processed_tree"]["case_id"] == case_id
        assert all(audit["processed_tree"]["audit"]["checks"].values())


def test_guidance2_tracks_use_the_complete_arena_lifecycle(cases):
    client = TestClient(create_app(cases))
    auth = client.post(
        "/auth/register",
        json={"username": "guidance2-doctor", "password": "test-password"},
    ).json()
    client.headers["Authorization"] = f"Bearer {auth['token']}"
    for case_id in ("SYN_ENC_0001", "MAB_TASK4_1"):
        catalog = client.get(f"/cases/{case_id}/catalog").json()
        outcome = catalog["conditions"][0]["condition_id"]
        belief = {
            "diagnoses": [
                {"condition_id": outcome, "rank": 1, "probability": 1.0}
            ],
            "overall_confidence": 0,
        }
        created = client.post("/sessions", json={"case_id": case_id}).json()
        session_id = created["session"]["session_id"]
        assert created["state"]["dataset_name"] in {"Synthea", "MedAgentBench"}
        assert client.post(
            f"/sessions/{session_id}/beliefs",
            json={"belief": belief, "client_event_id": f"{case_id}-s0"},
        ).status_code == 201
        action = client.get(
            f"/sessions/{session_id}/available-evidences"
        ).json()["actions"][0]
        observed = client.post(
            f"/sessions/{session_id}/actions/evidence",
            json={
                "evidence_id": action["evidence_id"],
                "client_event_id": f"{case_id}-action",
            },
        )
        assert observed.status_code == 200
        assert observed.json()["answer_text"]
        if case_id.startswith("MAB_"):
            assert observed.json()["state"]["created_resource_ids"] == []
        assert client.post(
            f"/sessions/{session_id}/beliefs",
            json={"belief": belief, "client_event_id": f"{case_id}-s1"},
        ).status_code == 201
        assert client.post(
            f"/sessions/{session_id}/finalize",
            json={"belief": belief, "client_event_id": f"{case_id}-final"},
        ).status_code == 200
        review = client.get(f"/sessions/{session_id}/review").json()
        assert review["ground_truth_tree"]["case_id"] == case_id
        assert review["case_type"] in {
            "DIAGNOSTIC_EVIDENCE_ACQUISITION",
            "WORKFLOW_FOREST",
        }
