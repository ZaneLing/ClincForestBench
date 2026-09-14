from __future__ import annotations

import hashlib
import json
import re
from collections import Counter
from pathlib import Path
from typing import Any

import pyarrow.parquet as pq

from backend.app.domain.evidence import human_readable_response
from backend.app.services.case_service import CaseService
from etl.common import (
    ddx_config,
    dump_json,
    load_json,
    load_yaml,
    parse_python_literal,
    path_from_root,
    selection_config,
)


TREE_SCHEMA_VERSION = "ground_truth_exposure_tree_v2"
CASE_ID_PATTERN = re.compile(r"^DDX_([A-Z]+)_(\d{7})$")


def canonical_hash(payload: Any) -> str:
    encoded = json.dumps(
        payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def disease_category_map(conditions: set[str]) -> tuple[dict[str, dict], dict]:
    taxonomy = load_yaml("configs/disease_categories.yaml")
    mapping: dict[str, dict] = {}
    for key, category in taxonomy["categories"].items():
        for condition in category["conditions"]:
            if condition in mapping:
                raise ValueError(f"Condition appears in two disease categories: {condition}")
            mapping[condition] = {"key": key, "label": category["label"]}
    missing = sorted(conditions - set(mapping))
    extra = sorted(set(mapping) - conditions)
    if missing or extra:
        raise ValueError(
            f"Disease taxonomy coverage mismatch; missing={missing}, extra={extra}"
        )
    return mapping, taxonomy


def stage_node(stage_id: str, label: str, order: int) -> dict:
    return {
        "node_id": stage_id,
        "node_type": "STAGE",
        "label": label,
        "order": order,
        "data": {},
    }


def build_tree(
    case,
    raw_case_path: str,
    raw_sha256: str,
    category: dict,
    taxonomy: dict,
    catalog,
    raw_tokens: list[str],
) -> dict:
    truth = case.truth_map()
    grouped: dict[str, list[str]] = {}
    token_order: list[str] = []
    for token in raw_tokens:
        evidence_id = token.partition("_@_")[0]
        if evidence_id not in grouped:
            grouped[evidence_id] = []
            token_order.append(evidence_id)
        grouped[evidence_id].append(token)

    nodes: list[dict] = [
        {
            "node_id": "case.root",
            "node_type": "CASE",
            "label": case.case_id,
            "order": 0,
            "data": {
                "pathology": case.oracle.pathology,
                "disease_category": category["label"],
            },
        }
    ]
    edges: list[dict] = []

    def add_node(node: dict, parent_id: str, edge_type: str = "CONTAINS") -> None:
        nodes.append(node)
        edges.append(
            {
                "source": parent_id,
                "target": node["node_id"],
                "edge_type": edge_type,
                "order": node["order"],
            }
        )

    stages = [
        ("stage.context", "Patient context", 10),
        ("stage.initial", "Initial presentation", 20),
        ("stage.symptoms", "Symptom inquiry", 30),
        ("stage.history", "History & risk inquiry", 40),
        ("stage.diagnosis", "Diagnostic conclusion", 50),
    ]
    stage_parent = "case.root"
    for node_id, label, order in stages:
        add_node(stage_node(node_id, label, order), stage_parent, "NEXT_STAGE")
        stage_parent = node_id

    add_node(
        {
            "node_id": "context.age",
            "node_type": "CONTEXT",
            "label": "Age",
            "order": 1,
            "data": {"value": case.demographics.age, "unit": "years", "source_field": "AGE"},
        },
        "stage.context",
    )
    add_node(
        {
            "node_id": "context.sex",
            "node_type": "CONTEXT",
            "label": "Sex",
            "order": 2,
            "data": {"value": case.demographics.sex, "source_field": "SEX"},
        },
        "stage.context",
    )

    result_nodes: dict[str, str] = {}
    action_count = 0
    orphan_count = 0
    remaining = list(token_order)
    if case.initial_evidence.evidence_id in remaining:
        remaining.remove(case.initial_evidence.evidence_id)
    ordered_evidence = [case.initial_evidence.evidence_id, *remaining]

    def evidence_parent(evidence_id: str) -> str:
        nonlocal orphan_count
        definition = catalog[evidence_id]
        if evidence_id == case.initial_evidence.evidence_id:
            return "stage.initial"
        parent_id = definition.parent_evidence_id
        if parent_id and parent_id in result_nodes:
            return result_nodes[parent_id]
        if parent_id and parent_id not in grouped:
            orphan_count += 1
        return "stage.history" if definition.is_antecedent else "stage.symptoms"

    # Parents must precede children even when upstream token order does not.
    pending = ordered_evidence[:]
    resolved: set[str] = set()
    while pending:
        progressed = False
        for evidence_id in pending[:]:
            definition = catalog[evidence_id]
            parent_id = definition.parent_evidence_id
            if parent_id in grouped and parent_id not in resolved:
                continue
            action_count += 1
            action_id = f"action.{evidence_id}"
            result_id = f"observation.{evidence_id}"
            response = truth[evidence_id]
            parent = evidence_parent(evidence_id)
            add_node(
                {
                    "node_id": action_id,
                    "node_type": "ACTION",
                    "action_type": "ASK_QUESTION",
                    "label": definition.question_en,
                    "order": action_count,
                    "data": {
                        "evidence_id": evidence_id,
                        "clinical_domain": "ANTECEDENT" if definition.is_antecedent else "SYMPTOM",
                        "semantic_role": definition.semantic_role,
                        "data_type": definition.data_type.value,
                        "exposure_tier": definition.exposure_tier,
                        "source_field": "EVIDENCES",
                    },
                },
                parent,
                "NEXT_ACTION" if parent.startswith("observation.") else "CONTAINS",
            )
            add_node(
                {
                    "node_id": result_id,
                    "node_type": "OBSERVATION",
                    "label": human_readable_response(response, definition),
                    "order": action_count,
                    "data": {
                        "evidence_id": evidence_id,
                        "status": response.status.value,
                        "value": response.value,
                        "values": response.values,
                        "raw_tokens": grouped.get(evidence_id, []),
                    },
                },
                action_id,
                "RETURNS",
            )
            result_nodes[evidence_id] = result_id
            resolved.add(evidence_id)
            pending.remove(evidence_id)
            progressed = True
        if not progressed:
            # Defensive fallback for malformed hierarchy cycles. QA records the
            # orphan and attaches the remaining item to its clinical stage.
            evidence_id = pending[0]
            catalog[evidence_id] = catalog[evidence_id].model_copy(
                update={"parent_evidence_id": None}
            )
            orphan_count += 1

    diagnosis_node_ids: list[str] = []
    pathology_node_ids: list[str] = []
    for rank, item in enumerate(case.oracle.differential, start=1):
        node_id = f"diagnosis.differential.{rank:03d}"
        diagnosis_node_ids.append(node_id)
        is_ground_truth = item.condition == case.oracle.pathology
        if is_ground_truth:
            pathology_node_ids.append(node_id)
        diagnosis_data = {
            "rank": rank,
            "probability": item.probability,
            "is_ground_truth": is_ground_truth,
            "source_field": "DIFFERENTIAL_DIAGNOSIS",
        }
        if is_ground_truth:
            diagnosis_data.update(
                {
                    "severity": case.oracle.severity,
                    "disease_category_key": category["key"],
                    "disease_category": category["label"],
                }
            )
        add_node(
            {
                "node_id": node_id,
                "node_type": "DIAGNOSIS",
                "label": item.condition,
                "order": rank,
                "data": diagnosis_data,
            },
            "stage.diagnosis",
            "DIFFERENTIAL",
        )

    node_counts = Counter(node["node_type"] for node in nodes)
    return {
        "schema_version": TREE_SCHEMA_VERSION,
        "case_id": case.case_id,
        "case_hash": case.case_hash,
        "classification": {
            "pathology": case.oracle.pathology,
            "disease_category_key": category["key"],
            "disease_category": category["label"],
            "severity": case.oracle.severity,
            "taxonomy_version": taxonomy["taxonomy_version"],
            "taxonomy_source": taxonomy["taxonomy_source"],
        },
        "semantics": {
            "tree_kind": "CANONICAL_GROUND_TRUTH_EXPOSURE_TREE",
            "is_observed_clinician_chronology": False,
            "source_asserted_evidence_only": True,
            "description": "A deterministic audit tree over source-asserted DDXPlus evidence. It is not a recorded clinician workflow.",
            "supported_action_types": ["ASK_QUESTION"],
            "unsupported_source_modalities": [
                "PHYSICAL_EXAM",
                "LAB_TEST",
                "IMAGING",
                "PROCEDURE",
                "TREATMENT",
            ],
        },
        "source": {
            "raw_case_path": raw_case_path,
            "raw_sha256": raw_sha256,
            "field_lineage": {
                "AGE": ["context.age"],
                "SEX": ["context.sex"],
                "INITIAL_EVIDENCE": ["stage.initial"],
                "EVIDENCES": ["ACTION", "OBSERVATION"],
                "PATHOLOGY": pathology_node_ids,
                "DIFFERENTIAL_DIAGNOSIS": diagnosis_node_ids,
            },
        },
        "tree": {
            "root_id": "case.root",
            "nodes": nodes,
            "edges": edges,
        },
        "audit": {
            "raw_evidence_token_count": len(raw_tokens),
            "source_asserted_evidence_count": len(grouped),
            "action_node_count": action_count,
            "observation_node_count": node_counts["OBSERVATION"],
            "differential_node_count": node_counts["DIAGNOSIS"],
            "total_node_count": len(nodes),
            "orphan_hierarchy_count": orphan_count,
            "checks": {
                "all_raw_tokens_parsed": set(grouped) == set(result_nodes),
                "one_action_per_source_evidence": action_count == len(grouped),
                "one_observation_per_action": node_counts["OBSERVATION"] == action_count,
                "initial_evidence_is_source_asserted": case.initial_evidence.evidence_id in grouped,
                "diagnosis_is_classified": bool(category["key"]),
                "all_reference_diagnoses_rendered": node_counts["DIAGNOSIS"]
                == len(case.oracle.differential),
                "pathology_present_in_reference_differential": len(pathology_node_ids)
                == 1,
            },
        },
    }


def main() -> None:
    config = ddx_config()
    selection = selection_config()
    manifests = path_from_root(config["paths"]["manifests_dir"])
    raw_dir = path_from_root(config["paths"]["raw_dir"])
    processed = path_from_root(config["paths"]["processed_dir"])
    manifest = load_json(manifests / "mvp50_manifest.json")
    cases = CaseService()
    condition_names = set(cases.condition_catalog)
    category_by_condition, taxonomy = disease_category_map(condition_names)

    source_split = selection["source_split"]
    source_names = config["splits"][source_split]
    if len(source_names) != 1:
        raise ValueError("MVP raw-case projection currently expects one source parquet")
    source_name = source_names[0]
    raw_table = pq.read_table(raw_dir / source_name)
    normalized = {
        row["case_id"]: row
        for row in pq.read_table(
            processed / f"patients/{source_split}.parquet",
            filters=[("case_id", "in", [item["case_id"] for item in manifest["cases"]])],
        ).to_pylist()
    }

    raw_output = processed / "raw_cases" / selection["manifest_version"]
    tree_output = processed / "case_trees" / selection["manifest_version"]
    entries = []
    for manifest_case in manifest["cases"]:
        case_id = manifest_case["case_id"]
        match = CASE_ID_PATTERN.match(case_id)
        if not match or match.group(1).lower() != source_split:
            raise ValueError(f"Cannot resolve source row for {case_id}")
        row_number = int(match.group(2))
        raw_row = raw_table.slice(row_number - 1, 1).to_pylist()[0]
        patient = normalized[case_id]
        raw_matches = (
            raw_row["AGE"] == patient["age"]
            and raw_row["SEX"] == patient["sex"]
            and raw_row["PATHOLOGY"] == patient["pathology"]
            and raw_row["EVIDENCES"] == patient["evidence_tokens"]
            and raw_row["INITIAL_EVIDENCE"] == patient["initial_evidence"]
            and raw_row["DIFFERENTIAL_DIAGNOSIS"] == patient["oracle_differential"]
        )
        if not raw_matches:
            raise ValueError(f"Normalized patient no longer matches raw source: {case_id}")
        raw_payload = {
            "provenance": {
                "case_id": case_id,
                "source_split": source_split,
                "source_file": f"data/raw/ddxplus/original/{source_name}",
                "source_row_number_one_based": row_number,
                "raw_row_sha256": canonical_hash(raw_row),
                "projection": "Exact source values; strings remain unparsed.",
            },
            "raw_row": raw_row,
        }
        raw_path = raw_output / f"{case_id}.raw.json"
        dump_json(raw_path, raw_payload)
        raw_relative = str(raw_path.relative_to(path_from_root(".")))
        category = category_by_condition[patient["pathology"]]
        tree = build_tree(
            cases.get(case_id),
            raw_relative,
            raw_payload["provenance"]["raw_row_sha256"],
            category,
            taxonomy,
            cases.evidence_catalog.copy(),
            parse_python_literal(raw_row["EVIDENCES"]),
        )
        tree["audit"]["checks"]["raw_row_matches_normalized_patient"] = raw_matches
        tree_path = tree_output / f"{case_id}.tree.json"
        dump_json(tree_path, tree)
        entries.append(
            {
                "case_id": case_id,
                "pathology": patient["pathology"],
                "disease_category_key": category["key"],
                "disease_category": category["label"],
                "raw_case_path": raw_relative,
                "tree_path": str(tree_path.relative_to(path_from_root("."))),
                "raw_sha256": raw_payload["provenance"]["raw_row_sha256"],
                "tree_sha256": canonical_hash(tree),
                "node_count": tree["audit"]["total_node_count"],
                "source_evidence_count": tree["audit"]["source_asserted_evidence_count"],
                "all_checks_pass": all(tree["audit"]["checks"].values()),
            }
        )

    tree_manifest = {
        "manifest_name": "DDXPlus MVP-50 ground-truth exposure trees",
        "manifest_version": selection["manifest_version"],
        "tree_schema_version": TREE_SCHEMA_VERSION,
        "taxonomy_version": taxonomy["taxonomy_version"],
        "case_count": len(entries),
        "pathology_count": len({item["pathology"] for item in entries}),
        "taxonomy_condition_count": len(condition_names),
        "category_count": len({item["disease_category_key"] for item in entries}),
        "category_case_counts": dict(
            sorted(Counter(item["disease_category"] for item in entries).items())
        ),
        "all_checks_pass": all(item["all_checks_pass"] for item in entries),
        "cases": entries,
    }
    dump_json(manifests / "mvp50_tree_manifest.json", tree_manifest)
    print(
        f"Built {len(entries)} raw projections and case trees across "
        f"{tree_manifest['category_count']} disease categories"
    )


if __name__ == "__main__":
    main()
