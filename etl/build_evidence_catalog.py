from __future__ import annotations

import csv
import json

import pyarrow as pa
import pyarrow.parquet as pq

from etl.common import ddx_config, load_json, path_from_root


TYPE_MAP = {"B": "binary", "C": "categorical", "M": "multi_choice"}


def build_rows() -> list[dict]:
    config = ddx_config()
    raw_dir = path_from_root(config["paths"]["raw_dir"])
    evidences = load_json(raw_dir / "release_evidences.json")
    mapping_version = config["dataset"]["semantic_mapping_version"]
    rows = []
    for evidence_id, item in sorted(evidences.items()):
        declared_parent = item["code_question"]
        unresolved_parent = declared_parent not in evidences
        is_root = declared_parent == evidence_id or unresolved_parent
        parent_id = None if is_root else declared_parent
        if item["is_antecedent"]:
            semantic_role = "OTHER_ANTECEDENT"
            tier = 3
        elif is_root:
            semantic_role = "PRESENTING_SYMPTOM"
            tier = 2
        else:
            semantic_role = "SYMPTOM_ATTRIBUTE"
            tier = 1
        rows.append(
            {
                "evidence_id": evidence_id,
                "question_en": item["question_en"],
                "is_antecedent": bool(item["is_antecedent"]),
                "data_type": TYPE_MAP[item["data_type"]],
                "default_value": json.dumps(item["default_value"]),
                "possible_values": json.dumps(item.get("possible-values", [])),
                "value_meanings": json.dumps(
                    item.get("value_meaning", {}), ensure_ascii=False
                ),
                "code_question": item["code_question"],
                "parent_evidence_id": parent_id,
                "hierarchy_status": "UNRESOLVED_UPSTREAM_PARENT"
                if unresolved_parent
                else "RESOLVED",
                "is_root_question": is_root,
                "semantic_role": semantic_role,
                "exposure_tier": tier,
                "mapping_version": mapping_version,
            }
        )
    return rows


def main() -> None:
    config = ddx_config()
    output_dir = path_from_root(config["paths"]["processed_dir"])
    output_dir.mkdir(parents=True, exist_ok=True)
    rows = build_rows()
    pq.write_table(pa.Table.from_pylist(rows), output_dir / "evidence_catalog.parquet")

    hierarchy = [
        {
            "parent_evidence_id": row["parent_evidence_id"],
            "child_evidence_id": row["evidence_id"],
            "activation_condition": "PRESENT",
            "mapping_version": row["mapping_version"],
        }
        for row in rows
        if row["parent_evidence_id"]
    ]
    pq.write_table(
        pa.Table.from_pylist(hierarchy), output_dir / "evidence_hierarchy.parquet"
    )

    semantics_path = output_dir / "evidence_semantics.csv"
    fields = [
        "evidence_id",
        "clinical_domain",
        "semantic_role",
        "is_root",
        "parent_id",
        "research_tier",
        "curation_source",
        "curation_version",
    ]
    with semantics_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for row in rows:
            writer.writerow(
                {
                    "evidence_id": row["evidence_id"],
                    "clinical_domain": "ANTECEDENT"
                    if row["is_antecedent"]
                    else "SYMPTOM",
                    "semantic_role": row["semantic_role"],
                    "is_root": row["is_root_question"],
                    "parent_id": row["parent_evidence_id"] or "",
                    "research_tier": row["exposure_tier"],
                    "curation_source": "DDXPlus automatic metadata mapping; requires clinical QA",
                    "curation_version": row["mapping_version"],
                }
            )
    print(f"Built {len(rows)} evidence rows and {len(hierarchy)} hierarchy edges")


if __name__ == "__main__":
    main()
