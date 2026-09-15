from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone

import pyarrow as pa
import pyarrow.parquet as pq

from etl.common import dump_json, load_json
from etl.temporal_v2 import (
    EICUTemporalAdapter,
    MCMEDTemporalAdapter,
    MIMICTemporalAdapter,
    NEJMTemporalAdapter,
    PMCTemporalAdapter,
)
from etl.temporal_v2.common import (
    ROOT,
    TEMPORAL_ROOT,
    attach_conversion_audit,
    clean,
)
from etl.temporal_v2.validation import (
    validate_eicu,
    validate_mcmed,
    validate_mimic,
)


def build(
    case_count: int = 10,
    narrative_case_count: int = 5,
    validate: bool = True,
) -> dict:
    if validate:
        source_validation = {
            "mcmed": validate_mcmed(),
            "mimic": validate_mimic(),
            "eicu": validate_eicu(),
        }
    else:
        cached = {
            name: TEMPORAL_ROOT / "source_validation" / f"{name}.json"
            for name in ("mcmed", "mimic", "eicu")
        }
        source_validation = (
            {name: load_json(path) for name, path in cached.items()}
            if all(path.exists() for path in cached.values())
            else {"status": "SKIPPED_BY_OPERATOR"}
        )

    adapters = [
        MCMEDTemporalAdapter(),
        MIMICTemporalAdapter(),
        EICUTemporalAdapter(),
        PMCTemporalAdapter(),
        NEJMTemporalAdapter(),
    ]
    cases = []
    entries = []
    candidate_scores = {}
    for adapter in adapters:
        target_count = (
            narrative_case_count
            if adapter.dataset_slug in {"pmc", "nejm"}
            else case_count
        )
        candidate_limit = {
            "mcmed": max(120, case_count * 24),
            "mimic": max(40, case_count * 8),
            "eicu": max(40, case_count * 8),
            "pmc": max(80, narrative_case_count * 16),
            "nejm": max(10, narrative_case_count * 2),
        }[adapter.dataset_slug]
        candidates = adapter.list_cases(candidate_limit)
        serializable_candidates = [
            {key: clean(value) for key, value in candidate.items()}
            for candidate in candidates
        ]
        candidate_scores[adapter.dataset_slug] = serializable_candidates
        dump_json(
            TEMPORAL_ROOT / "candidate_scores" / f"{adapter.dataset_slug}.json",
            {"dataset": adapter.dataset_name, "candidates": serializable_candidates},
        )
        selected = []
        for candidate in candidates:
            try:
                temporal_case = adapter.load_case(candidate)
            except (ValueError, KeyError):
                continue
            selected.append(attach_conversion_audit(temporal_case, candidate))
            if len(selected) >= target_count:
                break
        if len(selected) < target_count:
            raise RuntimeError(
                f"{adapter.dataset_name}: built {len(selected)} cases, requested {target_count}"
            )
        for temporal_case in selected:
            cases.append(temporal_case)
            entries.append(adapter.write_case(temporal_case))

    canonical = TEMPORAL_ROOT / "canonical"
    canonical.mkdir(parents=True, exist_ok=True)
    pq.write_table(
        pa.Table.from_pylist(
            [
                {
                    "case_id": item.case_id,
                    "case_version": item.case_version,
                    "dataset": item.source["dataset_family"],
                    "task_type": item.task_type,
                    "anchor_json": json.dumps(item.anchor, ensure_ascii=False, sort_keys=True),
                    "initial_state_json": json.dumps(item.initial_state, ensure_ascii=False, sort_keys=True),
                    "reference_json": json.dumps(item.reference, ensure_ascii=False, sort_keys=True),
                    "quality_json": json.dumps(item.case_quality, ensure_ascii=False, sort_keys=True),
                }
                for item in cases
            ]
        ),
        canonical / "cases.parquet",
    )
    pq.write_table(
        pa.Table.from_pylist(
            [
                {
                    "case_id": item.case_id,
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
                for item in cases
                for event in item.timeline_events
            ]
        ),
        canonical / "temporal_events.parquet",
    )

    dataset_counts = {}
    for entry in entries:
        dataset_counts[entry["dataset_name"]] = dataset_counts.get(entry["dataset_name"], 0) + 1
    manifest = {
        "schema_version": "clincforestbench.temporal-mvp-manifest.v2",
        "case_version": "2.0.0",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "case_count": len(entries),
        "dataset_case_counts": dataset_counts,
        "all_checks_pass": all(all(entry["checks"].values()) for entry in entries),
        "source_validation": (
            {
                key: value.get("all_required_files_present", False)
                for key, value in source_validation.items()
            }
            if "status" not in source_validation
            else source_validation
        ),
        "privacy": "RESTRICTED_LOCAL_ONLY; generated patient-level artifacts are gitignored",
        "cases": entries,
    }
    dump_json(TEMPORAL_ROOT / "manifest.json", manifest)
    (TEMPORAL_ROOT / "summary.md").write_text(_summary(manifest), encoding="utf-8")
    (TEMPORAL_ROOT / "all_graphs.html").write_text(
        _graph_index(entries), encoding="utf-8"
    )
    return manifest


def _summary(manifest: dict) -> str:
    lines = [
        "# Temporal Forest v2 MVP",
        "",
        f"Generated {manifest['case_count']} restricted, local-only case bundles.",
        "",
        "| Dataset | Cases |",
        "| --- | ---: |",
    ]
    lines.extend(
        f"| {name} | {count} |"
        for name, count in manifest["dataset_case_counts"].items()
    )
    lines.extend(
        [
            "",
            "Each case contains `case.json`, `timeline.parquet`, `realized_path.json`, ",
            "`temporal_graph.json`, and `review.html`. No unrecorded test result is generated.",
        ]
    )
    return "\n".join(lines) + "\n"


def _graph_index(entries: list[dict]) -> str:
    rows = "".join(
        "<tr>"
        f"<td>{entry['dataset_name']}</td>"
        f"<td>{entry['case_id']}</td>"
        f"<td>{entry['event_count']}</td>"
        f"<td>{entry['eligible_event_count']}</td>"
        f"<td><a href='{entry['review_path'].split('data/processed/temporal/v2/')[-1]}'>review</a></td>"
        "</tr>"
        for entry in entries
    )
    return f"""<!doctype html><html><head><meta charset='utf-8'><title>Temporal Forest v2 MVP</title>
<style>body{{font:14px system-ui;margin:24px;color:#102a33}}table{{border-collapse:collapse;width:100%}}th,td{{border:1px solid #cadadd;padding:7px;text-align:left}}th{{background:#073642;color:white}}</style></head>
<body><h1>Temporal Forest v2 MVP</h1><table><thead><tr><th>Dataset</th><th>Case</th><th>Events</th><th>Arena eligible</th><th>Review</th></tr></thead><tbody>{rows}</tbody></table></body></html>"""


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--cases-per-dataset", type=int, default=10)
    parser.add_argument("--narrative-cases-per-dataset", type=int, default=5)
    parser.add_argument("--skip-validation", action="store_true")
    arguments = parser.parse_args()
    manifest = build(
        arguments.cases_per_dataset,
        arguments.narrative_cases_per_dataset,
        validate=not arguments.skip_validation,
    )
    print(
        f"Built {manifest['case_count']} Temporal Forest v2 MVP cases at "
        f"{TEMPORAL_ROOT.relative_to(ROOT)}"
    )


if __name__ == "__main__":
    main()
