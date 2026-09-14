from __future__ import annotations

import json

import pyarrow as pa
import pyarrow.parquet as pq

from etl.common import ddx_config, load_json, path_from_root


def main() -> None:
    config = ddx_config()
    raw_dir = path_from_root(config["paths"]["raw_dir"])
    output_dir = path_from_root(config["paths"]["processed_dir"])
    output_dir.mkdir(parents=True, exist_ok=True)
    conditions = load_json(raw_dir / "release_conditions.json")
    rows = []
    for condition_id, item in sorted(conditions.items()):
        rows.append(
            {
                "condition_id": condition_id,
                "condition_name": item["condition_name"],
                "condition_name_en": item.get("cond-name-eng"),
                "condition_name_fr": item.get("cond-name-fr"),
                "icd10_id": item.get("icd10-id"),
                "severity": int(item["severity"]),
                "symptom_evidence_ids": json.dumps(sorted(item["symptoms"])),
                "antecedent_evidence_ids": json.dumps(
                    sorted(item["antecedents"])
                ),
                "dataset_version": config["dataset"]["dataset_version"],
            }
        )
    pq.write_table(pa.Table.from_pylist(rows), output_dir / "condition_catalog.parquet")
    print(f"Built {len(rows)} condition rows")


if __name__ == "__main__":
    main()
