from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable

import pyarrow as pa
import pyarrow.parquet as pq

from backend.app.repositories.base import ArenaRepository
from backend.app.services.case_service import CaseService
from backend.app.services.graph_builder import build_case_graph
from etl.common import dump_json


def _write(rows: list[dict], path: Path) -> None:
    table = pa.Table.from_pylist(rows) if rows else pa.table({"_empty": pa.array([], type=pa.string())})
    pq.write_table(table, path, compression="zstd")


class ExportService:
    def __init__(self, cases: CaseService, repository: ArenaRepository, root: Path) -> None:
        self.cases = cases
        self.repository = repository
        self.root = root

    def export(self, session_id: str | None = None) -> Path:
        stamp = datetime.now(timezone.utc).strftime("export_%Y%m%dT%H%M%SZ")
        output = self.root / stamp
        output.mkdir(parents=True, exist_ok=False)
        sessions = self.repository.all_sessions()
        if session_id:
            sessions = [item for item in sessions if item.session_id == session_id]
            if not sessions:
                raise KeyError(f"Unknown session: {session_id}")
        ids = {item.session_id for item in sessions}
        events = [event for sid in ids for event in self.repository.events(sid)]
        states = [state for sid in ids for state in self.repository.states(sid)]
        beliefs = [belief for sid in ids for belief in self.repository.beliefs(sid)]
        selected_cases = {item.case_id for item in sessions}
        case_rows = []
        for case_id in sorted(selected_cases):
            bundle = self.cases.get(case_id)
            case_rows.append(
                {
                    "case_id": bundle.case_id,
                    "case_hash": bundle.case_hash,
                    "dataset_json": json.dumps(bundle.dataset.model_dump(mode="json"), sort_keys=True),
                    "demographics_json": json.dumps(bundle.demographics.model_dump(mode="json"), sort_keys=True),
                    "initial_evidence_json": json.dumps(bundle.initial_evidence.model_dump(mode="json"), sort_keys=True),
                    "truth_json": json.dumps([item.model_dump(mode="json") for item in bundle.truth], sort_keys=True),
                    "oracle_json": json.dumps(bundle.oracle.model_dump(mode="json"), sort_keys=True),
                    "metadata_json": json.dumps(bundle.metadata.model_dump(mode="json"), sort_keys=True),
                }
            )
        _write(case_rows, output / "cases.parquet")
        _write([item.model_dump(mode="json") for item in sessions], output / "sessions.parquet")
        _write(
            [
                {
                    **item.model_dump(mode="json", exclude={"action", "observation"}),
                    "action_json": json.dumps(item.action, sort_keys=True),
                    "observation_json": json.dumps(item.observation, sort_keys=True),
                }
                for item in events
            ],
            output / "events.parquet",
        )
        _write(
            [
                {
                    "session_id": item.session_id,
                    "step": item.step,
                    "state_hash": item.state.state_hash,
                    "revealed_evidence_ids": sorted(item.state.revealed),
                    "state_json": item.state.model_dump_json(),
                    "created_at": item.created_at,
                }
                for item in states
            ],
            output / "states.parquet",
        )
        belief_rows = []
        for snapshot in beliefs:
            for diagnosis in snapshot.belief.diagnoses:
                belief_rows.append({
                    "belief_id": snapshot.belief_id, "session_id": snapshot.session_id,
                    "step": snapshot.step, "state_hash": snapshot.state_hash,
                    "diagnosis_id": diagnosis.condition_id, "rank": diagnosis.rank,
                    "probability": diagnosis.probability,
                    "overall_confidence": snapshot.belief.overall_confidence,
                    "is_final": snapshot.is_final, "timestamp": snapshot.timestamp,
                })
        _write(belief_rows, output / "beliefs.parquet")
        graphs = [
            build_case_graph(
                cid, sessions,
                {sid: self.repository.events(sid) for sid in ids},
                {sid: self.repository.states(sid) for sid in ids},
            ) for cid in sorted(selected_cases)
        ]
        _write([node.model_dump(mode="json") for graph in graphs for node in graph.nodes], output / "graph_nodes.parquet")
        _write([edge.model_dump(mode="json") for graph in graphs for edge in graph.edges], output / "graph_edges.parquet")
        for session in sessions:
            dump_json(output / f"session_bundle_{session.session_id}.json", {
                "case_bundle": self.cases.get(session.case_id).model_dump(mode="json"),
                "session": session.model_dump(mode="json"),
                "events": [e.model_dump(mode="json") for e in self.repository.events(session.session_id)],
                "states": [s.model_dump(mode="json") for s in self.repository.states(session.session_id)],
                "beliefs": [b.model_dump(mode="json") for b in self.repository.beliefs(session.session_id)],
            })
        return output
