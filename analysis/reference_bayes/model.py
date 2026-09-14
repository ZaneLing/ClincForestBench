from __future__ import annotations

import math
from pathlib import Path
from typing import Dict, Iterable

import pyarrow.parquet as pq

from backend.app.domain.evidence import EvidenceResponse
from etl.common import ddx_config, path_from_root


class ReferenceNaiveBayes:
    """Analysis-only train-derived reference. Never used by the Arena."""

    def __init__(self, priors_dir: Path | None = None) -> None:
        config = ddx_config()
        self.priors_dir = priors_dir or path_from_root(config["paths"]["processed_dir"]) / "priors"
        self.priors = {
            row["condition_id"]: float(row["probability"])
            for row in pq.read_table(self.priors_dir / "global_condition_prior.parquet").to_pylist()
        }
        self.likelihoods = {
            (row["condition_id"], row["evidence_id"]): row
            for row in pq.read_table(self.priors_dir / "condition_evidence_presence.parquet").to_pylist()
        }

    def posterior(self, observations: Iterable[EvidenceResponse]) -> Dict[str, float]:
        log_scores = {condition: math.log(prior) for condition, prior in self.priors.items()}
        for observation in observations:
            for condition in log_scores:
                row = self.likelihoods.get((condition, observation.evidence_id))
                if not row:
                    continue
                present = observation.status.value in {"PRESENT", "VALUE"}
                probability = row["p_present_given_condition"] if present else row["p_absent_given_condition"]
                log_scores[condition] += math.log(max(float(probability), 1e-12))
        maximum = max(log_scores.values())
        weights = {condition: math.exp(score - maximum) for condition, score in log_scores.items()}
        total = sum(weights.values())
        return {condition: value / total for condition, value in sorted(weights.items())}

    @staticmethod
    def information_gain(before: Dict[str, float], after: Dict[str, float]) -> float:
        def entropy(values):
            return -sum(value * math.log2(value) for value in values if value > 0)
        return entropy(before.values()) - entropy(after.values())
