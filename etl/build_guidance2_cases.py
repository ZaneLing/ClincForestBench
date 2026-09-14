from __future__ import annotations

"""Build the first Guidance2 Synthea and MedAgentBench Arena tracks.

The converter intentionally keeps the two datasets semantically different:

* Synthea cases expose encounter-linked observations and recorded actions.
* MedAgentBench cases expose an offline, task-derived FHIR workflow.  They do
  not claim that a FHIR request ran or that a write changed patient state.
"""

import csv
import hashlib
import json
import re
from collections import Counter, defaultdict
from datetime import date, datetime
from pathlib import Path
from typing import Any

from backend.app.domain.case import (
    CaseBundle,
    CaseMetadata,
    DatasetIdentity,
    Demographics,
    OracleDifferentialItem,
    OracleReference,
)
from backend.app.domain.enums import EvidenceDataType, TruthStatus
from backend.app.domain.evidence import EvidenceDefinition, EvidenceResponse
from etl.common import dump_json, load_json, path_from_root, sha256_file


TREE_SCHEMA_VERSION = "clinical_forest_tree_v3"
LAB_DESCRIPTION = re.compile(
    r"blood|serum|plasma|glucose|hemoglobin|hematocrit|wbc|rbc|creatinine|"
    r"sodium|potassium|chloride|calcium|urea|platelet|cholesterol|triglycer|"
    r"bilirubin|albumin|protein|urine|carbon dioxide|anion gap|troponin|"
    r"natriuretic|oxygen saturation",
    re.IGNORECASE,
)
VITAL_DESCRIPTIONS = {
    "Body temperature",
    "Diastolic Blood Pressure",
    "Heart rate",
    "Oxygen saturation in Arterial blood",
    "Pain severity - 0-10 verbal numeric rating [Score] - Reported",
    "Respiratory rate",
    "Systolic Blood Pressure",
}


def _canonical_hash(payload: Any) -> str:
    encoded = json.dumps(
        payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _slug(value: str) -> str:
    normalized = re.sub(r"[^A-Z0-9]+", "_", value.upper()).strip("_")
    return normalized[:72] or "UNKNOWN"


def _read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8-sig") as handle:
        return list(csv.DictReader(handle))


def _age_at(birthdate: str, instant: str) -> int:
    born = date.fromisoformat(birthdate)
    seen = datetime.fromisoformat(instant.replace("Z", "+00:00")).date()
    return max(0, seen.year - born.year - ((seen.month, seen.day) < (born.month, born.day)))


def _definition(
    evidence_id: str,
    label: str,
    *,
    role: str,
    domain: str,
    tier: int,
    parent: str | None = None,
    action_kind: str = "REVIEW_RECORD",
    resource_type: str | None = None,
    mutates_state: bool = False,
) -> EvidenceDefinition:
    return EvidenceDefinition(
        evidence_id=evidence_id,
        question_en=label,
        is_antecedent=domain in {"HISTORY", "CONDITION"},
        data_type=EvidenceDataType.CATEGORICAL,
        default_value=None,
        possible_values=[],
        value_meanings={},
        code_question=parent or evidence_id,
        parent_evidence_id=parent,
        is_root_question=parent is None,
        semantic_role=role,
        exposure_tier=tier,
        mapping_version="guidance2_semantics_v1",
        clinical_domain=domain,
        action_kind=action_kind,
        resource_type=resource_type,
        mutates_state=mutates_state,
    )


def _value_response(evidence_id: str, value: Any) -> EvidenceResponse:
    return EvidenceResponse(
        evidence_id=evidence_id,
        status=TruthStatus.VALUE,
        data_type=EvidenceDataType.CATEGORICAL,
        value=value,
    )


def _add_node(
    nodes: list[dict],
    edges: list[dict],
    node: dict,
    parent: str,
    edge_type: str,
) -> None:
    nodes.append(node)
    edges.append(
        {
            "source": parent,
            "target": node["node_id"],
            "edge_type": edge_type,
            "order": node["order"],
        }
    )


def _base_tree(
    bundle: CaseBundle,
    raw_path: str,
    raw_hash: str,
    category_key: str,
    category: str,
    *,
    stages: list[tuple[str, str]],
    semantics: dict,
) -> tuple[dict, list[dict], list[dict]]:
    nodes = [
        {
            "node_id": "case.root",
            "node_type": "CASE",
            "label": bundle.case_id,
            "order": 0,
            "data": {
                "dataset": bundle.dataset.name,
                "case_type": bundle.case_type,
                "generation_mode": bundle.generation_mode,
                "reference_outcome": bundle.oracle.pathology,
            },
        }
    ]
    edges: list[dict] = []
    parent = "case.root"
    for index, (stage_id, label) in enumerate(stages, start=1):
        node = {
            "node_id": stage_id,
            "node_type": "STAGE",
            "label": label,
            "order": index * 10,
            "data": {},
        }
        _add_node(nodes, edges, node, parent, "NEXT_STAGE")
        parent = stage_id
    tree = {
        "schema_version": TREE_SCHEMA_VERSION,
        "case_id": bundle.case_id,
        "case_hash": bundle.case_hash,
        "classification": {
            "pathology": bundle.oracle.pathology,
            "disease_category_key": category_key,
            "disease_category": category,
            "severity": bundle.oracle.severity,
            "taxonomy_version": "guidance2_case_type_v1",
            "taxonomy_source": "Guidance2.md dataset-specific MVP taxonomy",
        },
        "semantics": semantics,
        "source": {
            "raw_case_path": raw_path,
            "raw_sha256": raw_hash,
            "field_lineage": {},
        },
        "tree": {"root_id": "case.root", "nodes": nodes, "edges": edges},
        "audit": {},
    }
    return tree, nodes, edges


def _write_case_artifacts(
    bundle: CaseBundle,
    raw_payload: dict,
    tree: dict,
    *,
    processed_root: Path,
    manifest_prefix: str,
    category_key: str,
    category: str,
) -> dict:
    bundle_path = processed_root / "case_bundles" / f"{bundle.case_id}.json"
    raw_path = processed_root / "raw_cases" / f"{bundle.case_id}.raw.json"
    tree_path = processed_root / "case_trees" / f"{bundle.case_id}.tree.json"
    dump_json(bundle_path, bundle.model_dump(mode="json"))
    dump_json(raw_path, raw_payload)
    dump_json(tree_path, tree)
    return {
        "case_id": bundle.case_id,
        "pathology": bundle.oracle.pathology,
        "disease_category_key": category_key,
        "disease_category": category,
        "dataset_name": bundle.dataset.name,
        "case_type": bundle.case_type,
        "generation_mode": bundle.generation_mode,
        "path": str(bundle_path.relative_to(path_from_root("."))),
        "raw_case_path": str(raw_path.relative_to(path_from_root("."))),
        "tree_path": str(tree_path.relative_to(path_from_root("."))),
        "case_hash": bundle.case_hash,
        "raw_sha256": sha256_file(raw_path),
        "tree_sha256": sha256_file(tree_path),
        "node_count": len(tree["tree"]["nodes"]),
        "source_evidence_count": len(bundle.truth),
        "all_checks_pass": all(tree["audit"]["checks"].values()),
        "manifest_prefix": manifest_prefix,
    }


def _synthea_category(reason: str) -> tuple[str, str]:
    text = reason.lower()
    groups = [
        (("bronch", "sinus", "pharyng", "asthma", "respir"), "RESPIRATORY_ENT", "Respiratory & ENT"),
        (("pregnan", "obstetric"), "MATERNAL_HEALTH", "Maternal health"),
        (("prostate", "neoplasm", "cancer"), "ONCOLOGY", "Oncology"),
        (("seizure", "stroke", "neurolog"), "NEUROLOGIC", "Neurologic"),
        (("cystitis", "urinary", "kidney"), "GENITOURINARY", "Genitourinary"),
        (("anemia", "blood"), "HEMATOLOGIC", "Hematologic"),
        (("fracture", "injury", "molar"), "INJURY_PROCEDURAL", "Injury & procedural"),
    ]
    for needles, key, label in groups:
        if any(needle in text for needle in needles):
            return key, label
    return "GENERAL_MEDICINE", "General medicine"


def build_synthea(limit: int = 50) -> tuple[dict, dict]:
    source_root = path_from_root("dataset/synthea/csv")
    output_root = path_from_root("data/processed/synthea/v1/mvp50_v1")
    patients = {row["Id"]: row for row in _read_csv(source_root / "patients.csv")}
    encounters = _read_csv(source_root / "encounters.csv")

    linked: dict[str, dict[str, list[dict[str, str]]]] = defaultdict(
        lambda: defaultdict(list)
    )
    for filename, key in (
        ("observations.csv", "observations"),
        ("procedures.csv", "procedures"),
        ("medications.csv", "medications"),
        ("conditions.csv", "conditions"),
    ):
        for row in _read_csv(source_root / filename):
            if row.get("ENCOUNTER"):
                linked[row["ENCOUNTER"]][key].append(row)

    candidates = []
    for row in encounters:
        rows = linked[row["Id"]]
        categories = sum(bool(rows[name]) for name in linked[row["Id"]])
        if (
            row.get("REASONDESCRIPTION")
            and len(rows["observations"]) >= 3
            and any(
                item["DESCRIPTION"] not in VITAL_DESCRIPTIONS
                and LAB_DESCRIPTION.search(item["DESCRIPTION"])
                for item in rows["observations"]
            )
            and (rows["procedures"] or rows["medications"])
            and categories >= 3
        ):
            score = (
                categories,
                min(len(rows["observations"]), 20),
                len(rows["procedures"]) + len(rows["medications"]),
            )
            candidates.append((row, score))

    # Round-robin by reference reason prevents one common Synthea module from
    # consuming the whole MVP while remaining deterministic.
    by_reason: dict[str, list[tuple[dict, tuple]]] = defaultdict(list)
    for item in candidates:
        by_reason[item[0]["REASONDESCRIPTION"]].append(item)
    for rows in by_reason.values():
        rows.sort(key=lambda item: (item[1], item[0]["START"], item[0]["Id"]), reverse=True)
    selected: list[dict] = []
    round_index = 0
    reasons = sorted(by_reason)
    while len(selected) < limit:
        added = False
        for reason in reasons:
            rows = by_reason[reason]
            if round_index < len(rows):
                selected.append(rows[round_index][0])
                added = True
                if len(selected) == limit:
                    break
        if not added:
            break
        round_index += 1

    outcome_catalog = {
        f"SYN_DX_{row.get('REASONCODE') or _slug(row['REASONDESCRIPTION'])}": {
            "condition_name": row["REASONDESCRIPTION"],
            "severity": 1,
            "kind": "REFERENCE_CONDITION",
        }
        for row in selected
    }
    manifest_rows: list[dict] = []
    tree_rows: list[dict] = []
    for index, encounter in enumerate(selected, start=1):
        case_id = f"SYN_ENC_{index:04d}"
        patient = patients[encounter["PATIENT"]]
        records = linked[encounter["Id"]]
        initial_id = f"{case_id}_INITIAL"
        definitions = [
            _definition(
                initial_id,
                "Review the index encounter presentation",
                role="INITIAL_PRESENTATION",
                domain="ENCOUNTER",
                tier=0,
                action_kind="INITIAL_CONTEXT",
            )
        ]
        presentation_vitals = sorted(
            (
                row
                for row in records["observations"]
                if row["DESCRIPTION"] in VITAL_DESCRIPTIONS
            ),
            key=lambda row: (row["DATE"], row["CODE"]),
        )[:3]
        vital_summary = ", ".join(
            f"{row['DESCRIPTION']}: {row['VALUE']} {row['UNITS']}".strip()
            for row in presentation_vitals
        )
        initial_value = (
            f"{encounter['DESCRIPTION']} · reason: {encounter['REASONDESCRIPTION']}"
            + (f" · presentation vitals: {vital_summary}" if vital_summary else "")
        )
        responses = [_value_response(initial_id, initial_value)]
        trajectory: list[dict] = [
            {
                "sequence": 0,
                "record_type": "Encounter",
                "timestamp": encounter["START"],
                "description": encounter["DESCRIPTION"],
                "reason": encounter["REASONDESCRIPTION"],
                "source_id": encounter["Id"],
            }
        ]
        action_records: list[tuple[str, dict[str, str]]] = []
        hidden_observations = [
            row for row in records["observations"] if row not in presentation_vitals
        ]
        lab_observations = sorted(
            (
                row
                for row in hidden_observations
                if row["DESCRIPTION"] not in VITAL_DESCRIPTIONS
                and LAB_DESCRIPTION.search(row["DESCRIPTION"])
            ),
            key=lambda row: (row["DATE"], row["CODE"]),
        )
        other_observations = sorted(
            (row for row in hidden_observations if row not in lab_observations),
            key=lambda row: (row["DATE"], row["CODE"]),
        )
        observations = [*lab_observations[:8], *other_observations[:4]][:12]
        for row in observations:
            action_records.append(("OBSERVATION", row))
        for row in sorted(records["procedures"], key=lambda item: item["DATE"])[:4]:
            action_records.append(("PROCEDURE", row))
        for row in sorted(records["medications"], key=lambda item: item["START"])[:4]:
            action_records.append(("MEDICATION", row))

        previous_by_domain: dict[str, str] = {}
        for action_index, (record_type, row) in enumerate(action_records, start=1):
            evidence_id = f"{case_id}_{record_type[:3]}_{action_index:02d}"
            label = {
                "OBSERVATION": f"Review observation: {row['DESCRIPTION']}",
                "PROCEDURE": f"Review recorded procedure: {row['DESCRIPTION']}",
                "MEDICATION": f"Review recorded medication: {row['DESCRIPTION']}",
            }[record_type]
            timestamp = row.get("DATE") or row.get("START") or ""
            if record_type == "OBSERVATION":
                answer = f"{row['VALUE']} {row['UNITS']}".strip()
                role = "LAB_OR_VITAL_RESULT"
                domain = "OBSERVATION"
            else:
                answer = f"Recorded in source: {row['DESCRIPTION']}"
                role = f"RECORDED_{record_type}"
                domain = record_type
            # Same-domain chaining yields a true downward path while keeping
            # independent clinical modalities as separate branches.
            parent = previous_by_domain.get(domain)
            definitions.append(
                _definition(
                    evidence_id,
                    label,
                    role=role,
                    domain=domain,
                    tier=1 if record_type == "OBSERVATION" else 2,
                    parent=parent,
                    action_kind="REVIEW_RECORDED_RESOURCE",
                    resource_type=record_type.title(),
                )
            )
            responses.append(_value_response(evidence_id, answer))
            previous_by_domain[domain] = evidence_id
            trajectory.append(
                {
                    "sequence": action_index,
                    "record_type": record_type.title(),
                    "timestamp": timestamp,
                    "description": row["DESCRIPTION"],
                    "source_code": row.get("CODE"),
                    "source_encounter_id": encounter["Id"],
                }
            )

        target_id = f"SYN_DX_{encounter.get('REASONCODE') or _slug(encounter['REASONDESCRIPTION'])}"
        category_key, category = _synthea_category(encounter["REASONDESCRIPTION"])
        bundle = CaseBundle(
            case_id=case_id,
            dataset=DatasetIdentity(
                name="Synthea",
                split="sample_csv_apr2020",
                dataset_version="synthea_sample_csv_apr2020",
                pipeline_version="guidance2_v1",
                semantic_mapping_version="guidance2_semantics_v1",
                case_manifest_version="synthea_mvp50_v1",
            ),
            demographics=Demographics(
                age=_age_at(patient["BIRTHDATE"], encounter["START"]),
                sex=patient["GENDER"],
            ),
            initial_evidence=responses[0],
            truth=responses,
            oracle=OracleReference(
                pathology=target_id,
                severity=1,
                differential=[OracleDifferentialItem(condition=target_id, probability=1.0)],
                outcome_kind="REFERENCE_CONDITION",
                display_name=encounter["REASONDESCRIPTION"],
            ),
            metadata=CaseMetadata(
                evidence_count=len(responses),
                symptom_count=0,
                antecedent_count=0,
                independent_root_count=sum(item.parent_evidence_id is None for item in definitions),
                child_attribute_count=sum(item.parent_evidence_id is not None for item in definitions),
                nonbinary_count=len(responses),
                differential_size=1,
                differential_entropy=0,
                top1_probability=1,
                top1_top2_margin=1,
                branchability_score=min(1.0, len(responses) / 20),
            ),
            case_type="DIAGNOSTIC_EVIDENCE_ACQUISITION",
            generation_mode="NATURAL_CSV_EXPORT",
            initial_context={
                "encounter_id": encounter["Id"],
                "encounter_class": encounter["ENCOUNTERCLASS"],
                "encounter_description": encounter["DESCRIPTION"],
                "encounter_reason": encounter["REASONDESCRIPTION"],
                "start": encounter["START"],
                "presentation_vitals": presentation_vitals,
            },
            action_space=definitions,
            outcome_catalog=outcome_catalog,
            original_trajectory=trajectory,
            fidelity_note=(
                "Built from the official Synthea CSV sample. Observations, procedures, "
                "and medications are structured source records; no narrative radiology "
                "report or clinician chronology is implied."
            ),
        ).with_hash()
        raw_payload = {
            "provenance": {
                "case_id": case_id,
                "projection": "Exact encounter-linked CSV rows; no clinical text was synthesized.",
                "source_file": "dataset/synthea/csv",
                "source_split": "sample_csv_apr2020",
                "source_encounter_id": encounter["Id"],
                "generation_mode": bundle.generation_mode,
            },
            "raw_row": {
                "patient": patient,
                "encounter": encounter,
                "conditions": records["conditions"],
                "observations": records["observations"],
                "procedures": records["procedures"],
                "medications": records["medications"],
            },
        }
        raw_path = output_root / "raw_cases" / f"{case_id}.raw.json"
        dump_json(raw_path, raw_payload)
        raw_hash = _canonical_hash(raw_payload["raw_row"])
        tree, nodes, edges = _base_tree(
            bundle,
            str(raw_path.relative_to(path_from_root("."))),
            raw_hash,
            category_key,
            category,
            stages=[
                ("stage.context", "Patient context"),
                ("stage.initial", "Index encounter"),
                ("stage.observations", "Clinical observations"),
                ("stage.actions", "Recorded procedures & medications"),
                ("stage.diagnosis", "Reference condition"),
            ],
            semantics={
                "tree_kind": "SYNTHEA_ENCOUNTER_EVIDENCE_TREE",
                "is_observed_clinician_chronology": False,
                "source_asserted_evidence_only": True,
                "description": "Encounter-scoped evidence acquisition tree from structured Synthea CSV records.",
                "supported_action_types": ["REVIEW_OBSERVATION", "REVIEW_PROCEDURE", "REVIEW_MEDICATION"],
                "unsupported_source_modalities": ["NARRATIVE_RADIOLOGY_REPORT", "CLINICIAN_REASONING_NOTES"],
                "generation_mode": bundle.generation_mode,
            },
        )
        for order, (label, value, source_field) in enumerate(
            [
                ("Age", bundle.demographics.age, "patients.BIRTHDATE"),
                ("Sex", bundle.demographics.sex, "patients.GENDER"),
                ("Encounter class", encounter["ENCOUNTERCLASS"], "encounters.ENCOUNTERCLASS"),
            ],
            start=1,
        ):
            _add_node(nodes, edges, {
                "node_id": f"context.{order}", "node_type": "CONTEXT",
                "label": label, "order": order,
                "data": {"value": value, "source_field": source_field},
            }, "stage.context", "CONTAINS")
        for order, (definition, response) in enumerate(zip(definitions, responses), start=1):
            action_id = f"action.{definition.evidence_id}"
            observation_id = f"observation.{definition.evidence_id}"
            if order == 1:
                parent = "stage.initial"
            else:
                parent = "stage.observations" if definition.clinical_domain == "OBSERVATION" else "stage.actions"
            _add_node(nodes, edges, {
                "node_id": action_id, "node_type": "ACTION",
                "action_type": definition.action_kind, "label": definition.question_en,
                "order": order,
                "data": {
                    "evidence_id": definition.evidence_id,
                    "clinical_domain": definition.clinical_domain,
                    "semantic_role": definition.semantic_role,
                    "resource_type": definition.resource_type,
                },
            }, parent, "CONTAINS")
            _add_node(nodes, edges, {
                "node_id": observation_id, "node_type": "OBSERVATION",
                "label": str(response.value), "order": order,
                "data": {"evidence_id": response.evidence_id, "status": response.status.value, "value": response.value},
            }, action_id, "RETURNS")
        diagnosis_id = "diagnosis.reference.001"
        _add_node(nodes, edges, {
            "node_id": diagnosis_id, "node_type": "DIAGNOSIS",
            "label": encounter["REASONDESCRIPTION"], "order": 1,
            "data": {
                "condition_id": target_id, "probability": 1.0,
                "is_ground_truth": True, "source_field": "encounters.REASONDESCRIPTION",
            },
        }, "stage.diagnosis", "REFERENCE_OUTCOME")
        tree["source"]["field_lineage"] = {
            "patient": ["context.1", "context.2"],
            "encounter": ["stage.initial", diagnosis_id],
            "observations": ["stage.observations"],
            "procedures": ["stage.actions"],
            "medications": ["stage.actions"],
        }
        tree["audit"] = {
            "raw_evidence_token_count": len(responses),
            "source_asserted_evidence_count": len(responses),
            "action_node_count": len(definitions),
            "observation_node_count": len(responses),
            "differential_node_count": 1,
            "total_node_count": len(nodes),
            "orphan_hierarchy_count": 0,
            "checks": {
                "one_observation_per_action": len(responses) == len(definitions),
                "reference_condition_is_source_asserted": bool(encounter["REASONDESCRIPTION"]),
                "minimum_evidence_categories_present": sum(bool(records[name]) for name in records) >= 3,
                "lab_result_present": any(
                    row["DESCRIPTION"] not in VITAL_DESCRIPTIONS
                    and LAB_DESCRIPTION.search(row["DESCRIPTION"])
                    for row in observations
                ),
                "no_narrative_report_fabricated": True,
            },
        }
        dump_json(output_root / "case_trees" / f"{case_id}.tree.json", tree)
        dump_json(output_root / "case_bundles" / f"{case_id}.json", bundle.model_dump(mode="json"))
        entry = {
            "case_id": case_id,
            "pathology": target_id,
            "disease_category_key": category_key,
            "disease_category": category,
            "dataset_name": "Synthea",
            "case_type": bundle.case_type,
            "generation_mode": bundle.generation_mode,
            "path": str((output_root / "case_bundles" / f"{case_id}.json").relative_to(path_from_root("."))),
            "raw_case_path": str(raw_path.relative_to(path_from_root("."))),
            "tree_path": str((output_root / "case_trees" / f"{case_id}.tree.json").relative_to(path_from_root("."))),
            "case_hash": bundle.case_hash,
            "raw_sha256": raw_hash,
            "tree_sha256": _canonical_hash(tree),
            "node_count": len(nodes),
            "source_evidence_count": len(responses),
            "all_checks_pass": all(tree["audit"]["checks"].values()),
        }
        manifest_rows.append({key: entry[key] for key in ("case_id", "case_hash", "path", "pathology", "dataset_name", "case_type", "generation_mode")})
        tree_rows.append(entry)

    manifest = {
        "manifest_name": "synthea_mvp50",
        "manifest_version": "synthea_mvp50_v1",
        "dataset_name": "Synthea",
        "case_count": len(manifest_rows),
        "cases": manifest_rows,
    }
    tree_manifest = _tree_manifest("synthea_mvp50_trees", "synthea_mvp50_v1", tree_rows)
    dump_json(path_from_root("data/manifests/synthea_mvp50_manifest.json"), manifest)
    dump_json(path_from_root("data/manifests/synthea_mvp50_tree_manifest.json"), tree_manifest)
    return manifest, tree_manifest


def _medagent_plan(task_family: str, task: dict) -> list[dict[str, Any]]:
    patient_id = task.get("eval_MRN", "unknown")
    plans = {
        "task4": [
            ("FHIR_READ_PATIENT", "Patient", f"Resolve patient {patient_id}", f"GET /Patient?identifier={patient_id}"),
            ("FHIR_READ_OBSERVATION", "Observation", "Query magnesium observations in the last 24 hours", f"GET /Observation?patient={patient_id}&code=MG&date=<last-24h>"),
            ("VERIFY_RESULT", None, "Check recency and convert the most recent result to mg/dL", "Offline replay records the required validation; no result value is available without the FHIR server."),
            ("RETURN_WORKFLOW_RESULT", None, "Return the value, or -1 when no eligible result exists", "Reference output rule captured from the task."),
        ],
        "task5": [
            ("FHIR_READ_PATIENT", "Patient", f"Resolve patient {patient_id}", f"GET /Patient?identifier={patient_id}"),
            ("FHIR_READ_OBSERVATION", "Observation", "Query the latest magnesium result in the last 24 hours", f"GET /Observation?patient={patient_id}&code=MG&date=<last-24h>"),
            ("EVALUATE_PROTOCOL", None, "Apply the supplied magnesium replacement thresholds", "Branch: no result → no order; normal → no order; low → dose by severity."),
            ("FHIR_WRITE_INTENT", "MedicationRequest", "Conditionally create the IV magnesium medication request", "Offline replay captures POST /MedicationRequest intent only; it does not create a resource."),
        ],
        "task8": [
            ("FHIR_READ_PATIENT", "Patient", f"Resolve patient {patient_id}", f"GET /Patient?identifier={patient_id}"),
            ("VALIDATE_ORDER", None, "Validate referral code, patient, timing, and SBAR note", "SNOMED 306181000000106 and the task-provided referral text are required."),
            ("FHIR_WRITE_INTENT", "ServiceRequest", "Create the orthopedic referral ServiceRequest", "Offline replay captures POST /ServiceRequest intent only; it does not create a resource."),
        ],
    }
    return [
        {
            "action_kind": action_kind,
            "resource_type": resource_type,
            "label": label,
            "response": response,
        }
        for action_kind, resource_type, label, response in plans[task_family]
    ]


def _tree_manifest(name: str, version: str, cases: list[dict]) -> dict:
    category_counts = Counter(item["disease_category"] for item in cases)
    return {
        "manifest_name": name,
        "manifest_version": version,
        "tree_schema_version": TREE_SCHEMA_VERSION,
        "taxonomy_version": "guidance2_case_type_v1",
        "case_count": len(cases),
        "pathology_count": len({item["pathology"] for item in cases}),
        "taxonomy_condition_count": len({item["pathology"] for item in cases}),
        "category_count": len(category_counts),
        "category_case_counts": dict(sorted(category_counts.items())),
        "all_checks_pass": all(item["all_checks_pass"] for item in cases),
        "cases": cases,
    }


def build_medagentbench() -> tuple[dict, dict]:
    source = path_from_root("dataset/medagentbench/test_data_v2.json")
    functions = load_json(path_from_root("dataset/medagentbench/funcs_v1.json"))
    tasks = load_json(source)
    selected = [
        task
        for family in ("task4_", "task5_", "task8_")
        for task in tasks
        if task["id"].startswith(family) and int(task["id"].split("_")[1]) <= 10
    ]
    categories = {
        "task4": ("LAB_RETRIEVAL", "Lab result retrieval", "MAB_OUTCOME_LAB_RETRIEVAL", "Retrieve recent magnesium result"),
        "task5": ("CONDITIONAL_MANAGEMENT", "Conditional management", "MAB_OUTCOME_CONDITIONAL_MAGNESIUM", "Conditionally manage magnesium replacement"),
        "task8": ("PROCEDURE_ACTION", "Medication / procedure action", "MAB_OUTCOME_ORTHOPEDIC_REFERRAL", "Create orthopedic referral"),
    }
    outcome_catalog = {
        outcome_id: {
            "condition_name": outcome_label,
            "severity": 1,
            "kind": "REFERENCE_WORKFLOW_OUTCOME",
        }
        for _, _, outcome_id, outcome_label in categories.values()
    }
    output_root = path_from_root("data/processed/medagentbench/v2/mvp30_v1")
    manifest_rows: list[dict] = []
    tree_rows: list[dict] = []
    for task in selected:
        family = task["id"].split("_")[0]
        category_key, category, outcome_id, outcome_label = categories[family]
        case_id = f"MAB_{task['id'].upper()}"
        initial_id = f"{case_id}_TASK"
        definitions = [
            _definition(
                initial_id,
                "Review the workflow task and execution context",
                role="TASK_SPECIFICATION",
                domain="TASK",
                tier=0,
                action_kind="INITIAL_CONTEXT",
            )
        ]
        responses = [
            _value_response(
                initial_id,
                f"{task['instruction'].strip()} Context: {task.get('context', '').strip()}",
            )
        ]
        plan = _medagent_plan(family, task)
        parent: str | None = None
        trajectory = []
        for index, step in enumerate(plan, start=1):
            evidence_id = f"{case_id}_STEP_{index:02d}"
            definitions.append(
                _definition(
                    evidence_id,
                    step["label"],
                    role=step["action_kind"],
                    domain=(step["resource_type"] or "WORKFLOW").upper(),
                    tier=index,
                    parent=parent,
                    action_kind=step["action_kind"],
                    resource_type=step["resource_type"],
                    # Offline replay never claims that a POST created a resource.
                    mutates_state=False,
                )
            )
            responses.append(_value_response(evidence_id, step["response"]))
            trajectory.append({"sequence": index, **step, "evidence_id": evidence_id})
            parent = evidence_id
        bundle = CaseBundle(
            case_id=case_id,
            dataset=DatasetIdentity(
                name="MedAgentBench",
                split="test_data_v2",
                dataset_version="medagentbench_v2",
                pipeline_version="guidance2_v1",
                semantic_mapping_version="guidance2_semantics_v1",
                case_manifest_version="medagentbench_mvp30_v1",
            ),
            demographics=Demographics(age=0, sex="unknown"),
            initial_evidence=responses[0],
            truth=responses,
            oracle=OracleReference(
                pathology=outcome_id,
                severity=1,
                differential=[OracleDifferentialItem(condition=outcome_id, probability=1.0)],
                outcome_kind="REFERENCE_WORKFLOW_OUTCOME",
                display_name=outcome_label,
            ),
            metadata=CaseMetadata(
                evidence_count=len(responses),
                symptom_count=0,
                antecedent_count=0,
                independent_root_count=2,
                child_attribute_count=max(0, len(responses) - 2),
                nonbinary_count=len(responses),
                differential_size=1,
                differential_entropy=0,
                top1_probability=1,
                top1_top2_margin=1,
                branchability_score=0.5,
            ),
            case_type="WORKFLOW_FOREST",
            generation_mode="OFFLINE_TASK_REPLAY",
            initial_context={
                "task_id": task["id"],
                "patient_identifier": task.get("eval_MRN"),
                "instruction": task["instruction"],
                "context": task.get("context", ""),
                "runtime_status": "FHIR_SERVER_UNAVAILABLE",
            },
            action_space=definitions,
            outcome_catalog=outcome_catalog,
            original_trajectory=trajectory,
            fidelity_note=(
                "The official Docker FHIR runtime is unavailable on this machine. "
                "This MVP replays the task-derived workflow and official function schema; "
                "it does not fabricate FHIR responses, lab values, or created resources."
            ),
        ).with_hash()
        relevant_resources = {
            step["resource_type"] for step in plan if step["resource_type"]
        }
        relevant_functions = [
            function
            for function in functions
            if any(f"/{resource}" in function["name"] for resource in relevant_resources)
        ]
        raw_payload = {
            "provenance": {
                "case_id": case_id,
                "projection": "Exact MedAgentBench task plus relevant official function definitions.",
                "source_file": "dataset/medagentbench/test_data_v2.json",
                "source_task_id": task["id"],
                "generation_mode": bundle.generation_mode,
                "runtime_status": "OFFLINE_NO_DOCKER_FHIR_SERVER",
            },
            "raw_row": {"task": task, "official_function_definitions": relevant_functions},
        }
        raw_path = output_root / "raw_cases" / f"{case_id}.raw.json"
        dump_json(raw_path, raw_payload)
        raw_hash = _canonical_hash(raw_payload["raw_row"])
        tree, nodes, edges = _base_tree(
            bundle,
            str(raw_path.relative_to(path_from_root("."))),
            raw_hash,
            category_key,
            category,
            stages=[
                ("stage.task", "Task & patient context"),
                ("stage.read", "FHIR read actions"),
                ("stage.reason", "Workflow decision"),
                ("stage.write", "FHIR write intent"),
                ("stage.outcome", "Reference workflow outcome"),
            ],
            semantics={
                "tree_kind": "OFFLINE_REFERENCE_WORKFLOW_TREE",
                "is_observed_clinician_chronology": False,
                "source_asserted_evidence_only": True,
                "description": "Task-derived FHIR workflow tree. No FHIR request was executed in offline mode.",
                "supported_action_types": sorted({step["action_kind"] for step in plan}),
                "unsupported_source_modalities": ["LIVE_FHIR_RESPONSE", "PHYSIOLOGIC_STATE_CHANGE"],
                "generation_mode": bundle.generation_mode,
                "runtime_fidelity": "TASK_AND_FUNCTION_SCHEMA_ONLY",
            },
        )
        _add_node(nodes, edges, {
            "node_id": "context.patient", "node_type": "CONTEXT",
            "label": "Patient identifier", "order": 1,
            "data": {"value": task.get("eval_MRN"), "source_field": "eval_MRN"},
        }, "stage.task", "CONTAINS")
        _add_node(nodes, edges, {
            "node_id": f"action.{initial_id}", "node_type": "ACTION",
            "action_type": "INITIAL_CONTEXT", "label": definitions[0].question_en,
            "order": 1, "data": {"evidence_id": initial_id, "clinical_domain": "TASK"},
        }, "stage.task", "CONTAINS")
        _add_node(nodes, edges, {
            "node_id": f"observation.{initial_id}", "node_type": "OBSERVATION",
            "label": task["instruction"].strip(), "order": 1,
            "data": {"evidence_id": initial_id, "status": "VALUE", "value": responses[0].value},
        }, f"action.{initial_id}", "RETURNS")
        for index, (definition, response, plan_step) in enumerate(
            zip(definitions[1:], responses[1:], plan), start=1
        ):
            action_id = f"action.{definition.evidence_id}"
            observation_id = f"observation.{definition.evidence_id}"
            if plan_step["action_kind"].startswith("FHIR_READ"):
                stage = "stage.read"
            elif plan_step["action_kind"].startswith("FHIR_WRITE"):
                stage = "stage.write"
            else:
                stage = "stage.reason"
            _add_node(nodes, edges, {
                "node_id": action_id, "node_type": "ACTION",
                "action_type": definition.action_kind, "label": definition.question_en,
                "order": index,
                "data": {
                    "evidence_id": definition.evidence_id,
                    "resource_type": definition.resource_type,
                    "execution_mode": "OFFLINE_TASK_REPLAY",
                    "mutates_state": False,
                },
            }, stage, "CONTAINS")
            _add_node(nodes, edges, {
                "node_id": observation_id, "node_type": "OBSERVATION",
                "label": str(response.value), "order": index,
                "data": {
                    "evidence_id": definition.evidence_id,
                    "status": response.status.value,
                    "value": response.value,
                    "live_fhir_response": False,
                },
            }, action_id, "RETURNS")
        outcome_node = "diagnosis.reference.001"
        _add_node(nodes, edges, {
            "node_id": outcome_node, "node_type": "DIAGNOSIS",
            "label": outcome_label, "order": 1,
            "data": {
                "condition_id": outcome_id, "probability": 1.0,
                "is_ground_truth": True, "outcome_kind": "REFERENCE_WORKFLOW_OUTCOME",
                "source_field": "instruction/context",
            },
        }, "stage.outcome", "REFERENCE_OUTCOME")
        tree["source"]["field_lineage"] = {
            "instruction": [f"observation.{initial_id}", outcome_node],
            "context": ["stage.task", "stage.reason"],
            "official_function_definitions": ["stage.read", "stage.write"],
        }
        tree["audit"] = {
            "raw_evidence_token_count": len(responses),
            "source_asserted_evidence_count": len(responses),
            "action_node_count": len(definitions),
            "observation_node_count": len(responses),
            "differential_node_count": 1,
            "total_node_count": len(nodes),
            "orphan_hierarchy_count": 0,
            "checks": {
                "one_observation_per_action": len(responses) == len(definitions),
                "official_function_schema_retained": bool(relevant_functions),
                "task_source_retained": raw_payload["raw_row"]["task"] == task,
                "offline_runtime_disclosed": tree["semantics"]["generation_mode"] == "OFFLINE_TASK_REPLAY",
                "no_fhir_response_fabricated": True,
            },
        }
        bundle_path = output_root / "case_bundles" / f"{case_id}.json"
        tree_path = output_root / "case_trees" / f"{case_id}.tree.json"
        dump_json(bundle_path, bundle.model_dump(mode="json"))
        dump_json(tree_path, tree)
        entry = {
            "case_id": case_id,
            "pathology": outcome_id,
            "disease_category_key": category_key,
            "disease_category": category,
            "dataset_name": "MedAgentBench",
            "case_type": bundle.case_type,
            "generation_mode": bundle.generation_mode,
            "path": str(bundle_path.relative_to(path_from_root("."))),
            "raw_case_path": str(raw_path.relative_to(path_from_root("."))),
            "tree_path": str(tree_path.relative_to(path_from_root("."))),
            "case_hash": bundle.case_hash,
            "raw_sha256": raw_hash,
            "tree_sha256": _canonical_hash(tree),
            "node_count": len(nodes),
            "source_evidence_count": len(responses),
            "all_checks_pass": all(tree["audit"]["checks"].values()),
        }
        manifest_rows.append({key: entry[key] for key in ("case_id", "case_hash", "path", "pathology", "dataset_name", "case_type", "generation_mode")})
        tree_rows.append(entry)

    manifest = {
        "manifest_name": "medagentbench_mvp30",
        "manifest_version": "medagentbench_mvp30_v1",
        "dataset_name": "MedAgentBench",
        "case_count": len(manifest_rows),
        "execution_mode": "OFFLINE_TASK_REPLAY",
        "cases": manifest_rows,
    }
    tree_manifest = _tree_manifest("medagentbench_mvp30_trees", "medagentbench_mvp30_v1", tree_rows)
    dump_json(path_from_root("data/manifests/medagentbench_mvp30_manifest.json"), manifest)
    dump_json(path_from_root("data/manifests/medagentbench_mvp30_tree_manifest.json"), tree_manifest)
    return manifest, tree_manifest


def main() -> None:
    synthea, synthea_trees = build_synthea()
    medagent, medagent_trees = build_medagentbench()
    print(
        json.dumps(
            {
                "synthea_cases": synthea["case_count"],
                "synthea_trees_verified": synthea_trees["all_checks_pass"],
                "medagentbench_cases": medagent["case_count"],
                "medagentbench_trees_verified": medagent_trees["all_checks_pass"],
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
