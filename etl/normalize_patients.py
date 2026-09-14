from __future__ import annotations

import duckdb

from etl.common import ddx_config, path_from_root


def main() -> None:
    config = ddx_config()
    raw_dir = path_from_root(config["paths"]["raw_dir"])
    output_dir = path_from_root(config["paths"]["processed_dir"]) / "patients"
    output_dir.mkdir(parents=True, exist_ok=True)
    con = duckdb.connect()
    for split, names in config["splits"].items():
        sources = ", ".join("'{}'".format(raw_dir / name) for name in names)
        prefix = f"DDX_{split.upper()}_"
        output = output_dir / f"{split}.parquet"
        query = f"""
            COPY (
              SELECT
                '{prefix}' || lpad(CAST(row_number() OVER () AS VARCHAR), 7, '0') AS case_id,
                '{split}' AS split,
                CAST(AGE AS INTEGER) AS age,
                SEX AS sex,
                PATHOLOGY AS pathology,
                EVIDENCES AS evidence_tokens,
                INITIAL_EVIDENCE AS initial_evidence,
                DIFFERENTIAL_DIAGNOSIS AS oracle_differential,
                '{config['dataset']['dataset_version']}' AS dataset_version,
                '{config['dataset']['pipeline_version']}' AS pipeline_version
              FROM read_parquet([{sources}])
            ) TO '{output}' (FORMAT PARQUET, COMPRESSION ZSTD)
        """
        con.execute(query)
        count = con.execute(
            f"SELECT count(*) FROM read_parquet('{output}')"
        ).fetchone()[0]
        print(f"Normalized {split}: {count} rows")


if __name__ == "__main__":
    main()
