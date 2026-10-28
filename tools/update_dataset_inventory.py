"""Publish aggregate quotas/counts and prune unselected generated cases."""
from __future__ import annotations

import json
import shutil
from collections import Counter
from pathlib import Path

from backend.app.services.case_service import CaseService
from etl.quota import CASES_PER_DATASET, CONFIG

ROOT = Path(__file__).resolve().parents[1]


def main():
    cases = CaseService(ROOT)
    counts = Counter(case.dataset.name for case in cases.cases.values())
    source = json.loads((ROOT / "data/processed/sources/manifest.json").read_text())
    raw_gaps = {**source.get("ehr_shortfalls", {}), **source.get("interaction_shortfalls", {})}
    # Validation errors can contain source values. Public inventory is aggregate
    # metadata only; detailed failures remain in the private source manifest.
    gaps = {dataset: {
        "requested": gap["requested"], "actual": gap["actual"],
        "reason": gap.get("reason", "INSUFFICIENT_ELIGIBLE_SOURCE_CASES"),
    } for dataset, gap in raw_gaps.items()}
    for dataset, count in counts.items():
        if count != CASES_PER_DATASET and dataset not in gaps:
            raise ValueError(f"Unexplained quota mismatch: {dataset} {count}")
    memory = [c for c in cases.cases.values() if c.dataset.name == "MedMemoryBench"]
    personas = {c.source_provenance["raw_source"]["source_persona_id"] for c in memory}
    medpi = [c for c in cases.cases.values() if c.dataset.name == "MedPI"]
    medpi_patients = {c.source_provenance["raw_source"]["patient"]["id"] for c in medpi}
    nejm = [c for c in cases.cases.values() if c.dataset.name == "NEJM CPC"]
    nejm_fulltexts = sum(bool(c.source_provenance["raw_source"].get("pmcid")) for c in nejm)
    inventory = {
        "protocol": "UNORDERED_EVIDENCE", "case_count": len(cases.cases),
        "dataset_count": len(counts), "requested_cases_per_dataset": CASES_PER_DATASET,
        "requested_total": CASES_PER_DATASET * int(CONFIG["dataset_count"]),
        "quota_complete": len(counts) == int(CONFIG["dataset_count"]) and not gaps,
        "dataset_case_counts": dict(sorted(counts.items())), "shortfalls": gaps,
        "counting_unit": "Runnable source-backed case from current manifests",
        "sampling_notes": {"MedMemoryBench": {
            "case_count": len(memory), "source_persona_count": len(personas),
            "unit": "Non-overlapping source event window; shared personas are not independent patients",
        }, "MedPI": {
            "case_count": len(medpi), "source_patient_profile_count": len(medpi_patients),
            "unit": "Distinct source conversation; shared profiles are not independent patients",
        }, "NEJM CPC": {"open_fulltext_cases": nejm_fulltexts,
                       "pubmed_abstract_cases": len(nejm) - nejm_fulltexts}},
        "linked_modalities": {"MIMIC": ["MIMIC-IV-Note", "MIMIC-IV-ECG", "MIMIC-IV-ED"]},
        "privacy": "AGGREGATE_COUNTS_ONLY",
    }
    output = ROOT / "data/manifests/dataset_inventory.json"
    # Tree manifests also reference raw artifacts; use exact paths rather than
    # filename stems (which include suffixes such as ".raw" and ".tree").
    referenced = set()
    for manifest in (ROOT / "data/manifests").glob("*manifest.json"):
        for row in json.loads(manifest.read_text()).get("cases", []):
            referenced.update(ROOT / row[key] for key in
                              ("path", "raw_case_path", "tree_path") if row.get(key))
    missing = [path for path in referenced if not path.exists()]
    if missing:
        raise ValueError(f"Missing selected artifact: {missing[0]}")
    for dataset in ("ddxplus", "synthea", "medagentbench"):
        for kind in ("case_bundles", "raw_cases", "case_trees"):
            directory = ROOT / f"data/processed/{dataset}/{kind}"
            for path in directory.iterdir():
                if path.is_file() and path not in referenced:
                    path.unlink()
                elif path.is_dir() and not any(path in active.parents for active in referenced):
                    shutil.rmtree(path)
    active_paths = {ROOT / row["path"] for row in source["cases"]}
    for path in (ROOT / "data/processed/sources/case_bundles").glob("*/*/case.json"):
        if path not in active_paths:
            shutil.rmtree(path.parent)
    output.write_text(json.dumps(inventory, indent=2) + "\n")
    print(json.dumps(inventory, indent=2))


if __name__ == "__main__":
    main()
