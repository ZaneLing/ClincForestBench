import json
from collections import Counter

from fastapi.testclient import TestClient

from backend.app.domain.action import ClinicalAction
from backend.app.domain.enums import ActionType
from backend.app.domain.environment import DDXPlusEnvironment
from backend.app.main import create_app
from backend.app.services.encounter_catalog import EncounterCatalog
from backend.app.services.case_tree_service import CaseTreeService


def evidence_cases(cases):
    return [case for case in cases.cases.values()
            if case.generation_mode == "SOURCE_BACKED_EVIDENCE"]


def test_all_cases_use_shared_runtime_and_converted_cases_are_unordered(cases):
    assert len(Counter(case.dataset.name for case in cases.cases.values())) == 14
    converted = evidence_cases(cases)
    assert len(converted) == len(cases.cases) - 90
    trees = CaseTreeService(cases.root)
    for case in converted:
        assert case.case_hash == case.compute_hash()
        assert case.initial_context["protocol"] == "UNORDERED_EVIDENCE"
        assert case.original_trajectory == []
        assert case.reference_quality
        assert all(action.parent_evidence_id is None for action in case.action_space)
        tree = trees.get(case.case_id)["processed_tree"]
        assert tree["semantics"]["tree_kind"] == "UNORDERED_EVIDENCE"
        assert not any(edge["edge_type"] in {"NEXT_STAGE", "LATENCY", "NEXT_EVENT"}
                       for edge in tree["tree"]["edges"])
        active = {"initial_context": case.initial_context, "truth": [v.model_dump() for v in case.truth],
                  "actions": [v.model_dump() for v in case.action_space], "tree": tree}
        serialized = json.dumps(active)
        for forbidden in ("current_time_min", "expected_available_game_time", "pending_actions",
                          "relative_available_min", "sequential_actions", "WAIT_FOR_NEXT_RESULT"):
            assert forbidden not in serialized


def test_any_evidence_order_returns_same_source_results_and_merges_same_state(cases):
    for case in evidence_cases(cases):
        catalog = cases.catalog_for_case(case.case_id)
        results = []
        for reverse in (False, True):
            env = DDXPlusEnvironment(cases.cases, catalog)
            env.reset(case.case_id)
            available = env.get_available_actions().actions
            assert all(action.dependency_met for action in available)
            available = sorted(available, key=lambda a: a.evidence_id, reverse=reverse)
            seen = {}
            for action in available:
                result = env.step(ClinicalAction(action_type=ActionType.ASK_EVIDENCE,
                                                evidence_id=action.evidence_id,
                                                client_event_id=action.evidence_id))
                assert result.observation == case.truth_map()[action.evidence_id]
                seen[action.evidence_id] = result.observation.model_dump()
            assert env.get_available_actions().actions == []
            state = env.get_state()
            assert "current_time_min" not in state.model_dump()
            results.append((state.state_hash, seen))
        assert results[0] == results[1]


def test_source_records_are_preserved_and_case_answers_do_not_cross(cases):
    catalog = EncounterCatalog(cases)
    for case in evidence_cases(cases):
        for eid, records in case.evidence_records.items():
            item = eid.removeprefix("CFB_E::")
            actual = catalog.bindings[case.case_id][item]
            assert [(r["source_id"], r["result"]) for r in actual] == [
                (r["source_id"], r["result"]) for r in records]
            assert case.truth_map()[eid].value == [r["result"] for r in records]
    memory = [case for case in evidence_cases(cases) if case.dataset.name == "MedMemoryBench"]
    assert len(memory) == 30
    for case in memory:
        assert all(item.parent_evidence_id is None for item in case.action_space)


def test_api_has_one_case_catalog_and_no_temporal_runtime(cases):
    client = TestClient(create_app(cases))
    assert client.get("/health").json()["case_count"] == len(cases.cases)
    assert len(client.get("/cases").json()["cases"]) == len(cases.cases)
    assert len(client.get("/research/forest/cases").json()["cases"]) == len(cases.cases)
    assert not any("temporal" in route.path or route.path.endswith("/wait")
                   for route in client.app.routes)
    headers = {"X-Research-Key": "local-research-only"}
    for case in evidence_cases(cases):
        assert client.get(f"/research/cases/{case.case_id}").status_code == 403
        public = client.get(f"/cases/{case.case_id}/catalog").json()
        assert "source_provenance" not in json.dumps(public)
        assert client.get(f"/research/cases/{case.case_id}/tree-audit",
                          headers=headers).status_code == 200


def test_converted_case_full_arena_lifecycle_is_clock_free(cases):
    client = TestClient(create_app(cases))
    token = client.post("/auth/register", json={"username": "evidence-doctor",
                                                "password": "test-password"}).json()["token"]
    client.headers["Authorization"] = f"Bearer {token}"
    for case in evidence_cases(cases):
        sid = client.post("/sessions", json={"case_id": case.case_id}).json()["session"]["session_id"]
        belief = {"diagnoses": [{"condition_id": case.oracle.pathology, "rank": 1, "probability": 1}],
                  "overall_confidence": 0}
        assert client.post(f"/sessions/{sid}/beliefs",
                           json={"belief": belief, "client_event_id": "initial"}).status_code == 201
        actions = client.get(f"/sessions/{sid}/available-evidences").json()["actions"]
        if actions:
            result = client.post(f"/sessions/{sid}/actions/evidence",
                                 json={"evidence_id": actions[-1]["evidence_id"],
                                       "client_event_id": "choose-last"}).json()
            assert result["answer_text"]
            assert "current_time_min" not in result["state"]
        assert client.post(f"/sessions/{sid}/finalize",
                           json={"belief": belief, "client_event_id": "final"}).status_code == 200
        review = client.get(f"/sessions/{sid}/review").json()
        from backend.app.services.localization_service import localize_payload
        assert review["reference_quality"] == localize_payload(case.reference_quality, "en")
        assert review["comparison"]["is_correct"]


def test_public_media_stays_confined_to_case_and_access_class(cases, tmp_path):
    import pytest
    from backend.app.services.case_service import CaseService
    # Use a lightweight instance with a controlled generated bundle.
    case = next(c for c in evidence_cases(cases) if c.dataset.name == "MediScope")
    directory = tmp_path / "data/processed/evidence/case_bundles" / case.case_id / "media"
    directory.mkdir(parents=True)
    (directory / "report.jpg").write_bytes(b"source-image")
    service = object.__new__(CaseService)
    service.root, service._cases = tmp_path, {case.case_id: case}
    assert service.public_media_path(case.case_id, "report.jpg").read_bytes() == b"source-image"
    with pytest.raises(KeyError):
        service.public_media_path(case.case_id, "../case.json")
    private = case.model_copy(deep=True)
    private.source_provenance["source"]["access_class"] = "RESTRICTED"
    service._cases[case.case_id] = private
    with pytest.raises(PermissionError):
        service.public_media_path(case.case_id, "report.jpg")


def test_converted_source_translation_privacy_defaults_to_private(cases):
    from pathlib import Path
    from tools.build_case_translations import is_restricted_case, manifest_case_paths
    paths = manifest_case_paths()
    assert any("evidence" in path.parts for path in paths)
    assert not any("temporal" in path.parts for path in paths)
    path = Path("data/processed/evidence/case_bundles/example/case.json")
    assert is_restricted_case(path, {})
    for case in evidence_cases(cases):
        access = case.source_provenance["source"].get("access_class", "")
        assert is_restricted_case(path, case.model_dump()) == (not access.startswith("PUBLIC"))
