"""Shared case quota for every dataset track."""
from pathlib import Path

import yaml

CONFIG = yaml.safe_load(
    (Path(__file__).resolve().parents[1] / "configs/dataset_quota.yaml").read_text()
)
CASES_PER_DATASET = int(CONFIG["cases_per_dataset"])
