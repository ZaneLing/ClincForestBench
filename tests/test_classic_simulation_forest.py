"""Classic circular graph must project demo data without writing legacy sessions."""
import copy
import json
from collections import Counter, defaultdict

import pytest
from fastapi.testclient import TestClient

from backend.app.api.encounters import ActionRequest, DiagnosisRequest, EventRequest
from backend.app.main import create_app
from backend.app.services.classic_simulation_forest import project_classic_simulations
from backend.app.services.encounter_catalog import EncounterCatalog
from backend.app.services.encounter_service import EncounterService

CASE_ID = "DDX_TEST_0021752"
PATHS = [
    ["E_123", "E_124", "E_201", "E_66"],
    ["E_123", "E_66", "E_201", "E_124"],
    ["E_66", "E_123", "E_124", "E_201"],
    ["E_201", "E_91", "E_66", "E_123"],
]


@pytest.fixture(scope="module")
def catalog(cases):
    return EncounterCatalog(cases)


def item_for(catalog, evidence_id):
    return next(iid for iid, rows in catalog.bindings[CASE_ID].items()
                if len(rows) == 1 and rows[0]["source_id"] == evidence_id)


def seed(svc, catalog):
    documents = []
    for i, evidence_ids in enumerate(PATHS):
        owner = "demo-%d" % i
        doc = svc.create(CASE_ID, owner, "start", is_simulation=True)
        for step, eid in enumerate(evidence_ids):
            svc.act(doc["id"], owner, ActionRequest(item_id=item_for(catalog, eid),
                client_event_id="step-%d" % step, reason_id="support"))
        svc.diagnose(doc["id"], owner, DiagnosisRequest(client_event_id="dx", diagnoses=["模拟路径%d：未验证诊断" % i]))
        doc = svc.finish(doc["id"], owner, EventRequest(client_event_id="finish"))
        documents.append(doc)
    return documents


def test_four_paths_classic_merge_and_source_answers(catalog, cases):
    svc = EncounterService(catalog, ":memory:")
    docs = seed(svc, catalog)
    before = copy.deepcopy(docs)
    detail = svc.classic_simulation_detail(CASE_ID, "zh-CN")
    assert docs == before
    assert detail["summary"]["session_count"] == detail["summary"]["completed_session_count"] == 4
    assert detail["summary"]["physician_session_count"] == detail["summary"]["physician_count"] == 0
    assert len(detail["nodes"]) == 13 and len(detail["edges"]) == 15
    paths = detail["source_trajectories"]
    assert [p["evidence_ids"] for p in paths] == PATHS
    assert len({tuple(p["evidence_ids"]) for p in paths}) == 4
    assert len({p["final_state_hash"] for p in paths}) == 2
    assert paths[0]["final_state_hash"] == paths[1]["final_state_hash"] == paths[2]["final_state_hash"]
    assert paths[1]["state_hashes"][2] == paths[2]["state_hashes"][2]
    assert all(node["belief_submission_count"] == 0 and node["diagnoses"] == [] for node in detail["nodes"])
    assert detail["stages"] == detail["final_diagnoses"] == []
    assert len(detail["final_diagnosis_texts"]) == 4
    assert "owner" not in json.dumps(detail)
    node_counts = Counter(h for path in paths for h in path["state_hashes"])
    edge_counts = Counter((path["state_hashes"][i], path["state_hashes"][i+1], eid)
                         for path in paths for i, eid in enumerate(path["evidence_ids"]))
    outgoing = defaultdict(float)
    for node in detail["nodes"]:
        assert node["support"] == node_counts[node["state_hash"]]
        assert node["visit_rate"] == node["support"] / 4
        for observation in node["observations"]:
            expected = cases.get(CASE_ID).truth_map()[observation["evidence_id"]].model_dump(mode="json")
            assert observation == expected
    for edge in detail["edges"]:
        assert edge["support"] == edge_counts[(edge["source_hash"], edge["target_hash"], edge["action_evidence_id"])]
        outgoing[edge["source_hash"]] += edge["probability"]
    assert all(value == pytest.approx(1) for value in outgoing.values())
    assert "慢性阻塞性" in detail["evidence_labels"]["E_123"]
    assert svc.forest()["session_count"] == 0
    assert svc.forest(simulation=True)["session_count"] == 4


def test_projection_read_only_isolated_persistent_and_empty(catalog, tmp_path):
    database = tmp_path / "visits.db"
    svc = EncounterService(catalog, database)
    real = svc.create(CASE_ID, "real-doctor", "start")
    docs = seed(svc, catalog)
    before = svc.forest()
    total = svc.connection.total_changes
    index = svc.classic_simulation_index()
    detail = svc.classic_simulation_detail(CASE_ID)
    assert index["case_count"] == 1 and index["cases"][0]["simulation_session_count"] == 4
    assert total == svc.connection.total_changes
    assert before == svc.forest()
    assert svc.get(real["id"], "real-doctor") == real
    restarted = EncounterService(catalog, database)
    assert detail == restarted.classic_simulation_detail(CASE_ID)
    assert [restarted.get(doc["id"], doc["owner"]) for doc in docs] == docs
    empty = EncounterService(catalog, ":memory:")
    assert empty.classic_simulation_index()["case_count"] == 0
    assert empty.classic_simulation_detail(CASE_ID)["nodes"] == []
    with pytest.raises(KeyError):
        svc.classic_simulation_detail("unknown")
    with pytest.raises(ValueError, match="DDXPlus"):
        svc.classic_simulation_detail("SYN_ENC_0001")


@pytest.mark.parametrize("field", ["answer", "status"])
def test_corrupt_source_answer_is_rejected_not_fabricated(catalog, cases, field):
    svc = EncounterService(catalog, ":memory:")
    docs = seed(svc, catalog)
    docs[0]["events"][0]["records"][0]["result"][field] = "incorrect"
    with pytest.raises(ValueError, match="differs"):
        project_classic_simulations(cases, docs, CASE_ID)


def test_keyless_projection_routes_leave_legacy_forests_unchanged(cases):
    client = TestClient(create_app(cases))
    legacy_before = client.get("/research/forest/cases/" + CASE_ID).json()
    base = "/research/classic-simulation-forest/cases"
    assert client.get(base).status_code == 200
    assert client.get(base).json()["case_count"] == 0
    token = client.post("/auth/register", json={"username": "isolated-demo", "password": "test-password"}).json()["token"]
    headers = {"Authorization": "Bearer " + token}
    visit = client.post("/encounters", headers=headers, json={"case_id": CASE_ID,
        "client_event_id": "start", "is_simulation": True}).json()
    # Active visits are not mislabelled as aborted or completed.
    detail = client.get(base + "/" + CASE_ID).json()
    assert detail["source_trajectories"][0]["status"] == "ACTIVE"
    assert detail["summary"]["completed_session_count"] == 0
    assert detail["summary"]["simulation_session_count"] == 1
    assert client.get(base + "/" + CASE_ID, headers={"X-Research-Key": "wrong"}).status_code == 200
    assert client.get("/research/forest/cases/" + CASE_ID).json() == legacy_before
    assert client.get("/encounters/" + visit["id"]).status_code == 401
    assert client.get("/research/encounter-cases/" + CASE_ID).status_code == 403
    assert client.get(base + "/unknown").status_code == 404
    assert client.get(base + "/SYN_ENC_0001").status_code == 409
