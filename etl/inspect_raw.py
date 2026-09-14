from __future__ import annotations

import re
from collections import Counter
from pathlib import Path

import pyarrow.parquet as pq

from backend.app.domain.evidence import parse_evidence_token
from etl.common import (
    ddx_config,
    dump_json,
    load_json,
    parse_python_literal,
    path_from_root,
)


EXPECTED_COLUMNS = {
    "AGE",
    "DIFFERENTIAL_DIAGNOSIS",
    "SEX",
    "PATHOLOGY",
    "EVIDENCES",
    "INITIAL_EVIDENCE",
}
EVIDENCE_ID_RE = re.compile(r"^E_\d+$")


def validate_split(
    paths: list[Path], evidence_catalog: dict, condition_catalog: dict
) -> dict:
    counters = Counter()
    seen_rows = set()
    row_count = 0

    for path in paths:
        parquet_file = pq.ParquetFile(path)
        if set(parquet_file.schema_arrow.names) != EXPECTED_COLUMNS:
            raise ValueError(f"Unexpected schema in {path}")
        for batch in parquet_file.iter_batches(batch_size=32768):
            columns = batch.to_pydict()
            for row in zip(*(columns[name] for name in batch.schema.names)):
                record = dict(zip(batch.schema.names, row))
                row_count += 1
                if record["PATHOLOGY"] not in condition_catalog:
                    counters["missing_condition_count"] += 1
                try:
                    tokens = parse_python_literal(record["EVIDENCES"])
                except (ValueError, SyntaxError):
                    counters["invalid_evidence_list_count"] += 1
                    continue
                parsed_ids = []
                for token in tokens:
                    try:
                        parsed = parse_evidence_token(token)
                    except ValueError:
                        counters["invalid_evidence_token_count"] += 1
                        continue
                    parsed_ids.append(parsed.evidence_id)
                    definition = evidence_catalog.get(parsed.evidence_id)
                    if definition is None or not EVIDENCE_ID_RE.match(parsed.evidence_id):
                        counters["unknown_evidence_token_count"] += 1
                        continue
                    if parsed.value is not True:
                        allowed = definition.get("possible-values", [])
                        # Parquet stores evidence tokens as strings (for example
                        # ``E_56_@_4``) while the metadata uses JSON numbers.
                        # Comparing canonical string forms preserves both numeric
                        # and coded categorical values.
                        if allowed and str(parsed.value) not in {
                            str(value) for value in allowed
                        }:
                            counters["invalid_value_count"] += 1
                if record["INITIAL_EVIDENCE"] not in parsed_ids:
                    counters["initial_evidence_not_in_evidence_list_count"] += 1
                try:
                    differential = parse_python_literal(
                        record["DIFFERENTIAL_DIAGNOSIS"]
                    )
                    for condition, _ in differential:
                        if condition not in condition_catalog:
                            counters["invalid_differential_condition_count"] += 1
                except (ValueError, SyntaxError, TypeError):
                    counters["invalid_differential_count"] += 1
                signature = (
                    record["AGE"],
                    record["SEX"],
                    record["PATHOLOGY"],
                    record["EVIDENCES"],
                    record["INITIAL_EVIDENCE"],
                )
                if signature in seen_rows:
                    counters["duplicate_case_count"] += 1
                else:
                    seen_rows.add(signature)
    return {"row_count": row_count, **dict(counters)}


def main() -> None:
    config = ddx_config()
    raw_dir = path_from_root(config["paths"]["raw_dir"])
    evidences = load_json(raw_dir / "release_evidences.json")
    conditions = load_json(raw_dir / "release_conditions.json")

    hierarchy_errors = sum(
        1
        for evidence_id, value in evidences.items()
        if value["code_question"] != evidence_id
        and value["code_question"] not in evidences
    )
    report = {
        "dataset_version": config["dataset"]["dataset_version"],
        "evidence_catalog_count": len(evidences),
        "condition_catalog_count": len(conditions),
        "hierarchy_reference_error_count": hierarchy_errors,
        "splits": {},
    }
    for split, names in config["splits"].items():
        report["splits"][split] = validate_split(
            [raw_dir / name for name in names], evidences, conditions
        )

    expected = config.get("known_upstream_quality_exceptions", {})
    expected_duplicates = expected.get("duplicate_case_count", {})
    exception_drift = []
    if hierarchy_errors != int(expected.get("hierarchy_reference_error_count", 0)):
        exception_drift.append("hierarchy_reference_error_count")
    for split, values in report["splits"].items():
        if int(values.get("duplicate_case_count", 0)) != int(
            expected_duplicates.get(split, 0)
        ):
            exception_drift.append(f"{split}.duplicate_case_count")
    report["quality_status"] = (
        "PASSED_WITH_VERSIONED_UPSTREAM_EXCEPTIONS"
        if not exception_drift
        else "FAILED_EXCEPTION_DRIFT"
    )
    report["exception_drift"] = exception_drift

    dump_json(path_from_root("data/manifests/raw_quality_v1.json"), report)
    fatal_keys = {
        "missing_condition_count",
        "invalid_evidence_list_count",
        "invalid_evidence_token_count",
        "unknown_evidence_token_count",
        "invalid_value_count",
        "initial_evidence_not_in_evidence_list_count",
        "invalid_differential_condition_count",
        "invalid_differential_count",
    }
    # Five records in the public DDXPlus metadata reference question codes
    # which are not shipped as evidence records.  Keep this visible in the
    # report, but treat it as an upstream warning rather than patient corruption.
    failures = len(exception_drift) + sum(
        int(values.get(key, 0))
        for values in report["splits"].values()
        for key in fatal_keys
    )
    print(report)
    if failures:
        raise SystemExit(f"Raw data quality validation failed with {failures} errors")


if __name__ == "__main__":
    main()
