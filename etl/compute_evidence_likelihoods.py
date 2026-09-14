from __future__ import annotations

from collections import Counter

import pyarrow as pa
import pyarrow.parquet as pq

from backend.app.domain.evidence import parse_evidence_token
from etl.common import ddx_config, parse_python_literal, path_from_root


def main() -> None:
    config = ddx_config()
    processed = path_from_root(config["paths"]["processed_dir"])
    source = processed / "patients/train.parquet"
    alpha = float(config["smoothing_alpha"])
    condition_counts = Counter()
    present_counts = Counter()
    value_counts = Counter()
    evidence_values = Counter()
    parquet_file = pq.ParquetFile(source)
    for batch in parquet_file.iter_batches(
        columns=["pathology", "evidence_tokens"], batch_size=32768
    ):
        for pathology, raw_tokens in zip(
            batch.column(0).to_pylist(), batch.column(1).to_pylist()
        ):
            condition_counts[pathology] += 1
            seen = set()
            for token in parse_python_literal(raw_tokens):
                parsed = parse_evidence_token(token)
                if parsed.evidence_id not in seen:
                    present_counts[(pathology, parsed.evidence_id)] += 1
                    seen.add(parsed.evidence_id)
                if parsed.value is not True:
                    value = str(parsed.value)
                    value_counts[(pathology, parsed.evidence_id, value)] += 1
                    evidence_values[(parsed.evidence_id, value)] += 1
    conditions = sorted(condition_counts)
    evidences = sorted({evidence_id for _, evidence_id in present_counts})
    presence_rows = []
    for condition in conditions:
        total = condition_counts[condition]
        for evidence_id in evidences:
            present = present_counts[(condition, evidence_id)]
            presence_rows.append(
                {
                    "condition_id": condition,
                    "evidence_id": evidence_id,
                    "present_count": present,
                    "condition_count": total,
                    "p_present_given_condition": (present + alpha) / (total + 2 * alpha),
                    "p_absent_given_condition": (total - present + alpha) / (total + 2 * alpha),
                    "smoothing_alpha": alpha,
                    "provenance": "TRAIN_ONLY",
                }
            )
    value_rows = []
    values_by_evidence = {}
    for evidence_id, value in evidence_values:
        values_by_evidence.setdefault(evidence_id, []).append(value)
    for condition in conditions:
        for evidence_id, values in values_by_evidence.items():
            total = present_counts[(condition, evidence_id)]
            cardinality = len(values)
            for value in sorted(values):
                count = value_counts[(condition, evidence_id, value)]
                value_rows.append(
                    {
                        "condition_id": condition,
                        "evidence_id": evidence_id,
                        "value": value,
                        "value_count": count,
                        "evidence_present_count": total,
                        "probability": (count + alpha) / (total + alpha * cardinality),
                        "smoothing_alpha": alpha,
                        "provenance": "TRAIN_ONLY",
                    }
                )
    priors_dir = processed / "priors"
    pq.write_table(
        pa.Table.from_pylist(presence_rows),
        priors_dir / "condition_evidence_presence.parquet",
        compression="zstd",
    )
    pq.write_table(
        pa.Table.from_pylist(value_rows),
        priors_dir / "condition_evidence_values.parquet",
        compression="zstd",
    )
    print(
        f"Computed {len(presence_rows)} presence and {len(value_rows)} value likelihood rows from TRAIN only"
    )


if __name__ == "__main__":
    main()
