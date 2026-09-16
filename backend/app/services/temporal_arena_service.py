from __future__ import annotations

import json
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

from backend.app.domain.temporal import TemporalCase
from backend.app.services.clinical_presentation import (
    action_presentation,
    event_presentation,
    initial_state_presentation,
    is_meaningful_event,
)
from backend.app.services.temporal_case_service import TemporalCaseService


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _reference_label(case: TemporalCase) -> str:
    value = (
        case.reference.get("adjudicated_primary_diagnosis")
        or case.reference.get("primary_diagnosis")
        or case.reference.get("hospital_principal_diagnosis")
        or case.reference.get("reference_diagnosis")
        or "Reference outcome"
    )
    if isinstance(value, list):
        return str(value[0]) if value else "Reference outcome"
    return str(value)


class TemporalArenaService:
    """Persistent local Temporal v2 Arena sessions.

    Patient-level artifacts remain inside the gitignored processed-data tree.
    The active-session payload never includes the case reference or future
    results. An order can only reveal a result that exists in the source case.
    """

    def __init__(self, cases: TemporalCaseService, root: Path) -> None:
        self.cases = cases
        self.root = root / "data/processed/temporal/v2/arena_sessions"
        self.root.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()

    def case_index(self) -> dict:
        manifest = self.cases.manifest()
        return {
            "case_count": manifest.get("case_count", 0),
            "dataset_case_counts": manifest.get("dataset_case_counts", {}),
            "cases": [
                {
                    "case_id": item["case_id"],
                    "dataset_name": item["dataset_name"],
                    "task_type": item["task_type"],
                    "event_count": item["event_count"],
                    "eligible_event_count": item["eligible_event_count"],
                    "max_time_min": item["max_time_min"],
                }
                for item in manifest.get("cases", [])
            ],
        }

    def create(self, case_id: str, username: str) -> dict:
        case = self.cases.get(case_id)
        session_id = f"TEMP-{uuid.uuid4()}"
        session = {
            "schema_version": "clincforestbench.temporal-arena-session.v2",
            "session_id": session_id,
            "case_id": case_id,
            "username": username,
            "dataset_name": case.source.get("dataset_family", "Temporal v2"),
            "task_type": case.task_type,
            "status": "ACTIVE",
            "created_at": _now(),
            "completed_at": None,
            "current_time_min": 0.0,
            "checkpoint": 0,
            "belief_required": True,
            "initial_state": case.initial_state,
            "revealed_event_ids": [],
            "pending_actions": [],
            "ordered_event_ids": [],
            "unobserved_action_ids": [],
            "action_count": 0,
            "max_actions": int(case.arena_config.get("max_questions", 30)),
            "belief_history": [],
            "event_log": [
                {
                    "event_type": "SESSION_STARTED",
                    "timestamp": _now(),
                    "game_time_min": 0.0,
                    "initial_state": case.initial_state,
                }
            ],
        }
        self._save(session)
        return self._public(session, case)

    def get(self, session_id: str, username: str) -> dict:
        session = self._load_owned(session_id, username)
        return self._public(session, self.cases.get(session["case_id"]))

    def submit_belief(
        self, session_id: str, username: str, diagnoses: List[str]
    ) -> dict:
        with self._lock:
            session = self._load_owned(session_id, username)
            self._require_active(session)
            normalized: List[str] = []
            seen = set()
            for value in diagnoses:
                label = str(value).strip()
                key = label.casefold()
                if label and key not in seen:
                    normalized.append(label)
                    seen.add(key)
            if not normalized:
                raise ValueError("At least one diagnosis is required")
            snapshot = {
                "checkpoint": session["checkpoint"],
                "game_time_min": session["current_time_min"],
                "diagnoses": normalized,
                "revealed_event_ids": list(session["revealed_event_ids"]),
                "pending_action_ids": [
                    item["action_id"]
                    for item in session["pending_actions"]
                    if item["status"] == "PENDING"
                ],
                "submitted_at": _now(),
                "is_final": False,
            }
            session["belief_history"].append(snapshot)
            session["belief_required"] = False
            session["event_log"].append(
                {"event_type": "BELIEF_SUBMITTED", **snapshot}
            )
            self._save(session)
            return self._public(session, self.cases.get(session["case_id"]))

    def order(self, session_id: str, username: str, action_id: str) -> dict:
        with self._lock:
            session = self._load_owned(session_id, username)
            self._require_active(session)
            if session["belief_required"]:
                raise ValueError("Submit the current diagnosis before ordering")
            if session["action_count"] >= session["max_actions"]:
                raise ValueError("The 30-action limit has been reached")
            case = self.cases.get(session["case_id"])
            source = next(
                (
                    event
                    for event in case.timeline_events
                    if event.action_id == action_id
                    and event.event_id not in session["ordered_event_ids"]
                    and event.arena.arena_eligible
                    and is_meaningful_event(event)
                ),
                None,
            )
            session["action_count"] += 1
            if source is None:
                if action_id in session["unobserved_action_ids"]:
                    raise ValueError("This unobserved action was already attempted")
                session["unobserved_action_ids"].append(action_id)
                outcome = {
                    "action_id": action_id,
                    "status": "UNOBSERVED",
                    "ordered_game_time": session["current_time_min"],
                    "expected_available_game_time": None,
                    "source_event_id": None,
                    "message": "UNOBSERVED_IN_RECORDED_EPISODE",
                    "clinical_message": (
                        "本次真实就诊记录中没有该项结果，不能据此推断为阴性。"
                    ),
                }
            else:
                latency = max(0.0, source.available_min() - source.order_min())
                before = float(session["current_time_min"])
                replay_mode = source.arena.temporal_replay_mode.value
                if replay_mode == "OBSERVED_FIXED_TIME":
                    available_at = max(before, source.available_min())
                else:
                    available_at = before + latency
                action = action_presentation(source)
                outcome = {
                    "action_id": action_id,
                    "display": action["display"],
                    "modality": source.clinical_concept.modality,
                    "modality_label": action["modality_label"],
                    "interaction_type": action["interaction_type"],
                    "interaction_label": action["interaction_label"],
                    "status": "AVAILABLE",
                    "ordered_game_time": before,
                    "expected_available_game_time": round(available_at, 2),
                    "source_event_id": source.event_id,
                    "temporal_replay_mode": replay_mode,
                    "temporal_confidence": source.time.temporal_confidence.value,
                    "message": "RESULT_AVAILABLE_AFTER_SIMULATED_TIME_ADVANCE",
                    "clinical_message": (
                        f"模拟时钟已推进至第 {round(available_at, 2):g} 分钟，结果立即显示；"
                        "不需要现实等待。"
                    ),
                }
                session["ordered_event_ids"].append(source.event_id)
                session["pending_actions"].append(outcome)
                session["revealed_event_ids"].append(source.event_id)
                session["current_time_min"] = round(available_at, 2)
                session["checkpoint"] += 1
                session["belief_required"] = True
            session["event_log"].append(
                {
                    "event_type": "ORDER_ACTION",
                    "timestamp": _now(),
                    "game_time_min": outcome["ordered_game_time"],
                    "outcome": outcome,
                }
            )
            newly_revealed: List[str] = []
            if source is not None:
                newly_revealed = [source.event_id]
                session["event_log"].append(
                    {
                        "event_type": "RESULT_REVEALED",
                        "timestamp": _now(),
                        "game_time_before_min": outcome["ordered_game_time"],
                        "game_time_after_min": session["current_time_min"],
                        "resolved_event_ids": newly_revealed,
                        "automatic_simulation_advance": True,
                    }
                )
            self._save(session)
            payload = self._public(session, case, newly_revealed)
            payload["last_action_outcome"] = outcome
            return payload

    def wait(self, session_id: str, username: str) -> dict:
        with self._lock:
            session = self._load_owned(session_id, username)
            self._require_active(session)
            if session["belief_required"]:
                raise ValueError("Submit the current diagnosis before advancing time")
            waiting = [
                item
                for item in session["pending_actions"]
                if item["status"] == "PENDING"
                and item["expected_available_game_time"] is not None
            ]
            if not waiting:
                raise ValueError("There is no pending recorded result to wait for")
            next_time = min(
                float(item["expected_available_game_time"]) for item in waiting
            )
            before = session["current_time_min"]
            resolved = []
            for item in session["pending_actions"]:
                if (
                    item["status"] == "PENDING"
                    and item["expected_available_game_time"] is not None
                    and float(item["expected_available_game_time"]) <= next_time
                ):
                    item["status"] = "AVAILABLE"
                    event_id = item["source_event_id"]
                    if event_id not in session["revealed_event_ids"]:
                        session["revealed_event_ids"].append(event_id)
                        resolved.append(event_id)
            session["current_time_min"] = next_time
            session["checkpoint"] += 1
            session["belief_required"] = True
            session["event_log"].append(
                {
                    "event_type": "WAIT_FOR_NEXT_RESULT",
                    "timestamp": _now(),
                    "game_time_before_min": before,
                    "game_time_after_min": next_time,
                    "resolved_event_ids": resolved,
                }
            )
            self._save(session)
            return self._public(
                session, self.cases.get(session["case_id"]), resolved
            )

    def finalize(
        self, session_id: str, username: str, diagnoses: List[str]
    ) -> dict:
        with self._lock:
            session = self._load_owned(session_id, username)
            self._require_active(session)
            if session["belief_required"]:
                raise ValueError("Submit the current diagnosis before finalizing")
            normalized = [str(value).strip() for value in diagnoses if str(value).strip()]
            if not normalized:
                raise ValueError("A final diagnosis is required")
            session["status"] = "COMPLETED"
            session["completed_at"] = _now()
            session["final_diagnoses"] = list(dict.fromkeys(normalized))
            session["event_log"].append(
                {
                    "event_type": "FINAL_DIAGNOSIS",
                    "timestamp": session["completed_at"],
                    "game_time_min": session["current_time_min"],
                    "diagnoses": session["final_diagnoses"],
                }
            )
            self._save(session)
            return self.review(session_id, username)

    def review(self, session_id: str, username: str) -> dict:
        session = self._load_owned(session_id, username)
        if session["status"] != "COMPLETED":
            raise ValueError("Ground truth is available only after finalization")
        case = self.cases.get(session["case_id"])
        final = session.get("final_diagnoses", [])
        truth = _reference_label(case)
        completed = []
        for path in self.root.glob("*.json"):
            try:
                item = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                continue
            if item.get("case_id") == case.case_id and item.get("status") == "COMPLETED":
                completed.append(item)
        top1: Dict[str, int] = {}
        for item in completed:
            diagnoses = item.get("final_diagnoses", [])
            if diagnoses:
                top1[diagnoses[0]] = top1.get(diagnoses[0], 0) + 1
        return {
            "session": session,
            "comparison": {
                "predicted_diagnosis": final[0] if final else "",
                "ground_truth_diagnosis": truth,
                "is_exact_match": bool(final and final[0].casefold() == truth.casefold()),
                "actions_used": session["action_count"],
                "elapsed_game_time_min": session["current_time_min"],
            },
            "ground_truth_tree": case.temporal_graph.model_dump(mode="json"),
            "mvp_strategy_paths": case.mvp_simulations,
            "community": {
                "completed_session_count": len(completed),
                "top1_diagnoses": [
                    {
                        "diagnosis": diagnosis,
                        "count": count,
                        "rate": round(count / max(1, len(completed)), 4),
                    }
                    for diagnosis, count in sorted(
                        top1.items(), key=lambda item: (-item[1], item[0].casefold())
                    )
                ],
                "mean_actions": round(
                    sum(item.get("action_count", 0) for item in completed)
                    / max(1, len(completed)),
                    2,
                ),
            },
        }

    def history(self, username: str) -> dict:
        sessions = []
        for path in sorted(self.root.glob("*.json")):
            try:
                item = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                continue
            if item.get("username") == username:
                sessions.append(
                    {
                        "session_id": item["session_id"],
                        "case_id": item["case_id"],
                        "dataset_name": item["dataset_name"],
                        "status": item["status"],
                        "created_at": item["created_at"],
                        "completed_at": item.get("completed_at"),
                        "actions_used": item["action_count"],
                    }
                )
        return {"sessions": sorted(sessions, key=lambda x: x["created_at"], reverse=True)}

    def forest_index(self) -> dict:
        sessions = self._all_sessions()
        rows = []
        for entry in self.cases.manifest().get("cases", []):
            completed = [
                item
                for item in sessions
                if item.get("case_id") == entry["case_id"]
                and item.get("status") == "COMPLETED"
            ]
            rows.append(
                {
                    "case_id": entry["case_id"],
                    "dataset_name": entry["dataset_name"],
                    "task_type": entry["task_type"],
                    "event_count": entry["event_count"],
                    "eligible_event_count": entry["eligible_event_count"],
                    "completed_session_count": len(completed),
                    "participant_count": len(
                        {item.get("username") for item in completed}
                    ),
                }
            )
        return {
            "case_count": len(rows),
            "dataset_case_counts": self.cases.manifest().get(
                "dataset_case_counts", {}
            ),
            "cases": rows,
        }

    def forest_detail(self, case_id: str) -> dict:
        case = self.cases.get(case_id)
        completed = [
            item
            for item in self._all_sessions()
            if item.get("case_id") == case_id
            and item.get("status") == "COMPLETED"
        ]
        stages: Dict[int, List[List[str]]] = {}
        action_counts: Dict[str, int] = {}
        final_lists = []
        for session in completed:
            final = session.get("final_diagnoses", [])
            if final:
                final_lists.append(final)
            for snapshot in session.get("belief_history", []):
                stages.setdefault(int(snapshot.get("checkpoint", 0)), []).append(
                    snapshot.get("diagnoses", [])
                )
            for event in session.get("event_log", []):
                if event.get("event_type") != "ORDER_ACTION":
                    continue
                action_id = event.get("outcome", {}).get("action_id")
                if action_id:
                    action_counts[action_id] = action_counts.get(action_id, 0) + 1
        total = max(1, len(completed))
        return {
            "case_id": case_id,
            "dataset_name": case.source.get("dataset_family"),
            "task_type": case.task_type,
            "summary": {
                "completed_session_count": len(completed),
                "participant_count": len(
                    {item.get("username") for item in completed}
                ),
                "mean_actions": round(
                    sum(item.get("action_count", 0) for item in completed) / total,
                    2,
                ),
                "mean_elapsed_time_min": round(
                    sum(item.get("current_time_min", 0) for item in completed)
                    / total,
                    2,
                ),
            },
            "reference": {
                "diagnosis": _reference_label(case),
                "strength": case.reference.get("reference_strength"),
                "is_absolute_ground_truth": case.reference.get(
                    "is_absolute_ground_truth", False
                ),
            },
            "stages": [
                {
                    "checkpoint": checkpoint,
                    "submission_count": len(lists),
                    "diagnoses": self._rank_distribution(lists),
                }
                for checkpoint, lists in sorted(stages.items())
            ],
            "final_diagnoses": self._rank_distribution(final_lists),
            "actions": [
                {
                    "action_id": action_id,
                    "selection_count": count,
                    "selection_rate": round(count / total, 4),
                }
                for action_id, count in sorted(
                    action_counts.items(), key=lambda item: (-item[1], item[0])
                )
            ],
            "ground_truth_tree": case.temporal_graph.model_dump(mode="json"),
            "temporal_quality": case.temporal_quality,
            "trajectory_evaluation": self._trajectory_evaluation(case, completed),
        }

    def _trajectory_evaluation(
        self, case: TemporalCase, completed: List[dict]
    ) -> dict:
        """Attach the same trajectory metric contract to every Temporal case.

        These metrics separate diagnostic outcome from descriptive overlap with
        the recorded source path. The latter must not be interpreted as an
        optimal-policy score.
        """
        reference = _reference_label(case)
        reference_key = reference.casefold()
        eligible_sequence = [
            event.event_id
            for event in sorted(
                (event for event in case.timeline_events if event.arena.arena_eligible),
                key=lambda event: (event.order_min(), event.available_min(), event.event_id),
            )
        ]
        eligible = set(eligible_sequence)
        rows = []
        for session in completed:
            beliefs = session.get("belief_history", [])
            ranks = []
            top1 = []
            for belief in beliefs:
                diagnoses = [str(value) for value in belief.get("diagnoses", [])]
                keys = [value.casefold() for value in diagnoses]
                ranks.append(keys.index(reference_key) + 1 if reference_key in keys else None)
                if diagnoses:
                    top1.append(diagnoses[0])
            final = [str(value) for value in session.get("final_diagnoses", [])]
            exact = bool(final and final[0].casefold() == reference_key)
            ordered_sequence = [
                str(value) for value in session.get("ordered_event_ids", [])
            ]
            ordered = set(ordered_sequence)
            revealed = {
                str(value) for value in session.get("revealed_event_ids", [])
            }
            unobserved = len(session.get("unobserved_action_ids", []))
            recorded_actions = len(ordered & eligible)
            revealed_evidence = len(revealed & eligible)
            pending = sum(
                item.get("status") == "PENDING"
                for item in session.get("pending_actions", [])
            )
            action_count = int(session.get("action_count", 0))
            run = self._model_run_for_session(session)
            action_budget = int(
                (run or {}).get("max_actions", session.get("max_actions", 30))
            )
            coverage = revealed_evidence / max(1, len(eligible))
            overlap = recorded_actions / max(1, len(eligible) + unobserved)
            sequence_alignment = self._lcs_length(
                eligible_sequence, ordered_sequence
            ) / max(1, len(ordered_sequence))
            top1_revisions = sum(
                left.casefold() != right.casefold()
                for left, right in zip(top1, top1[1:])
            )
            username = str(session.get("username") or "unknown")
            run_id = str((run or {}).get("run_id") or "") or None
            participant_type = "MODEL" if run_id else "DOCTOR"
            rows.append(
                {
                    "session_id": session.get("session_id"),
                    "run_id": run_id,
                    "participant_type": participant_type,
                    "participant_label": (
                        str((run or {}).get("model_id") or "model")
                        if participant_type == "MODEL"
                        else username
                    ),
                    "final_prediction": final[0] if final else "",
                    "exact_top1": exact,
                    "reference_ever_considered": any(rank is not None for rank in ranks),
                    "last_reference_rank": ranks[-1] if ranks else None,
                    "last_reference_reciprocal_rank": (
                        round(1 / ranks[-1], 4) if ranks and ranks[-1] else 0.0
                    ),
                    "actions_used": action_count,
                    "action_budget": action_budget,
                    "action_budget_usage": round(
                        action_count / max(1, action_budget), 4
                    ),
                    "recorded_action_overlap_count": recorded_actions,
                    "recorded_action_overlap_rate": round(overlap, 4),
                    "source_order_alignment": round(sequence_alignment, 4),
                    "revealed_evidence_count": revealed_evidence,
                    "source_evidence_reveal_coverage": round(coverage, 4),
                    "unobserved_action_count": unobserved,
                    "pending_at_final": pending,
                    "elapsed_game_time_min": round(
                        float(session.get("current_time_min", 0) or 0), 2
                    ),
                    "checkpoint_count": len(beliefs),
                    "top1_revision_count": top1_revisions,
                    "premature_finalization_proxy": bool(
                        not exact and (pending > 0 or coverage < 0.5)
                    ),
                }
            )

        def mean(key: str) -> float | None:
            if not rows:
                return None
            return round(
                sum(float(row.get(key, 0) or 0) for row in rows) / len(rows), 4
            )

        def rate(key: str) -> float | None:
            if not rows:
                return None
            return round(sum(bool(row.get(key)) for row in rows) / len(rows), 4)

        return {
            "schema_version": "clincforestbench.case-trajectory-evaluation.v1",
            "status": "READY" if rows else "NO_COMPLETED_TRAJECTORIES",
            "completed_trajectory_count": len(rows),
            "aggregate": {
                "exact_top1_accuracy": rate("exact_top1"),
                "reference_considered_rate": rate("reference_ever_considered"),
                "mean_last_reference_reciprocal_rank": mean(
                    "last_reference_reciprocal_rank"
                ),
                "mean_recorded_action_overlap_rate": mean(
                    "recorded_action_overlap_rate"
                ),
                "mean_source_order_alignment": mean("source_order_alignment"),
                "mean_source_evidence_reveal_coverage": mean(
                    "source_evidence_reveal_coverage"
                ),
                "mean_action_budget_usage": mean("action_budget_usage"),
                "mean_top1_revision_count": mean("top1_revision_count"),
                "pending_at_final_rate": rate("pending_at_final"),
                "premature_finalization_proxy_rate": rate(
                    "premature_finalization_proxy"
                ),
                "mean_elapsed_game_time_min": mean("elapsed_game_time_min"),
            },
            "trajectories": rows,
            "metric_definitions": [
                {
                    "key": "exact_top1_accuracy",
                    "label": "Top-1 准确率",
                    "direction": "HIGHER",
                    "description": "最终第一诊断与回顾参考诊断完全一致的轨迹比例。",
                },
                {
                    "key": "reference_considered_rate",
                    "label": "参考诊断进入鉴别率",
                    "direction": "HIGHER",
                    "description": "任一阶段曾把参考诊断放入候选列表的轨迹比例。",
                },
                {
                    "key": "mean_last_reference_reciprocal_rank",
                    "label": "最终参考诊断 MRR",
                    "direction": "HIGHER",
                    "description": "最后一次鉴别列表中参考诊断排名倒数的平均值。",
                },
                {
                    "key": "mean_recorded_action_overlap_rate",
                    "label": "GT 动作节点重合",
                    "direction": "DESCRIPTIVE",
                    "description": "模型/医生动作与病例记录动作节点的集合重合；只描述覆盖，不代表最优。",
                },
                {
                    "key": "mean_source_order_alignment",
                    "label": "源路径顺序一致度",
                    "direction": "DESCRIPTIVE",
                    "description": "实际动作顺序与源病例记录顺序的最长公共子序列比例；源顺序不是标准答案。",
                },
                {
                    "key": "mean_source_evidence_reveal_coverage",
                    "label": "证据揭示覆盖",
                    "direction": "DESCRIPTIVE",
                    "description": "结束前真正返回给参与者的已记录结果占可选结果的比例。",
                },
                {
                    "key": "mean_action_budget_usage",
                    "label": "动作预算使用",
                    "direction": "LOWER_IF_CORRECT",
                    "description": "已用动作数除以该轨迹动作上限；只能结合诊断正确性解释。",
                },
                {
                    "key": "mean_top1_revision_count",
                    "label": "Top-1 修订次数",
                    "direction": "DESCRIPTIVE",
                    "description": "相邻 observation state 之间第一诊断发生变化的次数。",
                },
                {
                    "key": "premature_finalization_proxy_rate",
                    "label": "疑似错误早停率",
                    "direction": "LOWER",
                    "description": "最终错误，且仍有 pending 或已记录证据揭示不足一半的轨迹比例。",
                },
            ],
            "interpretation_limits": [
                "回顾诊断不一定是绝对真值，必要时仍需临床专家复核。",
                "GT 时间树是已记录事实树，不是唯一正确或最优的检查策略。",
                "节点重合与顺序一致度是描述性指标，不能单独用于奖励多做检查。",
                "真正的诊断延迟评分需要先标注每个病例的关键充分证据节点。",
            ],
        }

    def _model_run_for_session(self, session: dict) -> dict | None:
        username = str(session.get("username") or "")
        if not username.startswith("model:TMR-"):
            return None
        run_id = username.removeprefix("model:")
        path = self.root.parent / "model_runs" / f"{run_id}.json"
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return None

    @staticmethod
    def _lcs_length(left: List[str], right: List[str]) -> int:
        if not left or not right:
            return 0
        previous = [0] * (len(right) + 1)
        for left_value in left:
            current = [0]
            for index, right_value in enumerate(right, 1):
                if left_value == right_value:
                    current.append(previous[index - 1] + 1)
                else:
                    current.append(max(previous[index], current[-1]))
            previous = current
        return previous[-1]

    def _all_sessions(self) -> List[dict]:
        result = []
        for path in self.root.glob("*.json"):
            try:
                result.append(json.loads(path.read_text(encoding="utf-8")))
            except (OSError, json.JSONDecodeError):
                continue
        return result

    @staticmethod
    def _rank_distribution(lists: List[List[str]]) -> List[dict]:
        total = max(1, len(lists))
        records: Dict[str, dict] = {}
        for diagnoses in lists:
            for rank, diagnosis in enumerate(diagnoses, 1):
                row = records.setdefault(
                    diagnosis,
                    {"diagnosis": diagnosis, "selection_count": 0, "top1_count": 0, "rank_sum": 0},
                )
                row["selection_count"] += 1
                row["top1_count"] += rank == 1
                row["rank_sum"] += rank
        return [
            {
                "diagnosis": row["diagnosis"],
                "selection_count": row["selection_count"],
                "selection_rate": round(row["selection_count"] / total, 4),
                "top1_rate": round(row["top1_count"] / total, 4),
                "mean_rank": round(row["rank_sum"] / row["selection_count"], 2),
            }
            for row in sorted(
                records.values(),
                key=lambda item: (-item["top1_count"], -item["selection_count"], item["diagnosis"].casefold()),
            )
        ]

    def _public(
        self,
        session: dict,
        case: TemporalCase,
        newly_revealed: List[str] | None = None,
    ) -> dict:
        event_map = {event.event_id: event for event in case.timeline_events}
        reveal_times = {
            item.get("source_event_id"): item.get("expected_available_game_time")
            for item in session["pending_actions"]
            if item.get("source_event_id")
        }
        revealed = [
            event_map[event_id].model_dump(mode="json")
            | {
                "presentation": event_presentation(event_map[event_id]),
                "arena_reveal_time_min": reveal_times.get(event_id),
            }
            for event_id in session["revealed_event_ids"]
            if event_id in event_map
        ]
        return {
            "session_id": session["session_id"],
            "case_id": session["case_id"],
            "dataset_name": session["dataset_name"],
            "task_type": session["task_type"],
            "status": session["status"],
            "initial_state": session["initial_state"],
            "initial_presentation": initial_state_presentation(
                session["initial_state"], session["dataset_name"]
            ),
            "current_time_min": session["current_time_min"],
            "checkpoint": session["checkpoint"],
            "belief_required": session["belief_required"],
            "belief_history": session["belief_history"],
            "pending_actions": session["pending_actions"],
            "revealed_events": revealed,
            "newly_revealed_event_ids": newly_revealed or [],
            "action_count": session["action_count"],
            "max_actions": session["max_actions"],
            "available_actions": self._action_catalog(case, session),
            "diagnosis_catalog": self._diagnosis_catalog(),
        }

    def _action_catalog(self, case: TemporalCase, session: dict) -> List[dict]:
        dataset = case.source.get("dataset_family")
        definitions: Dict[str, dict] = {}
        case_scoped = case.arena_config.get("action_catalog_scope") == "CASE"
        entries = (
            [{"case_id": case.case_id}]
            if case_scoped
            else self.cases.manifest().get("cases", [])
        )
        for entry in entries:
            other = self.cases.get(entry["case_id"])
            if not case_scoped and other.source.get("dataset_family") != dataset:
                continue
            for event in other.timeline_events:
                if (
                    not event.arena.arena_eligible
                    or not event.action_id
                    or not is_meaningful_event(event)
                ):
                    continue
                presentation = action_presentation(event)
                definitions.setdefault(
                    event.action_id,
                    {
                        "action_id": event.action_id,
                        **presentation,
                    },
                )
        # An action disappears as soon as it has been attempted.  Keeping a
        # recorded action in the catalog after it was ordered allowed a second
        # click to be misclassified as an unobserved test.
        exhausted = set(session["unobserved_action_ids"])
        exhausted.update(
            item.get("action_id")
            for item in session["pending_actions"]
            if item.get("action_id")
        )
        available = [
            item
            for key, item in sorted(definitions.items())
            if key not in exhausted
        ]
        if case.arena_config.get("sequential_actions") and available:
            remaining_ids = {item["action_id"] for item in available}
            next_event = min(
                (
                    event
                    for event in case.timeline_events
                    if event.action_id in remaining_ids
                ),
                key=lambda event: (
                    event.order_min(),
                    event.available_min(),
                    event.event_id,
                ),
            )
            return [
                item for item in available if item["action_id"] == next_event.action_id
            ]
        return available

    def _diagnosis_catalog(self) -> List[str]:
        labels = []
        for item in self.cases.manifest().get("cases", []):
            value = item.get("reference_label")
            if isinstance(value, list):
                labels.extend(str(part) for part in value if part)
            elif value:
                labels.append(str(value))
        return sorted(set(labels), key=str.casefold)

    def _path(self, session_id: str) -> Path:
        if not session_id.startswith("TEMP-") or "/" in session_id:
            raise KeyError("Unknown Temporal session")
        return self.root / f"{session_id}.json"

    def _load_owned(self, session_id: str, username: str) -> dict:
        path = self._path(session_id)
        if not path.exists():
            raise KeyError("Unknown Temporal session")
        session = json.loads(path.read_text(encoding="utf-8"))
        if session.get("username") != username:
            raise PermissionError("Session belongs to another account")
        return session

    def _save(self, session: dict) -> None:
        path = self._path(session["session_id"])
        temporary = path.with_suffix(".tmp")
        temporary.write_text(
            json.dumps(session, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        temporary.replace(path)

    @staticmethod
    def _require_active(session: dict) -> None:
        if session["status"] != "ACTIVE":
            raise ValueError("Temporal session is already completed")
