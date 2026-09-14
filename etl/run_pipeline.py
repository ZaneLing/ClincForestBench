from __future__ import annotations

import subprocess
import sys


STAGES = [
    "etl.prepare_raw",
    "etl.inspect_raw",
    "etl.build_evidence_catalog",
    "etl.build_condition_catalog",
    "etl.normalize_patients",
    "etl.compute_priors",
    "etl.compute_evidence_likelihoods",
    "etl.score_cases",
    "etl.select_cases",
    "etl.build_case_bundles",
    "etl.build_case_trees",
    "etl.write_example_case",
]


def main() -> None:
    for stage in STAGES:
        print(f"\n== {stage} ==", flush=True)
        subprocess.run([sys.executable, "-m", stage], check=True)


if __name__ == "__main__":
    main()
