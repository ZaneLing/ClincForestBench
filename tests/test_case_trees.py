import ast

from fastapi.testclient import TestClient

from backend.app.main import create_app
from backend.app.services.case_tree_service import CaseTreeService
from etl.build_case_trees import TREE_SCHEMA_VERSION, canonical_hash


def test_mvp50_raw_to_tree_artifacts_are_complete_and_auditable(cases):
    service = CaseTreeService(cases.root)
    manifest = service.manifest()
    assert manifest["case_count"] == 130
    assert manifest["dataset_case_counts"] == {
        "DDXPlus": 50,
        "MedAgentBench": 30,
        "Synthea": 50,
    }
    assert manifest["pathology_count"] >= 48
    assert manifest["taxonomy_condition_count"] >= 49
    assert manifest["category_count"] >= 11
    assert manifest["all_checks_pass"] is True
    assert {item["case_id"] for item in manifest["cases"]} == set(
        cases.case_ids()
    )

    for entry in manifest["cases"]:
        audit = service.get(entry["case_id"])
        raw_case = audit["raw_case"]
        tree = audit["processed_tree"]
        assert canonical_hash(raw_case["raw_row"]) == entry["raw_sha256"]
        assert canonical_hash(tree) == entry["tree_sha256"]
        if entry["dataset_name"] != "DDXPlus":
            assert tree["schema_version"] == "clinical_forest_tree_v3"
            assert tree["semantics"]["generation_mode"] == entry[
                "generation_mode"
            ]
            assert all(
                edge["source"] in {
                    node["node_id"] for node in tree["tree"]["nodes"]
                }
                and edge["target"] in {
                    node["node_id"] for node in tree["tree"]["nodes"]
                }
                for edge in tree["tree"]["edges"]
            )
            continue

        assert tree["schema_version"] == TREE_SCHEMA_VERSION
        assert tree["classification"]["disease_category"]
        assert all(tree["audit"]["checks"].values())
        assert tree["audit"]["action_node_count"] == entry[
            "source_evidence_count"
        ]
        assert tree["audit"]["observation_node_count"] == entry[
            "source_evidence_count"
        ]
        assert set(tree["semantics"]["supported_action_types"]) == {
            "ASK_QUESTION"
        }
        assert "LAB_TEST" in tree["semantics"]["unsupported_source_modalities"]

        nodes = {node["node_id"]: node for node in tree["tree"]["nodes"]}
        assert tree["tree"]["root_id"] in nodes
        raw_differential = ast.literal_eval(
            raw_case["raw_row"]["DIFFERENTIAL_DIAGNOSIS"]
        )
        diagnosis_nodes = [
            node
            for node in tree["tree"]["nodes"]
            if node["node_type"] == "DIAGNOSIS"
        ]
        assert len(diagnosis_nodes) == len(raw_differential)
        assert [node["label"] for node in diagnosis_nodes] == [
            item[0] for item in raw_differential
        ]
        assert [node["data"]["probability"] for node in diagnosis_nodes] == [
            item[1] for item in raw_differential
        ]
        ground_truth_nodes = [
            node for node in diagnosis_nodes if node["data"]["is_ground_truth"]
        ]
        assert [node["label"] for node in ground_truth_nodes] == [
            raw_case["raw_row"]["PATHOLOGY"]
        ]
        assert all(
            edge["source"] in nodes and edge["target"] in nodes
            for edge in tree["tree"]["edges"]
        )


def test_case_tree_audit_api_is_protected_and_returns_all_three_views(cases):
    client = TestClient(create_app(cases))
    assert client.get("/research/case-trees").status_code == 403
    headers = {"X-Research-Key": "local-research-only"}
    manifest = client.get("/research/case-trees", headers=headers)
    assert manifest.status_code == 200
    case_id = manifest.json()["cases"][0]["case_id"]
    response = client.get(
        f"/research/cases/{case_id}/tree-audit", headers=headers
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["raw_case"]["raw_row"]
    assert payload["processed_tree"]["tree"]["nodes"]
    assert payload["processed_tree"]["audit"]["checks"]
