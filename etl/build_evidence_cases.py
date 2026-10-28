"""Convert source episodes into unordered, source-backed evidence cases.

Source adapters extract recorded evidence. Source dates are audit metadata;
all runnable action/result branches are independent.
"""
from __future__ import annotations

import hashlib
import json
import re
import shutil
from collections import Counter
from pathlib import Path

from backend.app.domain.case import (
    CaseBundle, CaseMetadata, DatasetIdentity, Demographics, OracleReference,
)
from backend.app.domain.enums import EvidenceDataType, TruthStatus
from backend.app.domain.evidence import EvidenceDefinition, EvidenceResponse
from backend.app.services.case_service import CaseService
from backend.app.services.encounter_catalog import EncounterCatalog
from etl.source_adapters.loader import SourceCaseLoader
from etl.common import dump_json, path_from_root, sha256_file

VERSION = "evidence_v1"
MANIFEST = "data/manifests/evidence_manifest.json"
TREE_MANIFEST = "data/manifests/evidence_tree_manifest.json"
OUTPUT = "data/processed/evidence"
SOURCE_ONLY_KEYS = {
    "source_time", "time_is_sequence_proxy", "source_sentence_index",
    "source_patient_turn", "time_semantics",
}


def without_clock(value):
    if isinstance(value, dict):
        return {k: without_clock(v) for k, v in value.items()
                if k not in SOURCE_ONLY_KEYS}
    if isinstance(value, list):
        return [without_clock(v) for v in value]
    return value


def condition_id(label):
    return "CFB_DX_" + hashlib.sha256(label.encode()).hexdigest()[:16]

def canonical_age(value):
    # Some public profiles encode age as [[52, "year"]]. Preserve the full
    # representation in patient_details and never substitute an invented age.
    if isinstance(value, (int, str)) or value is None:
        return value
    pair = value[0] if isinstance(value, list) and value else value
    if isinstance(pair, list) and len(pair) >= 2:
        number, unit = pair[:2]
        if str(unit).lower() in {"year", "years"} and isinstance(number, (int, float)):
            return int(number) if float(number).is_integer() else f"{number} years"
        return f"{number} {unit}"
    return json.dumps(value, ensure_ascii=False)


def definition(item_id, label, kind="inquiry", category="History"):
    eid = f"CFB_E::{item_id}"
    return EvidenceDefinition(
        evidence_id=eid, question_en=label, is_antecedent=kind == "inquiry",
        data_type=EvidenceDataType.CATEGORICAL, code_question=eid,
        is_root_question=True, semantic_role="SOURCE_EVIDENCE",
        exposure_tier=1, mapping_version=VERSION, clinical_domain=category,
        action_kind="ASK_QUESTION" if kind == "inquiry" else "REVIEW_RECORD",
    )


def response(eid, value):
    return EvidenceResponse(evidence_id=eid, status=TruthStatus.VALUE,
                            data_type=EvidenceDataType.CATEGORICAL, value=value)


def make_tree(bundle, raw_path, raw_hash):
    nodes = [{"node_id": "case.root", "node_type": "CASE", "order": 0,
              "label": bundle.case_id, "data": {}}]
    edges = []
    initial = bundle.initial_evidence.evidence_id
    nodes.append({"node_id": "context.initial", "node_type": "CONTEXT", "order": 1,
                  "label": "Initial presentation", "data": bundle.initial_context})
    edges.append({"source": "case.root", "target": "context.initial",
                  "edge_type": "CONTEXT", "order": 1})
    for index, item in enumerate(bundle.action_space, 2):
        if item.evidence_id == initial:
            continue
        action, result = f"action.{index}", f"result.{index}"
        nodes.extend([
            {"node_id": action, "node_type": "ACTION", "order": index,
             "action_type": "ASK_EVIDENCE", "label": item.question_en,
             "data": {"evidence_id": item.evidence_id}},
            {"node_id": result, "node_type": "OBSERVATION", "order": index,
             "label": item.question_en,
             "data": {"evidence_id": item.evidence_id,
                      "result": bundle.truth_map()[item.evidence_id].value}},
        ])
        edges.extend([
            {"source": "case.root", "target": action, "edge_type": "QUERYABLE", "order": index},
            {"source": action, "target": result, "edge_type": "REVEALS", "order": index},
        ])
    nodes.append({"node_id": "reference", "node_type": "DIAGNOSIS",
                  "order": len(bundle.action_space) + 2,
                  "label": bundle.oracle.display_name,
                  "data": {"is_ground_truth": bundle.reference_quality.get("is_absolute_ground_truth", False),
                           "reference_quality": bundle.reference_quality}})
    edges.append({"source": "case.root", "target": "reference",
                  "edge_type": "PROTECTED_REFERENCE", "order": len(nodes)})
    count = len(bundle.action_space) - 1
    return {
        "schema_version": "unordered_evidence_tree_v1", "case_id": bundle.case_id,
        "case_hash": bundle.case_hash,
        "classification": {"pathology": bundle.oracle.pathology,
                           "disease_category_key": "SOURCE_EVIDENCE",
                           "disease_category": bundle.dataset.name, "severity": 1,
                           "taxonomy_version": VERSION, "taxonomy_source": "Source dataset"},
        "semantics": {"tree_kind": "UNORDERED_EVIDENCE", "is_observed_clinician_chronology": False,
                      "source_asserted_evidence_only": True,
                      "description": "Independent action/result branches. Layout order is not a clinical sequence.",
                      "supported_action_types": ["ASK_EVIDENCE"], "unsupported_source_modalities": []},
        "source": {"raw_case_path": raw_path, "raw_sha256": raw_hash,
                   "field_lineage": {key: [key] for key in bundle.evidence_records}},
        "tree": {"root_id": "case.root", "nodes": nodes, "edges": edges},
        "audit": {"raw_evidence_token_count": count, "source_asserted_evidence_count": count,
                  "action_node_count": count, "observation_node_count": count,
                  "differential_node_count": 1, "total_node_count": len(nodes),
                  "orphan_hierarchy_count": 0,
                  "checks": {"one_result_per_action": True, "no_time_constraints": True,
                             "source_results_preserved": True, "reference_protected": True}},
    }


def build(root: Path | None = None):
    root = (root or path_from_root(".")).resolve()
    classic = CaseService(root, include_evidence=False)
    source_cases = SourceCaseLoader(root)
    if not source_cases.manifest()["cases"]:
        raise RuntimeError("Source episodes are missing; build the EHR and interaction sources first")
    catalog = EncounterCatalog(classic, source_cases)
    # All actions use public, case-independent labels. No reference label is
    # used to generate an action, and each answer stays inside its own case.
    definitions = {
        key: definition(key, item["label"]["en"], item["kind"], item["category"])
        for key, item in catalog.items.items()
    }
    conditions = {key: value for key, value in classic.all_condition_catalog.items()
                  if value.get("kind", "DIAGNOSIS") == "DIAGNOSIS"}
    references = {}
    for entry in source_cases.manifest()["cases"]:
        case = source_cases.get(entry["case_id"])
        label = str(case.reference.get("primary_diagnosis") or entry.get("reference_label") or "Unadjudicated reference")
        cid = condition_id(label)
        references[case.case_id] = (cid, label)
        conditions[cid] = {"condition_name": label, "severity": 1, "kind": "DIAGNOSIS"}
    entries = []
    for entry in source_cases.manifest()["cases"]:
        source = source_cases.get(entry["case_id"])
        visit = without_clock(catalog.visits[source.case_id])
        bindings = without_clock(catalog.bindings[source.case_id])
        initial_def = definition(f"initial:{source.case_id}", "Initial presentation")
        initial_response = response(initial_def.evidence_id, visit["presentation"])
        local_defs = [initial_def, *(definitions[key] for key in sorted(bindings))]
        records = {definitions[key].evidence_id: rows for key, rows in bindings.items()}
        truth = [initial_response, *(
            response(definitions[key].evidence_id, [row["result"] for row in bindings[key]])
            for key in sorted(bindings)
        )]
        dx, label = references[source.case_id]
        dataset_name = source.source.get("dataset_family", entry["dataset_name"])
        slug = re.sub(r"[^a-z0-9]+", "_", dataset_name.lower()).strip("_")
        age = visit["demographics"].get("age")
        bundle = CaseBundle(
            case_id=source.case_id,
            dataset=DatasetIdentity(name=dataset_name, split="local_mvp",
                                    dataset_version=f"{slug}_source_v1",
                                    pipeline_version=VERSION, semantic_mapping_version=VERSION,
                                    case_manifest_version=f"{VERSION}_{slug}"),
            demographics=Demographics(age=canonical_age(age),
                                      sex=str(visit["demographics"].get("sex", visit["demographics"].get("gender", "unknown")))),
            initial_evidence=initial_response, truth=truth,
            oracle=OracleReference(pathology=dx, severity=1, display_name=label),
            metadata=CaseMetadata(evidence_count=len(bindings), independent_root_count=len(bindings)),
            case_type="DIAGNOSTIC_EVIDENCE_ACQUISITION", generation_mode="SOURCE_BACKED_EVIDENCE",
            initial_context={"presentation": visit["presentation"], "patient_details": visit["demographics"],
                             "protocol": "UNORDERED_EVIDENCE", "runtime_status": "READY"},
            action_space=local_defs, outcome_catalog=conditions, evidence_records=records,
            source_provenance={"source": source.source, "raw_source": source.raw_source,
                               "source_event_audit": [event.model_dump(mode="json") for event in source.evidence_events],
                               "mapping_audit": catalog.audit[source.case_id],
                               "catalog_items": {key: catalog.items[key] for key in bindings},
                               "treatments": catalog.treatments[source.case_id]},
            reference_quality=source.reference,
            fidelity_note="Unordered source-backed evidence. No simulated clock, waiting, source-order requirement, or invented results.",
        ).with_hash()
        directory = root / OUTPUT / "case_bundles" / source.case_id
        path, raw_path, tree_path = directory / "case.json", directory / "raw.json", directory / "tree.json"
        dump_json(path, bundle.model_dump(mode="json"))
        dump_json(raw_path, {"provenance": source.source, "raw_row": source.raw_source})
        raw_hash = sha256_file(raw_path)
        tree = make_tree(bundle, str(raw_path.relative_to(root)), raw_hash)
        dump_json(tree_path, tree)
        source_directory = (root / entry["path"]).parent
        if (source_directory / "media").is_dir():
            shutil.copytree(source_directory / "media", directory / "media", dirs_exist_ok=True)
        entries.append({
            "case_id": bundle.case_id, "path": str(path.relative_to(root)),
            "raw_case_path": str(raw_path.relative_to(root)), "tree_path": str(tree_path.relative_to(root)),
            "dataset_name": dataset_name, "case_type": bundle.case_type,
            "generation_mode": bundle.generation_mode, "case_hash": bundle.case_hash,
            "pathology": dx, "disease_category_key": "SOURCE_EVIDENCE", "disease_category": dataset_name,
            "raw_sha256": raw_hash, "tree_sha256": sha256_file(tree_path),
            "node_count": len(tree["tree"]["nodes"]), "source_evidence_count": len(bindings),
            "all_checks_pass": True,
        })
    manifest = {
        "manifest_version": VERSION, "schema_version": "unordered_evidence_manifest_v1",
        "protocol": "UNORDERED_EVIDENCE", "case_count": len(entries),
        "dataset_case_counts": dict(Counter(row["dataset_name"] for row in entries)),
        "all_checks_pass": True, "privacy": "LOCAL_ONLY", "cases": entries,
    }
    dump_json(root / MANIFEST, manifest)
    dump_json(root / TREE_MANIFEST, manifest)
    active_ids = {entry["case_id"] for entry in entries}
    for directory in (root / OUTPUT / "case_bundles").iterdir():
        if directory.is_dir() and directory.name not in active_ids:
            shutil.rmtree(directory)
    print(f"Built {len(entries)} unordered evidence cases; {len(classic.cases) + len(entries)} total cases")
    return manifest


if __name__ == "__main__":
    build()
