from __future__ import annotations

from collections import defaultdict
from math import log2
from typing import Iterable


def entropy(probabilities: Iterable[float]) -> float:
    values = [float(value) for value in probabilities if value > 0]
    total = sum(values)
    if total <= 0:
        return 0.0
    return -sum((value / total) * log2(value / total) for value in values)


def belief_updates(rows: list[dict]) -> list[dict]:
    grouped = defaultdict(list)
    for row in rows:
        grouped[row["session_id"]].append(row)
    output = []
    for session_id, session_rows in grouped.items():
        by_belief = defaultdict(list)
        for row in session_rows:
            by_belief[row["belief_id"]].append(row)
        snapshots = sorted(
            by_belief.values(), key=lambda group: (group[0]["step"], str(group[0]["timestamp"]))
        )
        for previous, current in zip(snapshots, snapshots[1:]):
            previous_top = min(previous, key=lambda row: row["rank"])
            current_top = min(current, key=lambda row: row["rank"])
            output.append(
                {
                    "session_id": session_id,
                    "from_step": previous_top["step"],
                    "to_step": current_top["step"],
                    "top1_changed": previous_top["diagnosis_id"] != current_top["diagnosis_id"],
                    "confidence_shift": current_top["overall_confidence"] - previous_top["overall_confidence"],
                    "entropy_before": entropy(row["probability"] for row in previous),
                    "entropy_after": entropy(row["probability"] for row in current),
                }
            )
    return output


def edge_metrics(rows: list[dict]) -> list[dict]:
    outgoing = defaultdict(list)
    for row in rows:
        outgoing[(row["case_id"], row["source_hash"])].append(row)
    output = []
    for (case_id, source_hash), edges in outgoing.items():
        total = sum(int(edge["support"]) for edge in edges)
        output.append(
            {
                "case_id": case_id,
                "state_hash": source_hash,
                "out_degree": len(edges),
                "support": total,
                "branch_entropy": entropy(int(edge["support"]) / total for edge in edges),
            }
        )
    return output

