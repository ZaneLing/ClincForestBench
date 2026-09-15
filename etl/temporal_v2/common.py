from __future__ import annotations

import html
import json
import math
import re
from abc import ABC, abstractmethod
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence

import duckdb
import pyarrow as pa
import pyarrow.parquet as pq

from backend.app.domain.temporal import (
    CanonicalTemporalEvent,
    ClinicalConcept,
    EventArenaPolicy,
    EventProvenance,
    TemporalCase,
    TemporalConfidence,
    TemporalGraph,
    TemporalGraphEdge,
    TemporalGraphNode,
    TemporalPoint,
    TemporalReplayMode,
)
from etl.common import dump_json


ROOT = Path(__file__).resolve().parents[2]
TEMPORAL_ROOT = ROOT / "data/processed/temporal/v2"


def parse_time(value: Any) -> Optional[datetime]:
    if value in (None, "", "NaT"):
        return None
    if isinstance(value, datetime):
        return value.replace(tzinfo=None)
    text = str(value).strip().replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    if parsed.tzinfo:
        parsed = parsed.astimezone(timezone.utc).replace(tzinfo=None)
    return parsed


def iso(value: Any) -> Optional[str]:
    parsed = parse_time(value)
    return parsed.isoformat(timespec="seconds") if parsed else None


def relative_minutes(value: Any, anchor: datetime) -> Optional[float]:
    parsed = parse_time(value)
    if not parsed:
        return None
    return round((parsed - anchor).total_seconds() / 60, 2)


def clean(value: Any) -> Any:
    if value is None:
        return None
    if isinstance(value, float) and (math.isnan(value) or math.isinf(value)):
        return None
    if isinstance(value, datetime):
        return value.isoformat(timespec="seconds")
    return value


def slug(value: str) -> str:
    text = re.sub(r"[^a-z0-9]+", "_", value.lower()).strip("_")
    return text[:72] or "unknown"


def canonical_action(display: str, modality: str) -> str:
    upper = display.upper()
    rules = (
        (("TROPONIN",), "ORDER_TROPONIN"),
        (("D-DIMER", "D DIMER"), "ORDER_D_DIMER"),
        (("BLOOD GAS", "ABG", "PH, BLOOD"), "ORDER_BLOOD_GAS"),
        (("COMPLETE BLOOD", "CBC", "HEMOGRAM"), "ORDER_CBC"),
        (("COMPREHENSIVE METABOLIC", "CMP"), "ORDER_CMP"),
        (("BASIC METABOLIC", "BMP"), "ORDER_BMP"),
        (("CTA", "CT ANGIO"), "ORDER_CTA"),
        (("CT CHEST",), "ORDER_CT_CHEST"),
        (("CT ABD",), "ORDER_CT_ABDOMEN"),
        (("CHEST", "CXR"), "ORDER_CHEST_XRAY"),
        (("ULTRASOUND", " US "), "ORDER_ULTRASOUND"),
        (("ECG", "EKG", "ELECTROCARD"), "ORDER_ECG"),
    )
    for needles, action in rules:
        if any(needle in upper for needle in needles):
            return action
    prefix = {
        "LAB": "ORDER_LAB",
        "IMAGING": "ORDER_IMAGING",
        "ECG": "ORDER_ECG",
        "HISTORY": "REVIEW_HISTORY",
        "VITALS": "REVIEW_VITAL_TREND",
        "INTERVENTION": "OBSERVE_INTERVENTION",
        "DIAGNOSIS": "REVIEW_DIAGNOSIS",
    }.get(modality, "REVIEW_EVENT")
    return f"{prefix}_{slug(display).upper()[:48]}"


def make_event(
    *,
    case_id: str,
    event_id: str,
    event_type: str,
    display: str,
    modality: str,
    dataset: str,
    source_table: str,
    source_row_id: str,
    anchor: Optional[datetime] = None,
    order_time: Any = None,
    acquired_time: Any = None,
    available_time: Any = None,
    documented_time: Any = None,
    start_time: Any = None,
    end_time: Any = None,
    relative_order_min: Optional[float] = None,
    relative_acquired_min: Optional[float] = None,
    relative_available_min: Optional[float] = None,
    relative_documented_min: Optional[float] = None,
    relative_start_min: Optional[float] = None,
    relative_end_min: Optional[float] = None,
    confidence: str = "HIGH",
    availability_semantics: str,
    result: Optional[Dict[str, Any]] = None,
    action_id: Optional[str] = None,
    arena_eligible: bool = True,
    state_changing: bool = False,
    intervention_before_result: bool = False,
    leakage_risk: str = "LOW",
    exclusion_reason: Optional[str] = None,
    replay_mode: str = "OBSERVED_RESULT_WITH_SHIFTED_TAT",
) -> CanonicalTemporalEvent:
    if anchor:
        relative_order_min = (
            relative_order_min
            if relative_order_min is not None
            else relative_minutes(order_time, anchor)
        )
        relative_acquired_min = (
            relative_acquired_min
            if relative_acquired_min is not None
            else relative_minutes(acquired_time, anchor)
        )
        relative_available_min = (
            relative_available_min
            if relative_available_min is not None
            else relative_minutes(available_time, anchor)
        )
        relative_documented_min = (
            relative_documented_min
            if relative_documented_min is not None
            else relative_minutes(documented_time, anchor)
        )
        relative_start_min = (
            relative_start_min
            if relative_start_min is not None
            else relative_minutes(start_time, anchor)
        )
        relative_end_min = (
            relative_end_min
            if relative_end_min is not None
            else relative_minutes(end_time, anchor)
        )
    action = action_id or canonical_action(display, modality)
    return CanonicalTemporalEvent(
        case_id=case_id,
        event_id=event_id,
        event_type=event_type,
        clinical_concept=ClinicalConcept(
            canonical_id=action.replace("ORDER_", "").replace("REVIEW_", ""),
            display=display,
            source_code=source_row_id,
            source_system=dataset,
            modality=modality,
        ),
        action_id=action,
        time=TemporalPoint(
            order_time=iso(order_time),
            acquired_time=iso(acquired_time),
            available_time=iso(available_time),
            documented_time=iso(documented_time),
            start_time=iso(start_time),
            end_time=iso(end_time),
            relative_order_min=relative_order_min,
            relative_acquired_min=relative_acquired_min,
            relative_available_min=relative_available_min,
            relative_documented_min=relative_documented_min,
            relative_start_min=relative_start_min,
            relative_end_min=relative_end_min,
            temporal_confidence=TemporalConfidence(confidence),
            availability_semantics=availability_semantics,
        ),
        result={key: clean(value) for key, value in (result or {}).items()},
        provenance=EventProvenance(
            dataset=dataset,
            source_table=source_table,
            source_row_id=str(source_row_id),
            is_observed_real_result=True,
        ),
        arena=EventArenaPolicy(
            arena_eligible=arena_eligible,
            state_changing_intervention=state_changing,
            state_changing_intervention_before_result=intervention_before_result,
            leakage_risk=leakage_risk,
            exclusion_reason=exclusion_reason,
            temporal_replay_mode=TemporalReplayMode(replay_mode),
        ),
    )


def build_temporal_graph(case_id: str, events: Sequence[CanonicalTemporalEvent], reference: Dict[str, Any]) -> TemporalGraph:
    nodes: List[TemporalGraphNode] = [
        TemporalGraphNode(
            node_id=f"{case_id}::ROOT",
            node_type="ROOT",
            label="T0",
            subtitle="Case anchor",
            game_time_min=0,
            reveal_time_min=0,
            lane="ANCHOR",
            data={"anchor": "T0"},
        ),
        TemporalGraphNode(
            node_id=f"{case_id}::S0",
            node_type="CONTEXT",
            label="S0",
            subtitle="Initial state",
            game_time_min=0,
            reveal_time_min=0,
            lane="CONTEXT",
            data={"state": "initial_state"},
        ),
    ]
    edges: List[TemporalGraphEdge] = [
        TemporalGraphEdge(
            edge_id=f"{case_id}::ROOT_TO_S0",
            source_node=f"{case_id}::ROOT",
            target_node=f"{case_id}::S0",
            edge_type="INITIAL_STATE",
            action_time_min=0,
            result_available_time_min=0,
            latency_min=0,
        )
    ]
    previous = f"{case_id}::S0"
    ordered = sorted(events, key=lambda item: (item.order_min(), item.available_min(), item.event_id))
    for index, event in enumerate(ordered, 1):
        order_min = event.order_min()
        available_min = max(order_min, event.available_min())
        lane = event.clinical_concept.modality
        action_node = f"{event.event_id}::ACTION"
        result_node = f"{event.event_id}::RESULT"
        nodes.append(
            TemporalGraphNode(
                node_id=action_node,
                node_type="INTERVENTION" if event.arena.state_changing_intervention else "ACTION",
                label=event.action_id or "OBSERVE",
                subtitle=event.clinical_concept.display,
                game_time_min=order_min,
                reveal_time_min=order_min,
                lane=lane,
                event_id=event.event_id,
                temporal_confidence=event.time.temporal_confidence,
                data={"sequence": index, "arena_eligible": event.arena.arena_eligible},
            )
        )
        edges.append(
            TemporalGraphEdge(
                edge_id=f"{event.event_id}::ORDER_SEQUENCE",
                source_node=previous,
                target_node=action_node,
                edge_type="ORDER_SEQUENCE",
                action_id=event.action_id,
                action_time_min=order_min,
                result_available_time_min=available_min,
                latency_min=max(0, available_min - order_min),
                source_event_id=event.event_id,
            )
        )
        nodes.append(
            TemporalGraphNode(
                node_id=result_node,
                node_type="RESULT",
                label=event.clinical_concept.display,
                subtitle="Result available",
                game_time_min=available_min,
                reveal_time_min=available_min,
                lane=lane,
                event_id=event.event_id,
                temporal_confidence=event.time.temporal_confidence,
                data={
                    "result": event.result,
                    "availability_semantics": event.time.availability_semantics,
                    "arena_eligible": event.arena.arena_eligible,
                },
            )
        )
        edges.append(
            TemporalGraphEdge(
                edge_id=f"{event.event_id}::RESULT_AVAILABLE",
                source_node=action_node,
                target_node=result_node,
                edge_type="RESULT_AVAILABLE",
                action_id=event.action_id,
                action_time_min=order_min,
                result_available_time_min=available_min,
                latency_min=max(0, available_min - order_min),
                result_status="OBSERVED",
                source_event_id=event.event_id,
            )
        )
        previous = action_node

    reference_name = (
        reference.get("adjudicated_primary_diagnosis")
        or reference.get("primary_diagnosis")
        or reference.get("hospital_principal_diagnosis")
        or reference.get("reference_diagnosis")
        or "Reference outcome"
    )
    if isinstance(reference_name, list):
        reference_name = reference_name[0] if reference_name else "Reference outcome"
    final_time = max([item.available_min() for item in ordered] or [0]) + 5
    reference_id = f"{case_id}::REFERENCE"
    nodes.append(
        TemporalGraphNode(
            node_id=reference_id,
            node_type="REFERENCE",
            label=str(reference_name),
            subtitle="Retrospective reference",
            game_time_min=final_time,
            reveal_time_min=final_time,
            lane="REFERENCE",
            data=reference,
        )
    )
    result_nodes = [item.node_id for item in nodes if item.node_type == "RESULT"][-5:]
    for source_id in result_nodes or [previous]:
        edges.append(
            TemporalGraphEdge(
                edge_id=f"{source_id}::TO_REFERENCE",
                source_node=source_id,
                target_node=reference_id,
                edge_type="SUPPORTS_REFERENCE",
                result_available_time_min=final_time,
                result_status="REFERENCE_ONLY",
            )
        )
    return TemporalGraph(root_id=f"{case_id}::ROOT", nodes=nodes, edges=edges)


def build_mvp_simulations(events: Sequence[CanonicalTemporalEvent]) -> List[Dict[str, Any]]:
    eligible = [item for item in events if item.arena.arena_eligible]
    ordered = sorted(eligible, key=lambda item: (item.order_min(), item.event_id))
    targeted_priority = {"ECG": 0, "LAB": 1, "IMAGING": 2, "HISTORY": 3, "VITALS": 4}
    paths = {
        "FAST_TARGETED": sorted(
            ordered,
            key=lambda item: (
                targeted_priority.get(item.clinical_concept.modality, 9),
                item.available_min() - item.order_min(),
            ),
        )[:5],
        "BROAD_WORKUP": ordered[:8],
        "CONTEXT_FIRST": sorted(
            ordered,
            key=lambda item: (
                0 if item.clinical_concept.modality in {"HISTORY", "VITALS"} else 1,
                item.order_min(),
            ),
        )[:6],
    }
    result = []
    for name, path in paths.items():
        game_time = 0.0
        steps = []
        for event in path:
            latency = max(0.0, event.available_min() - event.order_min())
            available_at = round(game_time + latency, 2)
            steps.append(
                {
                    "action": event.action_id,
                    "ordered_at_min": game_time,
                    "available_at_min": available_at,
                    "source_event_id": event.event_id,
                    "result_origin": "OBSERVED_REAL_RESULT",
                }
            )
            game_time += 1
        if steps:
            game_time = max(item["available_at_min"] for item in steps)
        result.append(
            {
                "strategy": name,
                "steps": steps,
                "final_time_min": round(game_time + 1, 2),
                "synthetic_result_count": 0,
            }
        )
    return result


def attach_conversion_audit(
    case: TemporalCase, candidate: Dict[str, Any]
) -> TemporalCase:
    """Attach the exact selected source slice and a readable conversion trace."""
    raw_events = [
        {
            "source_table": event.provenance.source_table,
            "source_row_id": event.provenance.source_row_id,
            "source_time_fields": {
                "order_time": event.time.order_time,
                "acquired_time": event.time.acquired_time,
                "available_time": event.time.available_time,
                "documented_time": event.time.documented_time,
                "start_time": event.time.start_time,
                "end_time": event.time.end_time,
            },
            "source_result_fields": event.result,
        }
        for event in case.timeline_events
    ]
    raw_source = case.raw_source or {
        "candidate_row": {key: clean(value) for key, value in candidate.items()},
        "event_source_extracts": raw_events,
        "scope_note": (
            "Exact source fields selected for this Case; unrelated patient rows "
            "are intentionally excluded from the review artifact."
        ),
    }
    transformation = case.transformation or {
        "schema_version": "clincforestbench.temporal-conversion-audit.v2",
        "steps": [
            {
                "step": 1,
                "name": "Select episode and define T0",
                "input": "candidate_row",
                "output": "anchor + initial_state",
                "rule": case.anchor.get("anchor_type", "SOURCE_DEFINED_ANCHOR"),
            },
            {
                "step": 2,
                "name": "Normalize source events",
                "input": "event_source_extracts",
                "output": "timeline_events",
                "rule": (
                    "Keep order/acquired/available/documented/start/end separate; "
                    "convert source time to minutes from T0."
                ),
            },
            {
                "step": 3,
                "name": "Apply Arena safety policy",
                "input": "timeline_events",
                "output": "hidden_evidence_pool",
                "rule": (
                    "Only recorded results may be revealed; post-intervention or "
                    "high-leakage events remain visible to audit but cannot be reordered."
                ),
            },
            {
                "step": 4,
                "name": "Build dynamic graph",
                "input": "initial_state + eligible events + reference",
                "output": "temporal_graph",
                "rule": (
                    "Create separate action and result nodes, connect them by result "
                    "latency, then add the retrospective reference node."
                ),
            },
        ],
        "field_mappings": {
            "case anchor": "anchor",
            "presentation at T0": "initial_state",
            "recorded source rows": "timeline_events[].provenance + result",
            "six time semantics": "timeline_events[].time",
            "doctor-selectable evidence": "hidden_evidence_pool",
            "tree / DAG": "temporal_graph.nodes + temporal_graph.edges",
        },
        "safety_invariants": [
            "NO_SYNTHETIC_CLINICAL_RESULTS",
            "REFERENCE_HIDDEN_UNTIL_FINALIZATION",
            "UNRECORDED_ACTION_RETURNS_UNOBSERVED",
            "TIME_IS_PART_OF_STATE",
        ],
    }
    return case.model_copy(
        update={"raw_source": raw_source, "transformation": transformation}
    )


def review_html(case: TemporalCase) -> str:
    eligible = {item.event_id for item in case.timeline_events if item.arena.arena_eligible}
    rows = []
    for event in sorted(case.timeline_events, key=lambda item: (item.order_min(), item.available_min())):
        rows.append(
            "<tr>"
            f"<td>{html.escape(event.event_id)}</td>"
            f"<td>{event.order_min():.1f}</td>"
            f"<td>{event.available_min():.1f}</td>"
            f"<td>{html.escape(event.clinical_concept.modality)}</td>"
            f"<td>{html.escape(event.clinical_concept.display)}</td>"
            f"<td>{'YES' if event.event_id in eligible else 'NO'}</td>"
            f"<td>{html.escape(event.arena.exclusion_reason or '')}</td>"
            "</tr>"
        )
    return f"""<!doctype html><html><head><meta charset='utf-8'><title>{html.escape(case.case_id)}</title>
<style>body{{font:14px system-ui;margin:24px;color:#102a33}}pre{{white-space:pre-wrap;background:#eef6f7;padding:12px}}table{{border-collapse:collapse;width:100%}}th,td{{border:1px solid #cadadd;padding:6px;text-align:left}}th{{background:#073642;color:white}}</style></head><body>
<h1>{html.escape(case.case_id)} · Temporal Forest v2 review</h1>
<h2>S0</h2><pre>{html.escape(json.dumps(case.initial_state, ensure_ascii=False, indent=2))}</pre>
<h2>Timeline</h2><table><thead><tr><th>Event</th><th>Order</th><th>Available</th><th>Modality</th><th>Concept</th><th>Arena</th><th>Exclusion</th></tr></thead><tbody>{''.join(rows)}</tbody></table>
<h2>Reference</h2><pre>{html.escape(json.dumps(case.reference, ensure_ascii=False, indent=2))}</pre>
<h2>Temporal warnings</h2><pre>{html.escape(json.dumps(case.temporal_quality.get('warnings', []), ensure_ascii=False, indent=2))}</pre>
</body></html>"""


class TemporalAdapter(ABC):
    dataset_slug: str
    dataset_name: str

    def __init__(self, root: Path = ROOT):
        self.root = root
        self.connection = duckdb.connect()
        self.connection.execute("PRAGMA threads=4")

    @abstractmethod
    def list_cases(self, limit: int = 20) -> List[Dict[str, Any]]:
        raise NotImplementedError

    @abstractmethod
    def load_case(self, candidate: Dict[str, Any]) -> TemporalCase:
        raise NotImplementedError

    def build_cases(self, limit: int = 5) -> List[TemporalCase]:
        cases = []
        for candidate in self.list_cases(max(limit * 4, 20)):
            try:
                cases.append(self.load_case(candidate))
            except (ValueError, KeyError):
                continue
            if len(cases) >= limit:
                break
        if len(cases) < limit:
            raise RuntimeError(
                f"{self.dataset_name}: only {len(cases)} eligible cases, need {limit}"
            )
        return cases

    def write_case(self, case: TemporalCase) -> Dict[str, Any]:
        folder = TEMPORAL_ROOT / "case_bundles" / self.dataset_slug / case.case_id
        dump_json(folder / "case.json", case.model_dump(mode="json"))
        dump_json(folder / "realized_path.json", case.realized_trajectory)
        dump_json(folder / "temporal_graph.json", case.temporal_graph.model_dump(mode="json"))
        timeline_rows = []
        for event in case.timeline_events:
            timeline_rows.append(
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
                    "availability_semantics": event.time.availability_semantics,
                    "arena_eligible": event.arena.arena_eligible,
                    "temporal_replay_mode": event.arena.temporal_replay_mode.value,
                    "result_json": json.dumps(event.result, ensure_ascii=False, sort_keys=True),
                    "provenance_json": json.dumps(
                        event.provenance.model_dump(mode="json"),
                        ensure_ascii=False,
                        sort_keys=True,
                    ),
                }
            )
        pq.write_table(pa.Table.from_pylist(timeline_rows), folder / "timeline.parquet")
        (folder / "review.html").write_text(review_html(case), encoding="utf-8")
        return {
            "case_id": case.case_id,
            "dataset_name": self.dataset_name,
            "task_type": case.task_type,
            "reference_label": case.reference.get("adjudicated_primary_diagnosis")
            or case.reference.get("primary_diagnosis")
            or case.reference.get("hospital_principal_diagnosis")
            or case.reference.get("reference_diagnosis"),
            "event_count": len(case.timeline_events),
            "eligible_event_count": sum(
                item.arena.arena_eligible for item in case.timeline_events
            ),
            "max_time_min": max(
                [item.reveal_time_min for item in case.temporal_graph.nodes] or [0]
            ),
            "temporal_confidence_counts": _confidence_counts(case.timeline_events),
            "path": str(folder.relative_to(ROOT) / "case.json"),
            "review_path": str(folder.relative_to(ROOT) / "review.html"),
            "checks": case.case_quality.get("checks", {}),
        }


def _confidence_counts(events: Iterable[CanonicalTemporalEvent]) -> Dict[str, int]:
    counts: Dict[str, int] = {}
    for event in events:
        key = event.time.temporal_confidence.value
        counts[key] = counts.get(key, 0) + 1
    return counts
