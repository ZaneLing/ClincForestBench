from __future__ import annotations

import json
import time
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from pydantic import ValidationError

from backend.app.config import Settings
from backend.app.domain.belief import BeliefSubmission, DiagnosisBelief
from backend.app.domain.enums import PlayerType, SessionStatus
from backend.app.domain.evidence import human_readable_response
from backend.app.domain.model_run import (
    ModelDecision,
    ModelInteractionRecord,
    ModelRunRecord,
)
from backend.app.domain.session import Player, utc_now
from backend.app.repositories.base import ArenaRepository
from backend.app.services.arena_service import ArenaService
from backend.app.services.case_service import CaseService
from backend.app.services.case_tree_service import CaseTreeService
from backend.app.services.forest_analytics_service import ForestAnalyticsService
from backend.app.services.review_service import ReviewService


PROVIDER_LABELS = {
    "openai": "OpenAI",
    "anthropic": "Anthropic",
    "google": "Google",
    "deepseek": "DeepSeek",
    "z-ai": "Z.ai",
    "qwen": "Qwen",
    "meta-llama": "Meta",
    "mistralai": "Mistral AI",
    "x-ai": "xAI",
    "cohere": "Cohere",
    "microsoft": "Microsoft",
    "nvidia": "NVIDIA",
}


class ModelArenaService:
    """Drive the canonical Arena one validated OpenRouter turn at a time."""

    def __init__(
        self,
        settings: Settings,
        cases: CaseService,
        arena: ArenaService,
        repository: ArenaRepository,
        reviews: ReviewService,
        forest: ForestAnalyticsService,
        case_trees: CaseTreeService,
    ) -> None:
        self.settings = settings
        self.cases = cases
        self.arena = arena
        self.repository = repository
        self.reviews = reviews
        self.forest = forest
        self.case_trees = case_trees

    def status(self) -> dict[str, Any]:
        return {
            "provider": "OpenRouter",
            "configured": bool(self.settings.openrouter_api_key),
            "base_url": self.settings.openrouter_base_url,
            "max_questions": 30,
        }

    def models(self) -> dict[str, Any]:
        payload = self._request("GET", "/models")
        rows = []
        for item in payload.get("data", []):
            model_id = item.get("id")
            if not isinstance(model_id, str) or "/" not in model_id:
                continue
            provider = model_id.split("/", 1)[0]
            rows.append(
                {
                    "id": model_id,
                    "name": item.get("name") or model_id,
                    "provider": provider,
                    "provider_label": PROVIDER_LABELS.get(
                        provider, provider.replace("-", " ").title()
                    ),
                    "context_length": item.get("context_length"),
                    "pricing": item.get("pricing") or {},
                    "architecture": item.get("architecture") or {},
                }
            )
        rows.sort(key=lambda item: (item["provider_label"], item["name"]))
        providers = []
        for provider in sorted(
            {item["provider"] for item in rows},
            key=lambda value: PROVIDER_LABELS.get(value, value).lower(),
        ):
            providers.append(
                {
                    "id": provider,
                    "name": PROVIDER_LABELS.get(
                        provider, provider.replace("-", " ").title()
                    ),
                    "model_count": sum(
                        item["provider"] == provider for item in rows
                    ),
                }
            )
        return {"provider": "OpenRouter", "providers": providers, "models": rows}

    def create_run(
        self, model_id: str, case_id: str, max_questions: int = 30
    ) -> dict[str, Any]:
        if not self.settings.openrouter_api_key:
            raise ValueError("OPENROUTER_API_KEY is not configured on the API server")
        if not model_id or "/" not in model_id:
            raise ValueError("A valid OpenRouter model id is required")
        if not 1 <= max_questions <= 30:
            raise ValueError("max_questions must be between 1 and 30")
        bundle = self.cases.get(case_id)
        provider = model_id.split("/", 1)[0]
        session = self.arena.create_session(
            case_id=case_id,
            player=Player(
                player_id=f"model:{model_id}",
                player_type=PlayerType.MODEL,
                training_level="OpenRouter autonomous Arena",
                model_metadata={
                    "gateway": "OpenRouter",
                    "provider": provider,
                    "model_id": model_id,
                },
            ),
        )
        run = ModelRunRecord(
            session_id=session.session_id,
            model_id=model_id,
            provider=provider,
            case_id=case_id,
            dataset_name=bundle.dataset.name,
            max_questions=max_questions,
        )
        self.repository.add_model_run(run)
        return self.detail(run.run_id)

    def list_runs(self, case_id: str | None = None) -> dict[str, Any]:
        runs = self.repository.all_model_runs()
        if case_id:
            runs = [item for item in runs if item.case_id == case_id]
        return {
            "runs": [
                {
                    **run.model_dump(mode="json"),
                    "interaction_count": len(
                        self.repository.model_interactions(run.run_id)
                    ),
                    "question_count": self.arena.state(
                        run.session_id
                    ).question_count,
                }
                for run in runs
            ]
        }

    def step(self, run_id: str) -> dict[str, Any]:
        run = self.repository.get_model_run(run_id)
        session = self.arena.get_session(run.session_id)
        if run.status != "ACTIVE" or session.status != SessionStatus.ACTIVE:
            raise ValueError("Model run is not active")

        state = self.arena.state(run.session_id)
        request_payload = self._build_request(run, state.public_payload())
        started = time.monotonic()
        response_payload: dict[str, Any] | None = None
        assistant_content: str | None = None
        parsed_payload: dict[str, Any] | None = None
        application_result: dict[str, Any] | None = None
        error: str | None = None
        forced_final = False

        try:
            response_payload = self._request(
                "POST", "/chat/completions", request_payload
            )
            assistant_content = self._assistant_content(response_payload)
            parsed_payload = self._parse_json_object(assistant_content)
            decision = ModelDecision.model_validate(
                self._normalize_decision_payload(parsed_payload)
            )
            # Persist the validated, normalized contract for the UI. The raw
            # provider response remains intact in response_payload and
            # assistant_content for audit/debugging.
            parsed_payload = decision.model_dump(mode="json")
            application_result, forced_final = self._apply_decision(run, decision)
        except (ValueError, ValidationError, HTTPError, URLError) as exc:
            error = self._safe_error(exc)
        except Exception as exc:  # provider payloads can fail in unexpected ways
            error = f"{type(exc).__name__}: {exc}"

        interaction = ModelInteractionRecord(
            run_id=run_id,
            step=len(self.repository.model_interactions(run_id)) + 1,
            request_payload=request_payload,
            response_payload=response_payload,
            assistant_content=assistant_content,
            parsed_decision=parsed_payload,
            application_result=application_result,
            error=error,
            latency_ms=round((time.monotonic() - started) * 1000),
        )
        self.repository.append_model_interaction(interaction)

        updated_session = self.arena.get_session(run.session_id)
        completed = updated_session.status == SessionStatus.COMPLETED
        updated = run.model_copy(
            update={
                "status": "COMPLETED" if completed else "ACTIVE",
                "forced_final": run.forced_final or forced_final,
                "last_error": error,
                "completed_at": utc_now() if completed else None,
            }
        )
        self.repository.update_model_run(updated)
        return self.detail(run_id)

    def detail(self, run_id: str) -> dict[str, Any]:
        run = self.repository.get_model_run(run_id)
        session = self.arena.get_session(run.session_id)
        state = self.arena.state(run.session_id)
        interactions = self.repository.model_interactions(run_id)
        result: dict[str, Any] = {
            "run": run.model_dump(mode="json"),
            "session": session.model_dump(mode="json"),
            "state": state.public_payload(),
            "conditions": self.cases.safe_condition_catalog(run.case_id),
            "trajectory": self._active_trajectory(run.session_id),
            "belief_history": [
                item.model_dump(mode="json")
                for item in self.repository.beliefs(run.session_id)
            ],
            "interactions": [
                item.model_dump(mode="json") for item in interactions
            ],
        }
        if session.status == SessionStatus.COMPLETED:
            result["review"] = self._model_review(run.session_id)
            result["artifact"] = {
                "schema_version": "clincforestbench.model-arena-run.v1",
                "model_run": run.model_dump(mode="json"),
                "arena": self.reviews.completed_session_artifact(run.session_id),
                "interactions": [
                    item.model_dump(mode="json") for item in interactions
                ],
            }
        return result

    def _build_request(
        self, run: ModelRunRecord, public_state: dict[str, Any]
    ) -> dict[str, Any]:
        state = self.arena.state(run.session_id)
        candidates = self.arena.candidate_actions(run.session_id).actions
        available_ids = {
            item.evidence_id
            for item in candidates
            if item.evidence_id and item.dependency_met
        }
        revealed_ids = set(state.revealed)
        bundle = self.cases.get(run.case_id)
        decision_history = self._decision_history(run.run_id)
        latest_diagnoses = (
            decision_history[-1]["diagnoses"] if decision_history else []
        )
        relevance_hints = self.cases.question_scope(
            latest_diagnoses,
            state.initial_evidence_id,
            run.case_id,
        )
        full_actions = []
        for evidence_id, definition in self.cases.catalog_for_case(
            run.case_id
        ).items():
            if evidence_id == bundle.initial_evidence.evidence_id:
                status = "INITIAL_CONTEXT"
            elif evidence_id in revealed_ids:
                status = "ALREADY_USED"
            elif evidence_id in available_ids:
                status = "AVAILABLE"
            else:
                status = "LOCKED_BY_DEPENDENCY"
            full_actions.append(
                {
                    "action_id": evidence_id,
                    "label": definition.question_en,
                    "clinical_domain": definition.clinical_domain,
                    "action_kind": definition.action_kind,
                    "parent_action_id": definition.parent_evidence_id,
                    "suggested_by": relevance_hints.get(evidence_id, []),
                    "status": status,
                }
            )
        full_actions.sort(key=lambda item: item["action_id"])
        top1_history = [
            item["diagnoses"][0]
            for item in decision_history
            if item["diagnoses"]
        ]
        rejected_attempts = [
            {
                "attempted_decision": item.parsed_decision,
                "rejection": item.error,
            }
            for item in self.repository.model_interactions(run.run_id)[-3:]
            if item.error
        ]
        turn_payload = {
            "arena": {
                "dataset": run.dataset_name,
                "case_id": run.case_id,
                "case_type": bundle.case_type,
                "question_count": state.question_count,
                "max_questions": run.max_questions,
                "early_stop_policy": "MODEL_DECIDES",
                "automatic_early_stop": False,
                "must_finalize_now": state.question_count >= run.max_questions,
            },
            "patient_state": public_state,
            "diagnostic_progress": {
                "previous_decisions": decision_history[-8:],
                "top1_history": top1_history,
                "rejected_attempts_to_correct": rejected_attempts,
            },
            "stopping_policy": {
                "policy": "MODEL_DECIDES",
                "automatic_threshold": None,
                "finalize_when": "Set final=true only when you judge the current evidence sufficient for one final answer.",
                "continue_when": "You may keep acquiring non-repeated AVAILABLE evidence while it can improve the diagnosis.",
                "stable_top1_rule": "Top-1 stability alone is not a reason to finalize.",
                "hard_cap": run.max_questions,
            },
            "disease_or_outcome_library": self.cases.safe_condition_catalog(
                run.case_id
            ),
            "question_or_action_library": full_actions,
            "output_contract": {
                "top_level_object_only": True,
                "do_not_wrap_in": ["required_response", "response", "decision"],
                "diagnoses": ["condition_id in priority order; no duplicates"],
                "next_action_id": "one AVAILABLE action id, or null when final",
                "final": "boolean",
                "final_condition_id": "one condition_id when final, otherwise null",
                "rationale": "brief explanation",
            },
        }
        system = (
            "You are playing ClincForestBench under exactly the same rules as a "
            "human clinician. There is no heuristic or automatic early-stop "
            "threshold: you decide when the evidence is sufficient, and the action "
            "limit is only a hard safety ceiling. Return one JSON object and no "
            "markdown, with diagnoses, "
            "next_action_id, final, final_condition_id, and rationale directly at "
            "the top level. Never wrap them in required_response, response, or "
            "decision. Rank one or more unique ids from disease_or_outcome_library. "
            "Actively add, remove, and reorder candidates after each observation; "
            "an unchanged list is appropriate only when the new answer is genuinely "
            "non-discriminating. Choose no repeated "
            "disease id. If final is false, choose exactly one action whose status "
            "is AVAILABLE; never choose INITIAL_CONTEXT, ALREADY_USED, or "
            "LOCKED_BY_DEPENDENCY. Select the action with the highest expected value "
            "for separating the leading candidates, not a merely possible or broad "
            "history question. When final=false, rationale must name the competing "
            "outcomes the action separates and explain how its answer could change "
            "their order. Set final=true when you judge one unique answer is sufficiently "
            "supported; then provide "
            "exactly one final_condition_id and next_action_id=null. Follow the "
            "stopping_policy and diagnostic_progress signals. If a rejected attempt "
            "is supplied, correct it rather than repeating it. Do not invent ids. Do "
            "not use probabilities. When must_finalize_now is true you must finalize."
        )
        return {
            "model": run.model_id,
            "messages": [
                {"role": "system", "content": system},
                {
                    "role": "user",
                    "content": json.dumps(
                        turn_payload, ensure_ascii=False, separators=(",", ":")
                    ),
                },
            ],
            "temperature": 0,
            "max_tokens": 1200,
        }

    def _apply_decision(
        self, run: ModelRunRecord, decision: ModelDecision
    ) -> tuple[dict[str, Any], bool]:
        if len(decision.diagnoses) != len(set(decision.diagnoses)):
            raise ValueError("Model returned duplicate disease/outcome ids")
        condition_ids = {
            item["condition_id"]
            for item in self.cases.safe_condition_catalog(run.case_id)
        }
        unknown = sorted(set(decision.diagnoses) - condition_ids)
        if unknown:
            raise ValueError(f"Model returned unknown outcome ids: {', '.join(unknown)}")

        state = self.arena.state(run.session_id)
        forced_final = state.question_count >= run.max_questions
        should_finalize = decision.final or forced_final
        if should_finalize:
            final_id = decision.final_condition_id or decision.diagnoses[0]
            if final_id not in condition_ids:
                raise ValueError("final_condition_id is not in the outcome library")
            if decision.final_condition_id and final_id not in decision.diagnoses:
                raise ValueError("final_condition_id must also appear in diagnoses")
        else:
            if not decision.next_action_id:
                raise ValueError("next_action_id is required when final is false")
            allowed = {
                item.evidence_id
                for item in self.arena.candidate_actions(run.session_id).actions
                if item.evidence_id and item.dependency_met
            }
            if decision.next_action_id not in allowed:
                raise ValueError(
                    "next_action_id is repeated, locked, unknown, or unavailable"
                )

        staged_belief = self._belief(decision.diagnoses)
        snapshot = self.arena.submit_belief(
            run.session_id,
            staged_belief,
            f"model:{run.run_id}:belief:{state.question_count}",
        )
        result: dict[str, Any] = {
            "state_step": state.question_count,
            "belief": snapshot.model_dump(mode="json"),
            "forced_final": forced_final,
        }
        if should_finalize:
            final_id = decision.final_condition_id or decision.diagnoses[0]
            self.arena.finalize(
                run.session_id,
                self._belief([final_id]),
                f"model:{run.run_id}:final:{state.question_count}",
            )
            result.update(
                {
                    "result_type": "FINAL",
                    "final_condition_id": final_id,
                }
            )
            return result, forced_final

        action_id = decision.next_action_id
        step_result = self.arena.ask_evidence(
            run.session_id,
            action_id,
            f"model:{run.run_id}:action:{state.question_count}",
        )
        definition = self.cases.catalog_for_case(run.case_id)[action_id]
        result.update(
            {
                "result_type": step_result.result_type.value,
                "action_id": action_id,
                "question": definition.question_en,
                "answer": (
                    human_readable_response(step_result.observation, definition)
                    if step_result.observation
                    else None
                ),
                "observation": (
                    step_result.observation.model_dump(mode="json")
                    if step_result.observation
                    else None
                ),
                "state_before_hash": step_result.state_before_hash,
                "state_after_hash": step_result.state_after_hash,
            }
        )
        return result, False

    def _active_trajectory(self, session_id: str) -> list[dict[str, Any]]:
        session = self.arena.get_session(session_id)
        bundle = self.cases.get(session.case_id)
        catalog = self.cases.catalog_for_case(session.case_id)
        states = self.repository.states(session_id)
        trajectory = [
            {
                "step": 0,
                "state_hash": states[0].state.state_hash,
                "evidence_id": bundle.initial_evidence.evidence_id,
                "question": catalog[bundle.initial_evidence.evidence_id].question_en,
                "answer": human_readable_response(
                    bundle.initial_evidence,
                    catalog[bundle.initial_evidence.evidence_id],
                ),
                "status": bundle.initial_evidence.status.value,
            }
        ]
        for event in self.repository.events(session_id):
            if event.event_type != "ASK_EVIDENCE" or not event.observation:
                continue
            evidence_id = event.action["evidence_id"]
            definition = catalog[evidence_id]
            response = bundle.truth_map()[evidence_id]
            trajectory.append(
                {
                    "step": len(trajectory),
                    "state_hash": event.state_after_hash,
                    "evidence_id": evidence_id,
                    "question": definition.question_en,
                    "answer": human_readable_response(response, definition),
                    "status": response.status.value,
                }
            )
        return trajectory

    def _model_review(self, session_id: str) -> dict[str, Any]:
        review = self.reviews.completed_session_review(session_id)
        review["player_type"] = PlayerType.MODEL.value
        review["ground_truth_tree"] = self.case_trees.get(
            review["case_id"]
        )["processed_tree"]
        forest = self.forest.case_detail(review["case_id"], PlayerType.MODEL)
        review["case_graph"] = {
            "case_id": review["case_id"],
            "session_count": forest["summary"]["session_count"],
            "completed_session_count": forest["summary"][
                "completed_session_count"
            ],
            "participant_count": forest["summary"]["participant_count"],
            "physician_count": 0,
            "physician_session_count": 0,
            "nodes": forest["nodes"],
            "edges": forest["edges"],
        }
        review["community_final_diagnoses"] = forest["final_diagnoses"]
        return review

    @staticmethod
    def _belief(condition_ids: list[str]) -> BeliefSubmission:
        total = len(condition_ids) * (len(condition_ids) + 1) / 2
        return BeliefSubmission(
            diagnoses=[
                DiagnosisBelief(
                    condition_id=condition_id,
                    rank=index + 1,
                    probability=round((len(condition_ids) - index) / total, 6),
                )
                for index, condition_id in enumerate(condition_ids)
            ],
            overall_confidence=0,
        )

    def _request(
        self,
        method: str,
        path: str,
        payload: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        url = f"{self.settings.openrouter_base_url.rstrip('/')}{path}"
        data = json.dumps(payload).encode("utf-8") if payload is not None else None
        headers = {
            "Accept": "application/json",
            "Authorization": f"Bearer {self.settings.openrouter_api_key}",
            "Content-Type": "application/json",
            "X-Title": "ClincForestBench Model Arena",
        }
        request = Request(url, data=data, headers=headers, method=method)
        try:
            with urlopen(
                request, timeout=self.settings.openrouter_timeout_seconds
            ) as response:
                return json.loads(response.read().decode("utf-8"))
        except HTTPError as exc:
            body = exc.read().decode("utf-8", errors="replace")
            raise ValueError(f"OpenRouter HTTP {exc.code}: {body[:600]}") from exc

    @staticmethod
    def _assistant_content(payload: dict[str, Any]) -> str:
        choices = payload.get("choices") or []
        if not choices:
            raise ValueError("OpenRouter response has no choices")
        content = (choices[0].get("message") or {}).get("content")
        if isinstance(content, str):
            return content
        if isinstance(content, list):
            parts = [
                item.get("text", "")
                for item in content
                if isinstance(item, dict) and item.get("type") == "text"
            ]
            return "".join(parts)
        raise ValueError("OpenRouter response has no text content")

    @staticmethod
    def _parse_json_object(content: str) -> dict[str, Any]:
        source = content.strip()
        if source.startswith("```"):
            lines = source.splitlines()
            source = "\n".join(lines[1:-1]).strip()
        start = source.find("{")
        end = source.rfind("}")
        if start < 0 or end < start:
            raise ValueError("Model did not return a JSON object")
        parsed = json.loads(source[start : end + 1])
        if not isinstance(parsed, dict):
            raise ValueError("Model response JSON must be an object")
        return parsed

    @staticmethod
    def _normalize_decision_payload(payload: dict[str, Any]) -> dict[str, Any]:
        """Accept common single-wrapper mistakes without weakening validation."""

        if isinstance(payload.get("diagnoses"), list):
            return payload
        for key in ("required_response", "response", "decision"):
            nested = payload.get(key)
            if isinstance(nested, dict):
                return nested
        return payload

    def _decision_history(self, run_id: str) -> list[dict[str, Any]]:
        history = []
        for interaction in self.repository.model_interactions(run_id):
            decision = interaction.parsed_decision
            application = interaction.application_result
            if (
                not isinstance(decision, dict)
                or not isinstance(decision.get("diagnoses"), list)
                or not isinstance(application, dict)
            ):
                continue
            history.append(
                {
                    "state_step": application.get("state_step"),
                    "diagnoses": decision["diagnoses"],
                    "selected_action_id": application.get("action_id"),
                    "observed_answer": application.get("answer"),
                    "rationale": decision.get("rationale", ""),
                }
            )
        return history

    @staticmethod
    def _safe_error(exc: Exception) -> str:
        if isinstance(exc, ValidationError):
            return f"Invalid model decision: {exc.errors(include_url=False)}"
        return str(exc)
