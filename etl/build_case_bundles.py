from __future__ import annotations

import csv
import json
import random

import pyarrow as pa
import pyarrow.compute as pc
import pyarrow.parquet as pq

from backend.app.domain.case import (
    CaseBundle,
    CaseMetadata,
    DatasetIdentity,
    Demographics,
    OracleDifferentialItem,
    OracleReference,
)
from backend.app.domain.enums import EvidenceDataType
from backend.app.domain.evidence import (
    DATA_TYPE_MAP,
    EvidenceDefinition,
    build_dense_truth,
)
from etl.common import (
    ddx_config,
    dump_json,
    load_json,
    parse_python_literal,
    path_from_root,
    selection_config,
)


def load_catalog(raw_dir, mapping_version: str):
    raw = load_json(raw_dir / "release_evidences.json")
    catalog = {}
    for evidence_id, item in raw.items():
        is_root = (
            item["code_question"] == evidence_id
            or item["code_question"] not in raw
        )
        catalog[evidence_id] = EvidenceDefinition(
            evidence_id=evidence_id,
            question_en=item["question_en"],
            is_antecedent=item["is_antecedent"],
            data_type=DATA_TYPE_MAP[item["data_type"]],
            default_value=item["default_value"],
            possible_values=item.get("possible-values", []),
            value_meanings=item.get("value_meaning", {}),
            code_question=item["code_question"],
            parent_evidence_id=None if is_root else item["code_question"],
            is_root_question=is_root,
            semantic_role="OTHER_ANTECEDENT"
            if item["is_antecedent"]
            else ("PRESENTING_SYMPTOM" if is_root else "SYMPTOM_ATTRIBUTE"),
            exposure_tier=3 if item["is_antecedent"] else (2 if is_root else 1),
            mapping_version=mapping_version,
        )
    return catalog


def main() -> None:
    config = ddx_config()
    selection = selection_config()
    processed = path_from_root(config["paths"]["processed_dir"])
    manifests = path_from_root(config["paths"]["manifests_dir"])
    raw_dir = path_from_root(config["paths"]["raw_dir"])
    selected_table = pq.read_table(manifests / "mvp50_case_selection.parquet")
    selected = {row["case_id"]: row for row in selected_table.to_pylist()}
    case_ids = list(selected)
    patient_table = pq.read_table(
        processed / f"patients/{selection['source_split']}.parquet",
        filters=[("case_id", "in", case_ids)],
    )
    patients = {row["case_id"]: row for row in patient_table.to_pylist()}
    conditions = load_json(raw_dir / "release_conditions.json")
    catalog = load_catalog(
        raw_dir, config["dataset"]["semantic_mapping_version"]
    )

    bundle_dir = processed / "case_bundles" / selection["manifest_version"]
    bundle_dir.mkdir(parents=True, exist_ok=True)
    manifest_entries = []
    truth_rows = []
    for case_id in case_ids:
        patient = patients[case_id]
        quality = selected[case_id]
        dense_truth = build_dense_truth(
            parse_python_literal(patient["evidence_tokens"]), catalog
        )
        truth_map = {item.evidence_id: item for item in dense_truth}
        differential = [
            OracleDifferentialItem(condition=condition, probability=probability)
            for condition, probability in parse_python_literal(
                patient["oracle_differential"]
            )
        ]
        bundle = CaseBundle(
            case_id=case_id,
            dataset=DatasetIdentity(
                name=config["dataset"]["name"],
                split=patient["split"],
                dataset_version=config["dataset"]["dataset_version"],
                pipeline_version=config["dataset"]["pipeline_version"],
                semantic_mapping_version=config["dataset"][
                    "semantic_mapping_version"
                ],
                case_manifest_version=selection["manifest_version"],
            ),
            demographics=Demographics(age=patient["age"], sex=patient["sex"]),
            initial_evidence=truth_map[patient["initial_evidence"]],
            truth=dense_truth,
            oracle=OracleReference(
                pathology=patient["pathology"],
                severity=int(conditions[patient["pathology"]]["severity"]),
                differential=differential,
            ),
            metadata=CaseMetadata(
                **{
                    key: quality[key]
                    for key in CaseMetadata.model_fields
                    if key != "branchability_score"
                },
                branchability_score=quality["branchability_score"],
            ),
        ).with_hash()
        path = bundle_dir / f"{case_id}.json"
        dump_json(path, bundle.model_dump(mode="json"))
        manifest_entries.append(
            {
                "case_id": case_id,
                "case_hash": bundle.case_hash,
                "path": str(path.relative_to(path_from_root("."))),
                "pathology": patient["pathology"],
            }
        )
        for truth in dense_truth:
            truth_rows.append(
                {
                    "case_id": case_id,
                    "evidence_id": truth.evidence_id,
                    "status": truth.status.value,
                    "data_type": truth.data_type.value,
                    # DDXPlus values are heterogeneous (bool, number and code).
                    # JSON columns preserve their native meaning in a Parquet-safe
                    # representation and can be decoded without guessing types.
                    "value_json": json.dumps(truth.value),
                    "values_json": json.dumps(truth.values),
                }
            )

    pq.write_table(
        pa.Table.from_pylist(truth_rows),
        processed / "case_evidence_truth_mvp50.parquet",
        compression="zstd",
    )
    dump_json(
        manifests / "mvp50_manifest.json",
        {
            "manifest_name": selection["manifest_name"],
            "manifest_version": selection["manifest_version"],
            "dataset_version": config["dataset"]["dataset_version"],
            "pipeline_version": config["dataset"]["pipeline_version"],
            "semantic_mapping_version": config["dataset"][
                "semantic_mapping_version"
            ],
            "cases": manifest_entries,
        },
    )

    random.seed(selection["random_seed"])
    qa_cases = random.sample(case_ids, min(10, len(case_ids)))
    with (manifests / "clinical_qa.csv").open(
        "w", newline="", encoding="utf-8"
    ) as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=[
                "case_id",
                "reviewer",
                "issue_type",
                "severity",
                "comment",
                "status",
            ],
        )
        writer.writeheader()
        for case_id in qa_cases:
            writer.writerow({"case_id": case_id, "status": "PENDING"})
    print(f"Built {len(manifest_entries)} versioned case bundles")


if __name__ == "__main__":
    main()
