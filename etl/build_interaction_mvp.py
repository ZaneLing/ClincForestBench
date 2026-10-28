"""Select source-authored interaction evidence without replay or timing rules."""
from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime, timezone

from etl.common import dump_json, load_json
from etl.quota import CASES_PER_DATASET
from etl.source_adapters import (
    MedDialogRubricsSourceAdapter, MeddiesSourceAdapter, MediScopeSourceAdapter,
    MedMemoryBenchSourceAdapter, MedPISourceAdapter, PatientSimSourceAdapter,
)
from etl.source_adapters.common import SOURCE_ROOT, attach_conversion_audit, clean

INTERACTION_DATASETS = {"MediScope", "MedPI", "PatientSim", "Meddies Persona VIE",
                        "MedMemoryBench", "MedDialogRubrics"}


def build(case_count=CASES_PER_DATASET, allow_shortfall=False):
    path = SOURCE_ROOT / "manifest.json"
    if not path.exists():
        raise RuntimeError("Source manifest is missing; run `make preprocess-ehr-sources` first")
    previous = load_json(path)
    entries = [row for row in previous["cases"] if row["dataset_name"] not in INTERACTION_DATASETS]
    built_counts, shortfalls = {}, {}
    for adapter in (MediScopeSourceAdapter(), MedPISourceAdapter(), PatientSimSourceAdapter(),
                    MeddiesSourceAdapter(), MedMemoryBenchSourceAdapter(), MedDialogRubricsSourceAdapter()):
        target = case_count
        candidates = adapter.list_cases(max(20, target * 6))
        dump_json(SOURCE_ROOT / "candidate_scores" / f"{adapter.dataset_slug}.json", {
            "dataset": adapter.dataset_name, "selection_policy": "FIRST_ELIGIBLE_SOURCE_CASES",
            "candidates": [{key: clean(value) for key, value in row.items() if key not in {"messages", "row"}}
                           for row in candidates],
        })
        selected, failures = [], []
        for candidate in candidates:
            try:
                selected.append(attach_conversion_audit(adapter.load_case(candidate), candidate))
            except (ValueError, KeyError, TypeError) as exc:
                failures.append(str(exc))
                continue
            if len(selected) >= target:
                break
        if len(selected) < target:
            shortfalls[adapter.dataset_name] = {
                "requested": target, "actual": len(selected),
                "reason": "AUTHORIZED_SOURCE_REQUIRED" if adapter.dataset_slug == "patientsim"
                else "INSUFFICIENT_ELIGIBLE_SOURCE_CASES", "failures": failures[:3],
            }
            if not allow_shortfall:
                raise RuntimeError(f"{adapter.dataset_name}: built {len(selected)}/{target}; failures={failures[:3]}")
        entries.extend(adapter.write_case(case) for case in selected)
        built_counts[adapter.dataset_name] = len(selected)
    manifest = {
        **previous, "generated_at": datetime.now(timezone.utc).isoformat(),
        "case_count": len(entries), "dataset_case_counts": dict(Counter(row["dataset_name"] for row in entries)),
        "all_checks_pass": all(all(row["checks"].values()) for row in entries),
        "interaction_mvp": {"case_count": sum(built_counts.values()), "dataset_case_counts": built_counts},
        "interaction_shortfalls": shortfalls,
        "privacy": "LOCAL_ONLY", "cases": entries,
    }
    dump_json(path, manifest)
    return manifest


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--cases-per-dataset", type=int, default=CASES_PER_DATASET)
    parser.add_argument("--allow-shortfall", action="store_true")
    args = parser.parse_args()
    result = build(args.cases_per_dataset, args.allow_shortfall)
    print(f"Selected {result['interaction_mvp']['case_count']} interaction cases")
