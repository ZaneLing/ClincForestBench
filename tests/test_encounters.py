import json
from concurrent.futures import ThreadPoolExecutor

import pytest
from fastapi.testclient import TestClient

from backend.app.api.encounters import ActionRequest, DiagnosisRequest, EventRequest, PrescriptionRequest
from backend.app.main import create_app
from backend.app.services.encounter_catalog import EncounterCatalog
from backend.app.services.encounter_service import EncounterService
from backend.app.services.temporal_case_service import TemporalCaseService


@pytest.fixture(scope="module")
def catalog(cases):
    return EncounterCatalog(cases, TemporalCaseService(cases.root))


def action(item_id, event_id="step", reason_id="support", **kwargs):
    return ActionRequest(item_id=item_id, client_event_id=event_id, reason_id=reason_id, **kwargs)


@pytest.mark.parametrize("locale", ["en", "zh-CN"])
def test_inspector_matches_arena_for_every_case_and_binding(catalog, locale):
    svc = EncounterService(catalog, ":memory:")
    for case_id in catalog.visits:
        source_before = json.dumps(catalog.bindings[case_id], ensure_ascii=False)
        inspection = catalog.inspection(case_id, locale)
        doc = {"case_id": case_id, "visit": catalog.visits[case_id], "diagnoses": [],
               "events": [{"records": rows} for rows in catalog.bindings[case_id].values()]}
        view = svc.view(doc, locale)
        assert inspection["visit"] == view["visit"]
        assert list(inspection["bindings"].values()) == [e["records"] for e in view["events"]]
        assert set(inspection["bindings"]) <= set(catalog.items)
        for kind in ("inquiry", "operation"):
            expected = [i for i in catalog.items.values() if i["kind"] == kind]
            assert inspection["counts"][kind] == {
                "total": len(expected),
                "recorded": sum(bool(inspection["bindings"].get(i["id"])) for i in expected),
            }
        assert len(inspection["treatments"]) == len(catalog.treatments[case_id])
        assert source_before == json.dumps(catalog.bindings[case_id], ensure_ascii=False)
    assert svc.forest()["session_count"] == 0


def test_inspector_routes_are_research_only_read_only_and_share_global_catalog(cases):
    client = TestClient(create_app(cases))
    index_route = "/research/encounter-cases"
    case_route = index_route + "/DDX_TEST_0021752"
    assert client.get(index_route).status_code == 403
    assert client.get(case_route).status_code == 403
    headers = {"X-Research-Key": "local-research-only"}
    index = client.get(index_route, headers=headers).json()
    assert {row["source"] for row in index["cases"]} == {"classic", "temporal"}
    assert len(index["cases"]) == 188
    for locale in ("en", "zh-CN"):
        response = client.get(case_route, params={"lang": locale}, headers=headers)
        assert response.status_code == 200
        data = response.json()
        assert data["bindings"]["inquiry:CHIEF"]
        assert "inquiry:ONSET" not in data["bindings"]
    assert client.get(index_route + "/not-a-case", headers=headers).status_code == 404
    assert client.get("/research/encounter-forest", headers=headers).json()["session_count"] == 0
    token = client.post("/auth/register", json={"username": "inspector-test", "password": "test-password"}).json()["token"]
    client.headers["Authorization"] = f"Bearer {token}"
    assert client.get(index_route).status_code == 403
    arena_catalog = client.get("/encounters/catalog").json()
    assert index["items"] == arena_catalog["items"]
    assert {c["case_id"] for c in index["cases"]} == {c["case_id"] for c in arena_catalog["cases"]}
    assert "bindings" not in arena_catalog
    assert client.get("/encounters/history").json() == []


def test_all_sources_accounted_for_and_catalog_bilingual(catalog, cases):
    assert len(catalog.visits) == len(cases.cases) + len(catalog.temporal.manifest()["cases"])
    assert len([i for i in catalog.items.values() if i["kind"] == "operation"]) > 200
    assert len([i for i in catalog.items.values() if i["kind"] == "inquiry"]) > 250
    for item in catalog.items.values():
        assert item["label"]["en"] and item["label"]["zh-CN"]
        assert any("\u4e00" <= c <= "\u9fff" for c in item["label"]["zh-CN"])
        assert len(catalog.reasons(item["id"])) == 5
        assert set(item) == {"id", "kind", "category", "label", "catalog_version"}
    assert "anemia" in catalog.reasons("operation:CBC")[0]["label"]["en"]
    assert catalog.reasons("operation:CBC") != catalog.reasons("operation:ECG")
    for case_id, bundle in cases.cases.items():
        assert {r.evidence_id for r in bundle.truth} <= {a["source_id"] for a in catalog.audit[case_id]}
    for row in catalog.temporal.manifest()["cases"]:
        case = catalog.temporal.get(row["case_id"])
        assert {e.event_id for e in case.timeline_events} <= {a["source_id"] for a in catalog.audit[case.case_id]}


@pytest.mark.parametrize("item_id", ["operation:CT_HEAD", "inquiry:FINANCES", "inquiry:ONSET"])
def test_missing_result_terminates_atomically_and_survives_restart(catalog, tmp_path, item_id):
    database = tmp_path / "encounters.db"
    svc = EncounterService(catalog, database)
    doc = svc.create("DDX_TEST_0021752", "alice", "visit")
    # Preserve the answered question and the failed next step, not only the terminal event.
    svc.act(doc["id"], "alice", action("inquiry:CHIEF", event_id="answered"))
    request = action(item_id)
    ended = svc.act(doc["id"], "alice", request)
    assert ended["status"] == "TERMINATED_MISSING_RESULT"
    assert ended["completed_at"]
    assert len(ended["events"]) == 2
    assert ended["events"][0]["records"]
    assert ended["events"][-1]["reason_id"] == "support"
    assert ended["events"][-1]["records"] == []
    assert ended["events"][-1]["result_status"] == "NOT_RECORDED"
    assert len(ended["events"][-1]["reason_options"]) == 5
    assert svc.act(doc["id"], "alice", request) == ended
    with pytest.raises(ValueError, match="already closed"):
        svc.diagnose(doc["id"], "alice", DiagnosisRequest(diagnoses=["Asthma"], client_event_id="late"))
    with pytest.raises(ValueError, match="already closed"):
        svc.act(doc["id"], "alice", action("inquiry:CHIEF", event_id="late-action"))
    with pytest.raises(ValueError, match="already closed"):
        svc.finish(doc["id"], "alice", EventRequest(client_event_id="late-finish"))
    reopened = EncounterService(catalog, database)
    assert reopened.get(doc["id"], "alice") == ended
    with pytest.raises(KeyError):
        reopened.get(doc["id"], "bob")
    assert reopened.history("alice")[0]["status"] == "TERMINATED_MISSING_RESULT"
    if item_id.startswith("inquiry:"):
        assert reopened.forest()["missing_inquiry_counts"] == {item_id: 1}


def test_reason_validation_and_diagnosis_anytime(catalog):
    svc = EncounterService(catalog, ":memory:")
    doc = svc.create("DDX_TEST_0021752", "alice", "visit")
    with pytest.raises(ValueError, match="offered"):
        svc.act(doc["id"], "alice", action("operation:CBC", reason_id="invented"))
    with pytest.raises(ValueError, match="other reason"):
        svc.act(doc["id"], "alice", action("operation:CBC", reason_id="other"))
    request = DiagnosisRequest(diagnoses=["Custom diagnosis 自定义诊断"], client_event_id="diagnosis")
    current = svc.diagnose(doc["id"], "alice", request)
    assert current["diagnoses"] == request.diagnoses
    completed = svc.finish(doc["id"], "alice", EventRequest(client_event_id="finish"))
    assert completed["status"] == "COMPLETED"
    assert completed["prescription"] is None


def test_recorded_answer_negative_and_reason_hypothesis_preserved(catalog):
    svc = EncounterService(catalog, ":memory:")
    doc = svc.create("DDX_TEST_0021752", "alice", "visit")
    iid = next(i for i, rs in catalog.bindings[doc["case_id"]].items() if rs[0]["result"].get("status") == "ABSENT")
    request = action(iid, reason_id="differentiate", hypothesis="Asthma versus infection", reason_text="My reasoning")
    result = svc.act(doc["id"], "alice", request)
    assert result["events"][0]["records"][0]["result"]["answer"] == "No"
    assert result["status"] == "ACTIVE"
    assert svc.view(result, "zh-CN")["events"][0]["records"][0]["result"]["answer"] == "否"
    assert svc.view(result, "zh-CN")["events"][0]["hypothesis"] == request.hypothesis
    with pytest.raises(ValueError, match="different request"):
        svc.act(doc["id"], "alice", action(iid, reason_id="urgent"))


def test_concurrent_retry_is_single_event(catalog, tmp_path):
    svc = EncounterService(catalog, tmp_path / "concurrent.db")
    doc = svc.create("DDX_TEST_0021752", "alice", "visit")
    with ThreadPoolExecutor(max_workers=4) as pool:
        results = list(pool.map(lambda _: svc.act(doc["id"], "alice", action("operation:CBC")), range(4)))
    assert all(len(d["events"]) == 1 for d in results)


def test_prescription_after_diagnosis_is_optional_and_persisted(catalog):
    svc = EncounterService(catalog, ":memory:")
    case_id = next(cid for cid, rows in catalog.treatments.items() if rows)
    doc = svc.create(case_id, "alice", "visit")
    request = PrescriptionRequest(client_event_id="rx", text="Clinician-authored treatment plan")
    with pytest.raises(ValueError, match="diagnosis"):
        svc.prescribe(doc["id"], "alice", request)
    svc.diagnose(doc["id"], "alice", DiagnosisRequest(client_event_id="dx", diagnoses=["Working diagnosis"]))
    result = svc.prescribe(doc["id"], "alice", request)
    assert result["prescription"] == request.text
    assert svc.view(result, "en")["prescription_available"]


def test_panel_components_units_and_opening_inquiry(catalog):
    svc = EncounterService(catalog, ":memory:")
    doc = svc.create("SYN_ENC_0001", "alice", "visit")
    result = svc.act(doc["id"], "alice", action("operation:VITALS"))
    raw = result["events"][0]["records"][0]["result"]
    translated = svc.view(result, "zh-CN")["events"][0]["records"][0]["result"]
    assert [r["unit"] for r in translated] == [r["unit"] for r in raw]
    assert catalog.bindings[doc["case_id"]]["inquiry:CHIEF"][0]["result"] == doc["visit"]["presentation"]
    assert any("operation:CBC" in rows for cid, rows in catalog.bindings.items() if cid.startswith("SYN_"))


def test_bilingual_coverage_audit(catalog):
    from analysis.audit_encounter_mapping import audit
    assert audit(catalog)["localization"]["gap_count"] == 0


def test_every_case_can_start_and_retrieve_a_mapped_source(catalog):
    svc = EncounterService(catalog, ":memory:")
    for cid in catalog.visits:
        doc = svc.create(cid, "coverage", cid)
        iid = next(iter(catalog.bindings[cid]))
        result = svc.act(doc["id"], "coverage", action(iid))
        assert result["events"][0]["records"]
        assert result["status"] == "ACTIVE"
        assert svc.view(result, "en")["id"] == svc.view(result, "zh-CN")["id"]


def test_shared_menu_and_visit_do_not_expose_synthea_diagnosis(catalog, cases):
    case = next(b for b in cases.cases.values() if b.dataset.name == "Synthea")
    assert case.initial_context["encounter_reason"] not in json.dumps(catalog.visits[case.case_id])
    assert "truth" not in json.dumps(catalog.items)
    assert "available" not in json.dumps(catalog.items)
    assert "operation:CXR" in catalog.bindings[next(cid for cid, rows in catalog.bindings.items() if "operation:CXR" in rows)]


@pytest.mark.parametrize("locale", ["en", "zh-CN"])
def test_next_question_returns_answer_or_ends_case_over_http(cases, locale):
    client = TestClient(create_app(cases))
    token = client.post("/auth/register", json={"username": "next-question", "password": "test-password"}).json()["token"]
    client.headers["Authorization"] = f"Bearer {token}"
    visit = client.post("/encounters", json={"case_id": "DDX_TEST_0021752", "client_event_id": "new"}).json()
    route = f"/encounters/{visit['id']}"
    answered = client.post(route + f"/actions?lang={locale}", json=action("inquiry:CHIEF", event_id="first").model_dump())
    assert answered.status_code == 200
    assert answered.json()["status"] == "ACTIVE"
    assert answered.json()["events"][-1]["records"]
    request = action("inquiry:ONSET", event_id="next", reason_id="differentiate").model_dump()
    ended = client.post(route + f"/actions?lang={locale}", json=request)
    assert ended.status_code == 200
    assert ended.json()["status"] == "TERMINATED_MISSING_RESULT"
    assert ended.json()["completed_at"]
    assert ended.json()["events"][-1]["result_status"] == "NOT_RECORDED"
    assert ended.json()["events"][-1]["reason_id"] == "differentiate"
    assert client.post(route + f"/actions?lang={locale}", json=request).json() == ended.json()
    assert client.get(route + f"?lang={locale}").json() == ended.json()
    exported = client.get(route + "/export").json()
    assert [event["item"]["id"] for event in exported["events"]] == ["inquiry:CHIEF", "inquiry:ONSET"]
    assert client.get("/encounters/history").json()[0]["status"] == "TERMINATED_MISSING_RESULT"
    assert client.post(route + "/actions", json=action("inquiry:FINANCES", event_id="too-late").model_dump()).status_code == 409


def test_encounter_routes_auth_ownership_history_export_and_reason_required(cases):
    client = TestClient(create_app(cases))
    assert client.get("/encounters/catalog").status_code == 401
    token = client.post("/auth/register", json={"username": "encounter-doc", "password": "test-password"}).json()["token"]
    client.headers["Authorization"] = f"Bearer {token}"
    catalog_response = client.get("/encounters/catalog")
    assert catalog_response.status_code == 200
    request = {"case_id": cases.case_ids()[0], "client_event_id": "new"}
    created = client.post("/encounters", json=request)
    assert created.status_code == 201
    doc = created.json()
    assert client.post("/encounters", json=request).json()["id"] == doc["id"]
    route = f"/encounters/{doc['id']}"
    assert client.post(route + "/actions", json={"item_id": "operation:CBC", "client_event_id": "no-reason"}).status_code == 422
    assert client.post(route + "/actions", json=action("operation:CBC").model_dump()).json()["status"] == "TERMINATED_MISSING_RESULT"
    assert client.get(route + "/export").json()["events"][0]["reason_options"]
    assert client.get("/encounters/history").json()[0]["id"] == doc["id"]
    assert client.get("/research/encounter-mapping").status_code == 403
    forest = client.get("/research/encounter-forest", headers={"X-Research-Key": "local-research-only"}).json()
    assert forest["session_count"] == 1
    assert forest["reason_counts"] == {"support": 1}
    assert forest["missing_examination_counts"] == {"operation:CBC": 1}
    second = client.post("/auth/register", json={"username": "other-doc", "password": "test-password"}).json()["token"]
    client.headers["Authorization"] = f"Bearer {second}"
    assert client.get(route).status_code == 404
    assert client.get(route + "/export").status_code == 404
