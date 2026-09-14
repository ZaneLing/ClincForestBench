import json

from fastapi.testclient import TestClient

from backend.app.main import create_app


def authenticated_client(app, username="doctor"):
    client = TestClient(app)
    response = client.post(
        "/auth/register",
        json={"username": username, "password": "test-password"},
    )
    assert response.status_code == 201
    client.headers["Authorization"] = f"Bearer {response.json()['token']}"
    return client


def test_active_api_oracle_isolation_and_research_auth(cases):
    app = create_app(cases)
    client = authenticated_client(app)
    created = client.post("/sessions", json={"case_id": cases.case_ids()[0]}).json()
    session_id = created["session"]["session_id"]
    active_payloads = [
        created,
        client.get(f"/sessions/{session_id}").json(),
        client.get(f"/sessions/{session_id}/state").json(),
        client.get(f"/sessions/{session_id}/available-evidences").json(),
    ]
    serialized = json.dumps(active_payloads).lower()
    assert "pathology" not in serialized
    assert "differential_diagnosis" not in serialized
    assert '"oracle"' not in serialized
    assert client.get(f"/research/cases/{cases.case_ids()[0]}").status_code == 403
    research = client.get(
        f"/research/cases/{cases.case_ids()[0]}",
        headers={"X-Research-Key": "local-research-only"},
    )
    assert research.status_code == 200
    assert "oracle" in research.json()


def test_public_evidence_dictionary_explains_dataset_codes(cases):
    client = TestClient(create_app(cases))
    response = client.get("/catalog/evidences")
    assert response.status_code == 200
    evidences = response.json()["evidences"]
    assert len(evidences) == len(cases.evidence_catalog)
    by_id = {item["evidence_id"]: item for item in evidences}
    assert by_id["E_214"]["question_en"] == (
        "Have you noticed a wheezing sound when you exhale?"
    )
    assert "pathology" not in json.dumps(evidences).lower()


def test_initial_belief_is_required(cases):
    app = create_app(cases)
    client = authenticated_client(app)
    created = client.post("/sessions", json={"case_id": cases.case_ids()[0]}).json()
    session_id = created["session"]["session_id"]
    assert client.get(
        f"/sessions/{session_id}/available-evidences"
    ).json()["actions"] == []
    evidence_id = next(
        evidence_id
        for evidence_id, definition in cases.evidence_catalog.items()
        if definition.parent_evidence_id is None
        and evidence_id != cases.get(cases.case_ids()[0]).initial_evidence.evidence_id
    )
    response = client.post(
        f"/sessions/{session_id}/actions/evidence",
        json={"evidence_id": evidence_id, "client_event_id": "premature"},
    )
    assert response.status_code == 409


def test_question_pool_covers_full_evidence_catalog_and_review_is_post_completion(cases):
    app = create_app(cases)
    client = authenticated_client(app)
    case = cases.get(cases.case_ids()[0])
    created = client.post("/sessions", json={
        "case_id": case.case_id,
        "belief_capture_mode": "EVERY_STEP",
    }).json()
    session_id = created["session"]["session_id"]
    belief = {
        "diagnoses": [{
            "condition_id": case.oracle.pathology,
            "rank": 1,
            "probability": 0.8,
        }],
        "overall_confidence": 0.7,
    }
    assert client.get(f"/sessions/{session_id}/review").status_code == 409
    assert client.get(f"/sessions/{session_id}/artifact").status_code == 409
    assert client.post(
        f"/sessions/{session_id}/beliefs",
        json={"belief": belief, "client_event_id": "initial"},
    ).status_code == 201
    actions = client.get(
        f"/sessions/{session_id}/available-evidences"
    ).json()["actions"]
    assert len(actions) == len(cases.evidence_catalog) - 1
    assert all(action["suggested_by"] for action in actions)
    child_action = next(action for action in actions if not action["dependency_met"])
    assert child_action["parent_evidence_id"]
    assert child_action["parent_question_en"]
    truth = case.truth_map()
    statuses = {truth[action["evidence_id"]].status.value for action in actions}
    assert statuses & {"PRESENT", "VALUE"}
    assert statuses & {"ABSENT", "DEFAULT", "NOT_APPLICABLE"}

    negative_root = next(
        action
        for action in actions
        if action["dependency_met"]
        and truth[action["evidence_id"]].status.value == "ABSENT"
    )
    negative_answer = client.post(
        f"/sessions/{session_id}/actions/evidence",
        json={
            "evidence_id": negative_root["evidence_id"],
            "client_event_id": "negative-evidence",
        },
    )
    assert negative_answer.status_code == 200
    assert negative_answer.json()["answer_text"] == "No"
    assert client.post(
        f"/sessions/{session_id}/beliefs",
        json={"belief": belief, "client_event_id": "after-negative"},
    ).status_code == 201
    assert client.post(
        f"/sessions/{session_id}/finalize",
        json={"belief": belief, "client_event_id": "final"},
    ).status_code == 200
    review = client.get(f"/sessions/{session_id}/review")
    assert review.status_code == 200
    assert review.json()["comparison"]["is_correct"] is True
    assert review.json()["trajectory"][0]["question"]
    assert review.json()["case_graph"]["session_count"] == 1
    assert review.json()["case_graph"]["completed_session_count"] == 1
    assert review.json()["case_graph"]["participant_count"] == 1
    assert review.json()["case_graph"]["physician_count"] == 1
    assert review.json()["ground_truth_tree"]["case_id"] == case.case_id
    assert review.json()["community_final_diagnoses"][0]["condition"] == (
        case.oracle.pathology
    )
    artifact = client.get(f"/sessions/{session_id}/artifact")
    assert artifact.status_code == 200
    payload = artifact.json()
    assert payload["schema_version"] == "clincforestbench.arena-run.v1"
    assert payload["session"]["session_id"] == session_id
    assert payload["capture_semantics"]["overall_confidence"] == "not_collected"
    assert payload["belief_history"][-1]["submission_type"] == "FINAL_DIAGNOSIS"
    assert (
        payload["patient_path"][0]["belief"]["diagnoses"][0]["condition_id"]
        == case.oracle.pathology
    )
    assert payload["outcome"]["is_correct"] is True

    history = client.get("/me/history").json()
    assert history["username"] == "doctor"
    assert history["sessions"][0]["session_id"] == session_id
    detail = client.get(f"/me/history/{session_id}").json()
    assert detail["ground_truth_tree"]["case_id"] == case.case_id
    assert detail["belief_rounds"][-1]["is_final"] is True

    forest = client.get(
        f"/research/forest/cases/{case.case_id}",
        headers={"X-Research-Key": "local-research-only"},
    )
    assert forest.status_code == 200
    assert forest.json()["summary"]["physician_count"] == 1
    assert forest.json()["final_diagnoses"][0]["is_ground_truth"] is True


def test_authentication_ownership_and_plaintext_admin_view(cases):
    app = create_app(cases)
    unauthenticated = TestClient(app)
    assert unauthenticated.post("/sessions", json={}).status_code == 401

    owner = authenticated_client(app, "owner")
    created = owner.post("/sessions", json={}).json()
    session_id = created["session"]["session_id"]
    other = authenticated_client(app, "other")
    assert other.get(f"/sessions/{session_id}").status_code == 403

    accounts = owner.get(
        "/admin/accounts",
        headers={"X-Research-Key": "local-research-only"},
    )
    assert accounts.status_code == 200
    by_name = {item["username"]: item for item in accounts.json()["accounts"]}
    assert by_name["owner"]["password_plaintext"] == "test-password"
    assert by_name["owner"]["session_count"] == 1


def test_research_tree_audit_returns_raw_processed_and_classification(cases):
    app = create_app(cases)
    client = TestClient(app)
    case_id = cases.case_ids()[0]
    path = f"/research/cases/{case_id}/tree-audit"
    assert client.get(path).status_code == 403
    response = client.get(
        path, headers={"X-Research-Key": "local-research-only"}
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["raw_case"]["raw_row"]["PATHOLOGY"]
    assert payload["processed_tree"]["classification"]["disease_category"]
    assert payload["processed_tree"]["tree"]["nodes"]
