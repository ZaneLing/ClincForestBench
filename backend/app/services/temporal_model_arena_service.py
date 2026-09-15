from __future__ import annotations

import json
import threading
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from backend.app.services.model_arena_service import ModelArenaService
from backend.app.services.temporal_arena_service import TemporalArenaService
from backend.app.services.temporal_case_service import TemporalCaseService


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class TemporalModelArenaService:
    """Run OpenRouter models through the same Temporal state machine as doctors."""

    def __init__(
        self,
        root: Path,
        cases: TemporalCaseService,
        arena: TemporalArenaService,
        gateway: ModelArenaService,
    ) -> None:
        self.root = root / "data/processed/temporal/v2/model_runs"
        self.root.mkdir(parents=True, exist_ok=True)
        self.cases = cases
        self.arena = arena
        self.gateway = gateway
        self._lock = threading.RLock()

    def create_run(
        self, model_id: str, case_id: str, max_actions: int = 30
    ) -> dict[str, Any]:
        if not self.gateway.settings.openrouter_api_key:
            raise ValueError("OPENROUTER_API_KEY is not configured on the API server")
        if not model_id or "/" not in model_id:
            raise ValueError("A valid OpenRouter model id is required")
        if not 1 <= max_actions <= 30:
            raise ValueError("max_actions must be between 1 and 30")
        case = self.cases.get(case_id)
        run_id = f"TMR-{uuid.uuid4()}"
        owner = f"model:{run_id}"
        state = self.arena.create(case_id, owner)
        run = {
            "schema_version": "clincforestbench.temporal-model-run.v1",
            "run_id": run_id,
            "session_id": state["session_id"],
            "owner": owner,
            "model_id": model_id,
            "provider": model_id.split("/", 1)[0],
            "case_id": case_id,
            "dataset_name": case.source.get("dataset_family", "Temporal v2"),
            "status": "ACTIVE",
            "max_actions": max_actions,
            "forced_final": False,
            "last_error": None,
            "created_at": _now(),
            "completed_at": None,
            "interactions": [],
        }
        self._save(run)
        return self.detail(run_id)

    def list_runs(self, case_id: str | None = None) -> dict[str, Any]:
        rows = []
        for path in self.root.glob("*.json"):
            try:
                run = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                continue
            if case_id and run.get("case_id") != case_id:
                continue
            rows.append(self._summary(run))
        rows.sort(key=lambda item: item["created_at"], reverse=True)
        return {"runs": rows}

    def detail(self, run_id: str) -> dict[str, Any]:
        run = self._load(run_id)
        state = self.arena.get(run["session_id"], run["owner"])
        public_run = {key: value for key, value in run.items() if key != "interactions"}
        result: dict[str, Any] = {
            "run": public_run,
            "state": state,
            "interactions": run["interactions"],
        }
        if run["status"] == "COMPLETED":
            review = self.arena.review(run["session_id"], run["owner"])
            case = self.cases.get(run["case_id"])
            evaluation = self._evaluate_run(
                run,
                review["session"],
                case,
                review["comparison"],
            )
            result["review"] = review
            result["evaluation"] = evaluation
            case_evaluation = self.arena.forest_detail(run["case_id"])[
                "trajectory_evaluation"
            ]
            result["case_evaluation"] = case_evaluation
            result["case_record"] = case.model_dump(mode="json")
            result["artifact"] = {
                "schema_version": "clincforestbench.temporal-model-artifact.v1",
                "model_run": public_run,
                "temporal_session": review["session"],
                "comparison": review["comparison"],
                "evaluation": evaluation,
                "case_evaluation_snapshot": case_evaluation,
                "case_record": case.model_dump(mode="json"),
                "interactions": run["interactions"],
            }
        return result

    def step(self, run_id: str) -> dict[str, Any]:
        with self._lock:
            run = self._load(run_id)
            if run["status"] != "ACTIVE":
                raise ValueError("Temporal model run is not active")
            state = self.arena.get(run["session_id"], run["owner"])
            request_payload = self._build_request(run, state)
            started = time.monotonic()
            response_payload: dict[str, Any] | None = None
            assistant_content: str | None = None
            parsed_decision: dict[str, Any] | None = None
            application_result: dict[str, Any] | None = None
            error: str | None = None
            try:
                response_payload = self.gateway._request(
                    "POST", "/chat/completions", request_payload
                )
                assistant_content = self.gateway._assistant_content(response_payload)
                parsed_decision = self.gateway._normalize_decision_payload(
                    self.gateway._parse_json_object(assistant_content)
                )
                parsed_decision = self._validate_decision(parsed_decision)
                application_result = self._apply(run, state, parsed_decision)
            except Exception as exc:  # provider and validation errors are audit data
                error = self.gateway._safe_error(exc)

            interaction = {
                "interaction_id": f"TMI-{uuid.uuid4()}",
                "run_id": run_id,
                "step": len(run["interactions"]) + 1,
                "request_payload": request_payload,
                "response_payload": response_payload,
                "assistant_content": assistant_content,
                "parsed_decision": parsed_decision,
                "application_result": application_result,
                "error": error,
                "latency_ms": round((time.monotonic() - started) * 1000),
                "created_at": _now(),
            }
            run["interactions"].append(interaction)
            run["last_error"] = error
            updated_state = self.arena.get(run["session_id"], run["owner"])
            if updated_state["status"] == "COMPLETED":
                run["status"] = "COMPLETED"
                run["completed_at"] = _now()
                run["forced_final"] = bool(
                    application_result and application_result.get("forced_final")
                )
            self._save(run)
            return self.detail(run_id)

    def _build_request(self, run: dict[str, Any], state: dict[str, Any]) -> dict[str, Any]:
        history = [
            {
                "step": item["step"],
                "decision": item.get("parsed_decision"),
                "result": item.get("application_result"),
            }
            for item in run["interactions"][-8:]
            if item.get("parsed_decision") and not item.get("error")
        ]
        rejected_attempts = [
            {
                "attempted_decision": item.get("parsed_decision"),
                "rejection": item.get("error"),
            }
            for item in run["interactions"][-3:]
            if item.get("error")
        ]
        action_library = [
            {
                **item,
                "status": "AVAILABLE",
            }
            for item in state["available_actions"]
        ]
        turn = {
            "arena": {
                "benchmark": "ClincForestBench Temporal Forest v2",
                "dataset": state["dataset_name"],
                "case_id": state["case_id"],
                "task_type": state["task_type"],
                "action_count": state["action_count"],
                "max_actions": run["max_actions"],
                "early_stop_policy": "MODEL_DECIDES",
                "automatic_early_stop": False,
                "must_finalize_now": state["action_count"] >= run["max_actions"],
            },
            "patient_state": {
                "initial_state": state["initial_state"],
                "current_time_min": state["current_time_min"],
                "revealed_events": state["revealed_events"],
                "pending_actions": state["pending_actions"],
            },
            "diagnostic_progress": {
                "previous_decisions": history,
                "rejected_attempts_to_correct": rejected_attempts,
            },
            "disease_library": state["diagnosis_catalog"],
            "action_library": action_library,
            "rules": [
                "Rank unique diagnoses using exact strings from disease_library.",
                "Never repeat an action. Choose exactly one AVAILABLE action_id when final is false.",
                "Selecting an action returns synchronously: the simulation clock advances to that recorded result time without real-world waiting.",
                "There is no automatic early-stop threshold. You decide when the evidence is sufficient to finalize.",
                "Do not finalize merely because the same diagnosis remained Top-1 across several turns.",
                "The action ceiling is a safety limit. If it is reached, the current Top-1 is finalized automatically.",
                "Use only exact action_id values from action_library; free-form or invented actions are rejected.",
                "If rejected_attempts_to_correct is non-empty, correct the prior contract error instead of repeating it.",
                "A valid catalog action may be absent from this recorded episode. In that case the environment returns UNOBSERVED_IN_RECORDED_EPISODE; never fabricate a result and do not repeat that action.",
                "If continuing, rationale must name what competing diagnoses the action separates.",
            ],
            "output_contract": {
                "diagnoses": ["exact disease strings in rank order; no duplicates"],
                "next_action_id": "one AVAILABLE id, or null when final",
                "final": "boolean",
                "final_diagnosis": "one disease string when final, otherwise null",
                "rationale": "brief clinical explanation",
            },
        }
        system = (
            "You are a clinician playing ClincForestBench Temporal Forest v2. "
            "Return exactly one top-level JSON object and no markdown. Do not expose "
            "chain-of-thought; give only a brief clinical rationale. Update the ranked "
            "differential after newly revealed evidence. Test turnaround remains a "
            "simulation-time feature, but every selected action returns immediately "
            "after the clock advances—never request WAIT. Optimize diagnostic "
            "correctness and information gain. There is no heuristic early stop: you "
            "may set final=true at any turn when you judge the evidence sufficient, or "
            "continue up to the hard action ceiling. Never invent a disease or action string."
        )
        return {
            "model": run["model_id"],
            "messages": [
                {"role": "system", "content": system},
                {
                    "role": "user",
                    "content": json.dumps(turn, ensure_ascii=False, separators=(",", ":")),
                },
            ],
            "temperature": 0,
            "max_tokens": 1000,
        }

    @staticmethod
    def _validate_decision(value: dict[str, Any]) -> dict[str, Any]:
        diagnoses = value.get("diagnoses")
        if not isinstance(diagnoses, list) or not diagnoses:
            raise ValueError("Model decision requires a non-empty diagnoses list")
        normalized = [str(item).strip() for item in diagnoses if str(item).strip()]
        if not normalized or len({item.casefold() for item in normalized}) != len(normalized):
            raise ValueError("Model diagnoses must be non-empty and unique")
        final = value.get("final")
        if not isinstance(final, bool):
            raise ValueError("Model decision final must be a boolean")
        next_action = value.get("next_action_id")
        final_diagnosis = value.get("final_diagnosis") or value.get("final_condition_id")
        return {
            "diagnoses": normalized,
            "next_action_id": str(next_action).strip() if next_action else None,
            "final": final,
            "final_diagnosis": str(final_diagnosis).strip() if final_diagnosis else None,
            "rationale": str(value.get("rationale") or "").strip(),
        }

    def _apply(
        self,
        run: dict[str, Any],
        state: dict[str, Any],
        decision: dict[str, Any],
    ) -> dict[str, Any]:
        catalog = state["diagnosis_catalog"]
        by_casefold = {item.casefold(): item for item in catalog}
        unknown = [item for item in decision["diagnoses"] if item.casefold() not in by_casefold]
        if unknown:
            raise ValueError(f"Model returned unknown diagnoses: {', '.join(unknown)}")
        diagnoses = [by_casefold[item.casefold()] for item in decision["diagnoses"]]
        forced_final = state["action_count"] >= run["max_actions"]
        should_finalize = decision["final"] or forced_final

        if state["belief_required"]:
            state = self.arena.submit_belief(run["session_id"], run["owner"], diagnoses)
        result: dict[str, Any] = {
            "checkpoint": state["checkpoint"],
            "diagnoses": diagnoses,
            "forced_final": forced_final,
        }
        if should_finalize:
            requested = decision["final_diagnosis"] or diagnoses[0]
            if requested.casefold() not in by_casefold:
                raise ValueError("final_diagnosis is not in the disease library")
            final_diagnosis = by_casefold[requested.casefold()]
            review = self.arena.finalize(
                run["session_id"], run["owner"], [final_diagnosis]
            )
            result.update(
                {
                    "result_type": "FINAL",
                    "final_diagnosis": final_diagnosis,
                    "comparison": review["comparison"],
                }
            )
            return result

        action_id = decision["next_action_id"]
        if not action_id:
            raise ValueError("next_action_id is required when final is false")
        if action_id == "WAIT":
            raise ValueError(
                "WAIT is no longer an Arena action; choose a clinical action or finalize"
            )

        available = {item["action_id"] for item in state["available_actions"]}
        if action_id not in available:
            raise ValueError("next_action_id is repeated, unknown, or unavailable")
        next_state = self.arena.order(
            run["session_id"], run["owner"], action_id
        )
        result.update(
            {
                "result_type": "ORDER",
                "action_id": action_id,
                "outcome": next_state.get("last_action_outcome"),
            }
        )
        return result

    @staticmethod
    def _summary(run: dict[str, Any]) -> dict[str, Any]:
        return {
            key: value
            for key, value in run.items()
            if key not in {"owner", "interactions"}
        } | {"interaction_count": len(run.get("interactions", []))}

    @staticmethod
    def _evaluate_run(
        run: dict[str, Any],
        session: dict[str, Any],
        case: Any,
        comparison: dict[str, Any],
    ) -> dict[str, Any]:
        """Compute policy metrics without treating the recorded source path as optimal.

        The retrospective diagnosis is a reference outcome.  The recorded event
        trajectory is useful for coverage and timing, but it is not an oracle
        sequence of actions; a shorter alternative path can be clinically valid.
        """
        reference = str(comparison.get("ground_truth_diagnosis") or "")
        reference_key = reference.casefold()
        beliefs = session.get("belief_history", [])
        reference_trace = []
        first_reference = None
        first_correct_top1 = None
        for belief in beliefs:
            diagnoses = [str(item) for item in belief.get("diagnoses", [])]
            keys = [item.casefold() for item in diagnoses]
            rank = keys.index(reference_key) + 1 if reference_key in keys else None
            point = {
                "checkpoint": belief.get("checkpoint"),
                "game_time_min": belief.get("game_time_min"),
                "rank": rank,
            }
            reference_trace.append(point)
            if rank is not None and first_reference is None:
                first_reference = point
            if rank == 1 and first_correct_top1 is None:
                first_correct_top1 = point

        last_rank = reference_trace[-1]["rank"] if reference_trace else None
        top1 = [
            str(item.get("diagnoses", [""])[0])
            for item in beliefs
            if item.get("diagnoses")
        ]
        top1_revisions = sum(
            left.casefold() != right.casefold()
            for left, right in zip(top1, top1[1:])
        )
        differential_revisions = sum(
            tuple(map(str.casefold, left.get("diagnoses", [])))
            != tuple(map(str.casefold, right.get("diagnoses", [])))
            for left, right in zip(beliefs, beliefs[1:])
        )
        consecutive_jaccards = []
        for left, right in zip(beliefs, beliefs[1:]):
            left_set = {str(item).casefold() for item in left.get("diagnoses", [])}
            right_set = {str(item).casefold() for item in right.get("diagnoses", [])}
            union = left_set | right_set
            consecutive_jaccards.append(
                len(left_set & right_set) / len(union) if union else 1.0
            )

        eligible_sequence = [
            event.event_id
            for event in sorted(
                (event for event in case.timeline_events if event.arena.arena_eligible),
                key=lambda event: (event.order_min(), event.available_min(), event.event_id),
            )
        ]
        eligible = set(eligible_sequence)
        ordered_sequence = [str(value) for value in session.get("ordered_event_ids", [])]
        ordered = set(ordered_sequence)
        revealed = set(session.get("revealed_event_ids", []))
        action_count = int(session.get("action_count", 0))
        recorded_action_count = len(ordered & eligible)
        revealed_count = len(revealed & eligible)
        unobserved_action_count = len(session.get("unobserved_action_ids", []))
        unresolved = sum(
            item.get("status") == "PENDING"
            for item in session.get("pending_actions", [])
        )
        event_log = session.get("event_log", [])
        wait_count = sum(
            item.get("event_type") == "WAIT_FOR_NEXT_RESULT" for item in event_log
        )
        simulation_advance_count = sum(
            item.get("event_type")
            in {"WAIT_FOR_NEXT_RESULT", "RESULT_REVEALED"}
            for item in event_log
        )
        order_streak = 0
        max_parallel_orders = 0
        for item in event_log:
            if item.get("event_type") == "ORDER_ACTION":
                order_streak += 1
                max_parallel_orders = max(max_parallel_orders, order_streak)
            elif item.get("event_type") in {
                "WAIT_FOR_NEXT_RESULT",
                "RESULT_REVEALED",
            }:
                order_streak = 0

        interactions = run.get("interactions", [])
        valid_interactions = [item for item in interactions if not item.get("error")]
        usage_rows = [
            item.get("response_payload", {}).get("usage", {})
            for item in interactions
            if isinstance(item.get("response_payload"), dict)
            and isinstance(item.get("response_payload", {}).get("usage"), dict)
        ]

        def usage_total(key: str) -> float:
            return round(
                sum(
                    float(row.get(key, 0) or 0)
                    for row in usage_rows
                    if isinstance(row.get(key, 0), (int, float))
                ),
                6,
            )

        reasoning_tokens = round(
            sum(
                float((row.get("completion_tokens_details") or {}).get("reasoning_tokens", 0) or 0)
                for row in usage_rows
                if isinstance(row.get("completion_tokens_details") or {}, dict)
            )
        )
        valid_latencies = [
            float(item.get("latency_ms", 0) or 0) for item in valid_interactions
        ]
        max_actions = int(run.get("max_actions", 30))
        evidence_denominator = max(1, len(eligible))
        transition_denominator = max(1, len(beliefs) - 1)
        exact = bool(comparison.get("is_exact_match"))
        low_coverage = revealed_count / evidence_denominator < 0.5
        return {
            "schema_version": "clincforestbench.temporal-model-evaluation.v1",
            "outcome": {
                "exact_top1": exact,
                "final_prediction": comparison.get("predicted_diagnosis"),
                "reference_diagnosis": reference,
                "reference_ever_considered": first_reference is not None,
                "last_differential_reference_rank": last_rank,
                "last_differential_reciprocal_rank": (
                    round(1 / last_rank, 4) if last_rank else 0.0
                ),
                "first_reference_checkpoint": (
                    first_reference["checkpoint"] if first_reference else None
                ),
                "first_reference_time_min": (
                    first_reference["game_time_min"] if first_reference else None
                ),
                "first_correct_top1_checkpoint": (
                    first_correct_top1["checkpoint"] if first_correct_top1 else None
                ),
                "first_correct_top1_time_min": (
                    first_correct_top1["game_time_min"] if first_correct_top1 else None
                ),
                "reference_rank_trajectory": reference_trace,
            },
            "evidence_acquisition": {
                "actions_used": action_count,
                "action_budget": max_actions,
                "action_budget_usage": round(action_count / max(1, max_actions), 4),
                "eligible_recorded_evidence_count": len(eligible),
                "recorded_action_count": recorded_action_count,
                "unobserved_action_count": unobserved_action_count,
                "recorded_action_precision": round(
                    recorded_action_count / max(1, action_count), 4
                ),
                "source_path_action_coverage": round(
                    recorded_action_count / evidence_denominator, 4
                ),
                "recorded_action_overlap_rate": round(
                    recorded_action_count
                    / max(1, len(eligible) + unobserved_action_count),
                    4,
                ),
                "source_order_alignment": round(
                    TemporalArenaService._lcs_length(
                        eligible_sequence, ordered_sequence
                    )
                    / max(1, len(ordered_sequence)),
                    4,
                ),
                "revealed_evidence_count": revealed_count,
                "source_evidence_reveal_coverage": round(
                    revealed_count / evidence_denominator, 4
                ),
                "unresolved_pending_count_at_final": unresolved,
                "wait_count": wait_count,
                "simulation_time_advance_count": simulation_advance_count,
                "max_orders_before_wait": max_parallel_orders,
                "elapsed_game_time_min": comparison.get("elapsed_game_time_min", 0),
            },
            "belief_dynamics": {
                "checkpoint_count": len(beliefs),
                "unique_top1_count": len({item.casefold() for item in top1}),
                "top1_revision_count": top1_revisions,
                "top1_revision_rate": round(
                    top1_revisions / transition_denominator, 4
                ),
                "differential_revision_count": differential_revisions,
                "differential_revision_rate": round(
                    differential_revisions / transition_denominator, 4
                ),
                "mean_consecutive_differential_jaccard": round(
                    sum(consecutive_jaccards) / max(1, len(consecutive_jaccards)), 4
                ),
            },
            "execution": {
                "interaction_count": len(interactions),
                "valid_interaction_count": len(valid_interactions),
                "invalid_interaction_count": len(interactions) - len(valid_interactions),
                "mean_model_latency_ms": round(
                    sum(valid_latencies) / max(1, len(valid_latencies))
                ),
                "prompt_tokens": round(usage_total("prompt_tokens")),
                "completion_tokens": round(usage_total("completion_tokens")),
                "reasoning_tokens": reasoning_tokens,
                "total_tokens": round(usage_total("total_tokens")),
                "reported_cost_usd": usage_total("cost"),
                "forced_final": bool(run.get("forced_final")),
            },
            "flags": {
                "ended_with_pending_results": unresolved > 0,
                "premature_finalization_proxy": bool(
                    not exact and (unresolved > 0 or low_coverage)
                ),
                "correct_early_stop": bool(exact and action_count < max_actions),
            },
            "interpretation_limits": [
                "The retrospective diagnosis may require clinician review and is not always absolute ground truth.",
                "Source-path coverage is descriptive, not a correctness score; the recorded order is not an optimal policy.",
                "Diagnostic latency needs clinician-annotated critical evidence before it can be scored fairly.",
            ],
        }

    def _path(self, run_id: str) -> Path:
        if not run_id.startswith("TMR-") or "/" in run_id:
            raise KeyError("Unknown Temporal model run")
        return self.root / f"{run_id}.json"

    def _load(self, run_id: str) -> dict[str, Any]:
        path = self._path(run_id)
        if not path.exists():
            raise KeyError("Unknown Temporal model run")
        return json.loads(path.read_text(encoding="utf-8"))

    def _save(self, run: dict[str, Any]) -> None:
        path = self._path(run["run_id"])
        temporary = path.with_suffix(".tmp")
        temporary.write_text(
            json.dumps(run, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        temporary.replace(path)
