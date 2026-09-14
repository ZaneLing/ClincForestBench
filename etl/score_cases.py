from __future__ import annotations

from collections import defaultdict

import pyarrow as pa
import pyarrow.parquet as pq

from backend.app.domain.evidence import group_evidence_tokens
from etl.common import (
    ddx_config,
    entropy,
    load_json,
    parse_python_literal,
    path_from_root,
    selection_config,
)


def normalize(values: list[float]) -> list[float]:
    low, high = min(values), max(values)
    if high == low:
        return [0.0 for _ in values]
    return [(value - low) / (high - low) for value in values]


def main() -> None:
    config = ddx_config()
    selection = selection_config()
    processed = path_from_root(config["paths"]["processed_dir"])
    raw = path_from_root(config["paths"]["raw_dir"])
    evidences = load_json(raw / "release_evidences.json")
    conditions = load_json(raw / "release_conditions.json")
    source = processed / f"patients/{selection['source_split']}.parquet"

    rows: list[dict] = []
    parquet_file = pq.ParquetFile(source)
    for batch in parquet_file.iter_batches(batch_size=16384):
        for record in batch.to_pylist():
            tokens = parse_python_literal(record["evidence_tokens"])
            grouped = group_evidence_tokens(tokens)
            ids = set(grouped)
            symptom_count = sum(
                1 for evidence_id in ids if not evidences[evidence_id]["is_antecedent"]
            )
            antecedent_count = len(ids) - symptom_count
            root_count = sum(
                1
                for evidence_id in ids
                if evidences[evidence_id]["code_question"] == evidence_id
            )
            child_count = len(ids) - root_count
            nonbinary_count = sum(
                1 for evidence_id in ids if evidences[evidence_id]["data_type"] != "B"
            )
            differential = parse_python_literal(record["oracle_differential"])
            probabilities = [float(item[1]) for item in differential]
            ordered = sorted(probabilities, reverse=True)
            initial = evidences[record["initial_evidence"]]
            rows.append(
                {
                    "case_id": record["case_id"],
                    "split": record["split"],
                    "pathology": record["pathology"],
                    "age": record["age"],
                    "sex": record["sex"],
                    "initial_evidence": record["initial_evidence"],
                    "initial_evidence_type": "ANTECEDENT"
                    if initial["is_antecedent"]
                    else "SYMPTOM",
                    "evidence_count": len(ids),
                    "symptom_count": symptom_count,
                    "antecedent_count": antecedent_count,
                    "independent_root_count": root_count,
                    "child_attribute_count": child_count,
                    "nonbinary_count": nonbinary_count,
                    "differential_size": len(differential),
                    "differential_entropy": entropy(probabilities),
                    "top1_probability": ordered[0],
                    "top1_top2_margin": ordered[0] - ordered[1]
                    if len(ordered) > 1
                    else ordered[0],
                    "condition_severity": int(conditions[record["pathology"]]["severity"]),
                }
            )

    components = {
        "independent_root_count": normalize(
            [float(row["independent_root_count"]) for row in rows]
        ),
        "child_attribute_count": normalize(
            [float(row["child_attribute_count"]) for row in rows]
        ),
        "differential_entropy": normalize(
            [float(row["differential_entropy"]) for row in rows]
        ),
        "nonbinary_count": normalize(
            [float(row["nonbinary_count"]) for row in rows]
        ),
        "evidence_count": normalize(
            [float(row["evidence_count"]) for row in rows]
        ),
    }
    for index, row in enumerate(rows):
        row["branchability_score"] = sum(
            float(selection["weights"][name]) * components[name][index]
            for name in components
        )
    output = processed / "case_quality.parquet"
    pq.write_table(pa.Table.from_pylist(rows), output, compression="zstd")
    print(f"Scored {len(rows)} {selection['source_split']} cases")


if __name__ == "__main__":
    main()
