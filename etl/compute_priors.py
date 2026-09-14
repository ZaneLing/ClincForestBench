from __future__ import annotations

import duckdb

from etl.common import ddx_config, path_from_root


def age_bucket_sql(config: dict) -> str:
    clauses = [
        f"WHEN age BETWEEN {bucket['min']} AND {bucket['max']} THEN '{bucket['name']}'"
        for bucket in config["age_buckets"]
    ]
    return "CASE " + " ".join(clauses) + " ELSE 'UNKNOWN' END"


def main() -> None:
    config = ddx_config()
    processed = path_from_root(config["paths"]["processed_dir"])
    priors_dir = processed / "priors"
    priors_dir.mkdir(parents=True, exist_ok=True)
    train = processed / "patients/train.parquet"
    con = duckdb.connect()
    age_bucket = age_bucket_sql(config)
    alpha = float(config["smoothing_alpha"])

    con.execute(
        f"""
        COPY (
          WITH counts AS (
            SELECT pathology AS condition_id, count(*) AS n
            FROM read_parquet('{train}') GROUP BY pathology
          ), totals AS (SELECT sum(n) AS total, count(*) AS k FROM counts)
          SELECT condition_id, n,
                 (n + {alpha}) / (total + {alpha} * k) AS probability,
                 'TRAIN_ONLY' AS provenance
          FROM counts, totals ORDER BY condition_id
        ) TO '{priors_dir / 'global_condition_prior.parquet'}'
          (FORMAT PARQUET, COMPRESSION ZSTD)
        """
    )
    con.execute(
        f"""
        COPY (
          WITH base AS (
            SELECT *, {age_bucket} AS age_bucket FROM read_parquet('{train}')
          ), counts AS (
            SELECT age_bucket, sex, pathology AS condition_id, count(*) AS n
            FROM base GROUP BY age_bucket, sex, pathology
          ), totals AS (
            SELECT age_bucket, sex, sum(n) AS total, count(*) AS k
            FROM counts GROUP BY age_bucket, sex
          )
          SELECT c.*, (c.n + {alpha}) / (t.total + {alpha} * t.k) AS probability,
                 'TRAIN_ONLY' AS provenance
          FROM counts c JOIN totals t USING (age_bucket, sex)
          ORDER BY age_bucket, sex, condition_id
        ) TO '{priors_dir / 'demographic_condition_prior.parquet'}'
          (FORMAT PARQUET, COMPRESSION ZSTD)
        """
    )
    con.execute(
        f"""
        COPY (
          WITH base AS (
            SELECT *, {age_bucket} AS age_bucket FROM read_parquet('{train}')
          ), counts AS (
            SELECT age_bucket, sex, initial_evidence,
                   pathology AS condition_id, count(*) AS n
            FROM base GROUP BY age_bucket, sex, initial_evidence, pathology
          ), totals AS (
            SELECT age_bucket, sex, initial_evidence, sum(n) AS total, count(*) AS k
            FROM counts GROUP BY age_bucket, sex, initial_evidence
          )
          SELECT c.*, (c.n + {alpha}) / (t.total + {alpha} * t.k) AS probability,
                 'TRAIN_ONLY' AS provenance
          FROM counts c JOIN totals t USING (age_bucket, sex, initial_evidence)
          ORDER BY age_bucket, sex, initial_evidence, condition_id
        ) TO '{priors_dir / 'initial_evidence_condition_prior.parquet'}'
          (FORMAT PARQUET, COMPRESSION ZSTD)
        """
    )
    print("Computed three train-only DDXPlus empirical priors")


if __name__ == "__main__":
    main()
