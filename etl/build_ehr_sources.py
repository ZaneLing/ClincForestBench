"""Select source-backed EHR and narrative evidence for unordered case building."""
from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime, timezone

from etl.common import dump_json, load_json
from etl.quota import CASES_PER_DATASET
from etl.source_adapters import (
    EICUSourceAdapter, MCMEDSourceAdapter, MIMICSourceAdapter, NEJMSourceAdapter, PMCSourceAdapter,
)
from etl.source_adapters.common import ROOT, SOURCE_ROOT, attach_conversion_audit, clean
from etl.source_adapters.validation import validate_eicu, validate_mcmed, validate_mimic


def build(case_count=CASES_PER_DATASET, narrative_case_count=None, validate=True,
          allow_shortfall=False):
    narrative_case_count = narrative_case_count or case_count
    if validate:
        source_validation = {"mcmed": validate_mcmed(), "mimic": validate_mimic(), "eicu": validate_eicu()}
    else:
        source_validation = {"status": "SKIPPED_BY_OPERATOR"}
    entries, shortfalls = [], {}
    for adapter in (MCMEDSourceAdapter(), MIMICSourceAdapter(), EICUSourceAdapter(),
                    PMCSourceAdapter(), NEJMSourceAdapter()):
        target = narrative_case_count if adapter.dataset_slug in {"pmc", "nejm"} else case_count
        candidate_limit = {"mcmed": max(120, case_count * 24), "mimic": max(40, case_count * 8),
                           "eicu": max(40, case_count * 8), "pmc": max(80, narrative_case_count * 16),
                           "nejm": max(10, narrative_case_count * 2)}[adapter.dataset_slug]
        candidates = adapter.list_cases(candidate_limit)
        dump_json(SOURCE_ROOT / "candidate_scores" / f"{adapter.dataset_slug}.json", {
            "dataset": adapter.dataset_name,
            "candidates": [{key: clean(value) for key, value in row.items()} for row in candidates],
        })
        selected = []
        for candidate in candidates:
            try:
                selected.append(attach_conversion_audit(adapter.load_case(candidate), candidate))
            except (ValueError, KeyError):
                continue
            if len(selected) >= target:
                break
        if len(selected) < target:
            shortfalls[adapter.dataset_name] = {"requested": target, "actual": len(selected)}
            if not allow_shortfall:
                raise RuntimeError(f"{adapter.dataset_name}: built {len(selected)} cases, requested {target}")
        entries.extend(adapter.write_case(case) for case in selected)
        print(f"{adapter.dataset_name}: {len(selected)}/{target} cases", flush=True)
    # Rebuilding EHR sources does not discard already selected interaction cases.
    path = SOURCE_ROOT / "manifest.json"
    previous = load_json(path) if path.exists() else {}
    from etl.build_interaction_mvp import INTERACTION_DATASETS
    entries.extend(row for row in previous.get("cases", []) if row["dataset_name"] in INTERACTION_DATASETS)
    manifest = {
        "interaction_shortfalls": previous.get("interaction_shortfalls", {}),
        "interaction_mvp": previous.get("interaction_mvp", {}),
        "schema_version": "clincforestbench.source-evidence-manifest",
        "generated_at": datetime.now(timezone.utc).isoformat(), "case_count": len(entries),
        "dataset_case_counts": dict(Counter(row["dataset_name"] for row in entries)),
        "all_checks_pass": all(all(row["checks"].values()) for row in entries),
        "source_validation": source_validation, "privacy": "LOCAL_ONLY", "cases": entries,
        "ehr_shortfalls": shortfalls,
    }
    dump_json(path, manifest)
    return manifest


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--cases-per-dataset", type=int, default=CASES_PER_DATASET)
    parser.add_argument("--narrative-cases-per-dataset", type=int)
    parser.add_argument("--skip-validation", action="store_true")
    parser.add_argument("--allow-shortfall", action="store_true")
    args = parser.parse_args()
    manifest = build(args.cases_per_dataset, args.narrative_cases_per_dataset,
                     not args.skip_validation, args.allow_shortfall)
    print(f"Selected {manifest['case_count']} source cases under {SOURCE_ROOT.relative_to(ROOT)}")
