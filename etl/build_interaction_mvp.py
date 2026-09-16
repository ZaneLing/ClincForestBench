from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from typing import Any

import pyarrow as pa
import pyarrow.parquet as pq

from backend.app.domain.temporal import TemporalCase
from etl.common import dump_json, load_json
from etl.temporal_v2 import (
    MedDialogRubricsTemporalAdapter,
    MeddiesTemporalAdapter,
    MediScopeTemporalAdapter,
    MedMemoryBenchTemporalAdapter,
    MedPITemporalAdapter,
    PatientSimTemporalAdapter,
)
from etl.temporal_v2.common import ROOT, TEMPORAL_ROOT, attach_conversion_audit, clean


INTERACTION_DATASETS = {
    "MediScope",
    "MedPI",
    "PatientSim",
    "Meddies Persona VIE",
    "MedMemoryBench",
    "MedDialogRubrics",
}


def _candidate_summary(candidate: dict[str, Any]) -> dict[str, Any]:
    """Persist selection evidence without duplicating full conversations/records."""
    omitted = {"messages", "row"}
    return {
        key: clean(value)
        for key, value in candidate.items()
        if key not in omitted
    }


def _load_existing() -> tuple[list, list[dict[str, Any]], dict[str, Any]]:
    manifest_path = TEMPORAL_ROOT / "manifest.json"
    if not manifest_path.exists():
        raise RuntimeError(
            "Temporal base manifest is missing; run `make preprocess-temporal` first"
        )
    manifest = load_json(manifest_path)
    entries = [
        entry
        for entry in manifest.get("cases", [])
        if entry.get("dataset_name") not in INTERACTION_DATASETS
    ]
    cases = [
        TemporalCase.model_validate(load_json(ROOT / entry["path"]))
        for entry in entries
    ]
    return cases, entries, manifest


def _write_canonical(cases: list) -> None:
    canonical = TEMPORAL_ROOT / "canonical"
    canonical.mkdir(parents=True, exist_ok=True)
    pq.write_table(
        pa.Table.from_pylist(
            [
                {
                    "case_id": case.case_id,
                    "case_version": case.case_version,
                    "dataset": case.source["dataset_family"],
                    "task_type": case.task_type,
                    "anchor_json": json.dumps(case.anchor, ensure_ascii=False, sort_keys=True),
                    "initial_state_json": json.dumps(case.initial_state, ensure_ascii=False, sort_keys=True),
                    "reference_json": json.dumps(case.reference, ensure_ascii=False, sort_keys=True),
                    "quality_json": json.dumps(case.case_quality, ensure_ascii=False, sort_keys=True),
                }
                for case in cases
            ]
        ),
        canonical / "cases.parquet",
    )
    pq.write_table(
        pa.Table.from_pylist(
            [
                {
                    "case_id": case.case_id,
                    "event_id": event.event_id,
                    "event_type": event.event_type,
                    "modality": event.clinical_concept.modality,
                    "display": event.clinical_concept.display,
                    "action_id": event.action_id,
                    "relative_order_min": event.time.relative_order_min,
                    "relative_acquired_min": event.time.relative_acquired_min,
                    "relative_available_min": event.time.relative_available_min,
                    "relative_documented_min": event.time.relative_documented_min,
                    "temporal_confidence": event.time.temporal_confidence.value,
                    "arena_eligible": event.arena.arena_eligible,
                    "replay_mode": event.arena.temporal_replay_mode.value,
                    "result_json": json.dumps(event.result, ensure_ascii=False, sort_keys=True),
                }
                for case in cases
                for event in case.timeline_events
            ]
        ),
        canonical / "temporal_events.parquet",
    )


def _summary(manifest: dict[str, Any]) -> str:
    rows = "\n".join(
        f"| {dataset} | {count} |"
        for dataset, count in sorted(manifest["dataset_case_counts"].items())
    )
    return (
        "# Temporal Forest v2 local build\n\n"
        f"Generated {manifest['case_count']} local case bundles.\n\n"
        "| Dataset | Cases |\n| --- | ---: |\n"
        f"{rows}\n\n"
        "Interaction MVP cases preserve source-authored answers and explicitly label "
        "non-adjudicated references. Patient-level artifacts remain gitignored.\n"
    )


def _graph_index(entries: list[dict[str, Any]]) -> str:
    rows = "".join(
        "<tr>"
        f"<td>{entry['dataset_name']}</td><td>{entry['case_id']}</td>"
        f"<td>{entry['event_count']}</td><td>{entry['eligible_event_count']}</td>"
        f"<td><a href='{entry['review_path'].split('data/processed/temporal/v2/')[-1]}'>review</a></td>"
        "</tr>"
        for entry in entries
    )
    return (
        "<!doctype html><html><head><meta charset='utf-8'><title>Temporal Forest v2</title>"
        "<style>body{font:14px system-ui;margin:24px;color:#102a33}table{border-collapse:collapse;width:100%}"
        "th,td{border:1px solid #cadadd;padding:7px;text-align:left}th{background:#073642;color:white}</style>"
        "</head><body><h1>Temporal Forest v2</h1><table><thead><tr><th>Dataset</th><th>Case</th>"
        f"<th>Events</th><th>Arena eligible</th><th>Review</th></tr></thead><tbody>{rows}</tbody></table></body></html>"
    )


def build(case_count: int = 3) -> dict[str, Any]:
    cases, entries, previous = _load_existing()
    adapters = [
        MediScopeTemporalAdapter(),
        MedPITemporalAdapter(),
        PatientSimTemporalAdapter(),
        MeddiesTemporalAdapter(),
        MedMemoryBenchTemporalAdapter(),
        MedDialogRubricsTemporalAdapter(),
    ]
    built_counts: dict[str, int] = {}
    for adapter in adapters:
        target = min(case_count, 3) if adapter.dataset_slug == "patientsim" else case_count
        candidates = adapter.list_cases(max(20, target * 6))
        dump_json(
            TEMPORAL_ROOT / "candidate_scores" / f"{adapter.dataset_slug}.json",
            {
                "dataset": adapter.dataset_name,
                "selection_policy": "FIRST_SOURCE_CASES_MEETING_ADAPTER_MVP_REQUIREMENTS",
                "candidates": [_candidate_summary(candidate) for candidate in candidates],
            },
        )
        selected = []
        failures = []
        for candidate in candidates:
            try:
                case = attach_conversion_audit(adapter.load_case(candidate), candidate)
            except (ValueError, KeyError, TypeError) as exc:
                failures.append(str(exc))
                continue
            selected.append(case)
            if len(selected) >= target:
                break
        if len(selected) < target:
            raise RuntimeError(
                f"{adapter.dataset_name}: built {len(selected)} cases, requested {target}; "
                f"sample failures={failures[:3]}"
            )
        for case in selected:
            cases.append(case)
            entries.append(adapter.write_case(case))
        built_counts[adapter.dataset_name] = len(selected)

    _write_canonical(cases)
    counts: dict[str, int] = {}
    for entry in entries:
        dataset = entry["dataset_name"]
        counts[dataset] = counts.get(dataset, 0) + 1
    manifest = {
        **previous,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "case_count": len(entries),
        "dataset_case_counts": counts,
        "all_checks_pass": all(all(entry["checks"].values()) for entry in entries),
        "interaction_mvp": {
            "status": "READY",
            "case_count": sum(built_counts.values()),
            "dataset_case_counts": built_counts,
            "download_command": "make download-interaction-mvp",
            "build_command": "make preprocess-interaction-mvp",
        },
        "privacy": (
            "MIXED_LOCAL_ONLY: restricted, DUA-limited, conservatively licensed, and "
            "public-source derivatives; generated patient-level artifacts are gitignored"
        ),
        "cases": entries,
    }
    dump_json(TEMPORAL_ROOT / "manifest.json", manifest)
    (TEMPORAL_ROOT / "summary.md").write_text(_summary(manifest), encoding="utf-8")
    (TEMPORAL_ROOT / "all_graphs.html").write_text(
        _graph_index(entries), encoding="utf-8"
    )
    return manifest


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--cases-per-dataset", type=int, default=3)
    arguments = parser.parse_args()
    manifest = build(arguments.cases_per_dataset)
    detail = manifest["interaction_mvp"]
    print(
        f"Built {detail['case_count']} interaction MVP cases; "
        f"combined manifest now has {manifest['case_count']} cases"
    )


if __name__ == "__main__":
    main()
