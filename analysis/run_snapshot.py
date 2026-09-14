from __future__ import annotations

import argparse
import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq

from analysis.metrics import belief_updates, edge_metrics
from etl.common import ddx_config, dump_json, load_json, path_from_root


def read_rows(path: Path) -> list[dict]:
    if not path.exists():
        return []
    table = pq.read_table(path)
    return [] if table.column_names == ["_empty"] else table.to_pylist()


def write_rows(path: Path, rows: list[dict]) -> None:
    table = pa.Table.from_pylist(rows) if rows else pa.table({"_empty": pa.array([], type=pa.string())})
    pq.write_table(table, path, compression="zstd")


def main() -> None:
    parser = argparse.ArgumentParser(description="Create a versioned analysis snapshot")
    parser.add_argument("export_dir", type=Path)
    parser.add_argument("--version", default="analysis_v001")
    args = parser.parse_args()
    output = path_from_root("data/analysis_runs") / args.version
    output.mkdir(parents=True, exist_ok=False)
    sessions = read_rows(args.export_dir / "sessions.parquet")
    case_rows = read_rows(args.export_dir / "cases.parquet")
    events = read_rows(args.export_dir / "events.parquet")
    beliefs = read_rows(args.export_dir / "beliefs.parquet")
    edges = read_rows(args.export_dir / "graph_edges.parquet")
    session_metrics = []
    cases = {row["case_id"]: json.loads(row["oracle_json"]) for row in case_rows}
    for session in sessions:
        own_events = [row for row in events if row["session_id"] == session["session_id"]]
        final_beliefs = [
            row for row in beliefs
            if row["session_id"] == session["session_id"] and row["is_final"]
        ]
        final_beliefs.sort(key=lambda row: row["rank"])
        oracle = cases.get(session["case_id"], {})
        pathology = oracle.get("pathology")
        final_ids = [row["diagnosis_id"] for row in final_beliefs]
        oracle_ids = {row["condition"] for row in oracle.get("differential", [])}
        session_metrics.append(
            {
                "session_id": session["session_id"],
                "case_id": session["case_id"],
                "number_of_questions": sum(row["event_type"] == "ASK_EVIDENCE" for row in own_events),
                "redundant_question_count": sum(row.get("result_type") == "REPEATED_QUERY" for row in own_events),
                "status": session["status"],
                "final_state_hash": session.get("final_state_hash"),
                "final_accuracy": bool(final_ids and final_ids[0] == pathology),
                "top3_accuracy": pathology in final_ids[:3],
                "top5_accuracy": pathology in final_ids[:5],
                "pathology_rank": final_ids.index(pathology) + 1 if pathology in final_ids else None,
                "oracle_differential_coverage": (
                    len(set(final_ids) & oracle_ids) / len(oracle_ids) if oracle_ids else 0.0
                ),
            }
        )
    write_rows(output / "session_metrics.parquet", session_metrics)
    write_rows(output / "belief_update_metrics.parquet", belief_updates(beliefs))
    write_rows(output / "edge_metrics.parquet", edge_metrics(edges))
    case_metrics = [
        {
            "case_id": case_id,
            "session_count": sum(row["case_id"] == case_id for row in session_metrics),
            "mean_questions": (
                sum(row["number_of_questions"] for row in session_metrics if row["case_id"] == case_id)
                / max(1, sum(row["case_id"] == case_id for row in session_metrics))
            ),
        }
        for case_id in sorted(cases)
    ]
    write_rows(output / "case_metrics.parquet", case_metrics)
    write_rows(output / "state_metrics.parquet", [])
    (output / "figures").mkdir()
    config = ddx_config()
    try:
        git_commit = subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip()
    except (subprocess.CalledProcessError, FileNotFoundError):
        git_commit = "UNVERSIONED"
    dump_json(
        output / "metadata.json",
        {
            "analysis_version": args.version,
            "git_commit": git_commit,
            "dataset_version": config["dataset"]["dataset_version"],
            "manifest_version": load_json(path_from_root("data/manifests/mvp50_manifest.json"))["manifest_version"],
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "source_export": str(args.export_dir),
            "metrics": ["path_efficiency", "belief_update", "branch_entropy"],
        },
    )
    print(output)


if __name__ == "__main__":
    main()
