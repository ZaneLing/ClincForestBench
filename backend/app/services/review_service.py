from __future__ import annotations

from collections import defaultdict

from backend.app.domain.enums import ActionResultType, ActionType, SessionStatus, TruthStatus
from backend.app.repositories.base import ArenaRepository
from backend.app.services.case_service import CaseService
from backend.app.services.graph_builder import build_case_graph
from backend.app.domain.evidence import human_readable_response


class ReviewService:
    def __init__(self, cases: CaseService, repository: ArenaRepository) -> None:
        self.cases = cases
        self.repository = repository

    def completed_session_review(self, session_id: str) -> dict:
        session = self.repository.get_session(session_id)
        if session.status != SessionStatus.COMPLETED:
            raise ValueError("Ground truth is available only after session completion")
        bundle = self.cases.get(session.case_id)
        catalog = self.cases.catalog_for_case(session.case_id)
        outcomes = self.cases.condition_catalog_for_case(session.case_id)
        events = self.repository.events(session_id)
        snapshots = self.repository.beliefs(session_id)
        beliefs_by_step = defaultdict(list)
        for snapshot in snapshots:
            beliefs_by_step[snapshot.step].append(snapshot)

        def belief_payload(step: int):
            candidates = beliefs_by_step.get(step, [])
            if not candidates:
                return None
            selected = next(
                (item for item in reversed(candidates) if item.is_final),
                candidates[-1],
            )
            return selected.belief.model_dump(mode="json")

        initial = bundle.initial_evidence
        trajectory = [
            {
                "step": 0,
                "state_hash": self.repository.states(session_id)[0].state.state_hash,
                "evidence_id": initial.evidence_id,
                "question": catalog[initial.evidence_id].question_en,
                "answer": human_readable_response(
                    initial, catalog[initial.evidence_id]
                ),
                "status": initial.status.value,
                "belief": belief_payload(0),
            }
        ]
        asked_ids = set()
        for event in events:
            if (
                event.event_type != ActionType.ASK_EVIDENCE.value
                or event.result_type != ActionResultType.OBSERVATION.value
                or not event.observation
            ):
                continue
            evidence_id = event.action["evidence_id"]
            asked_ids.add(evidence_id)
            response = bundle.truth_map()[evidence_id]
            trajectory.append(
                {
                    "step": len(trajectory),
                    "state_hash": event.state_after_hash,
                    "evidence_id": evidence_id,
                    "question": catalog[evidence_id].question_en,
                    "answer": human_readable_response(
                        response, catalog[evidence_id]
                    ),
                    "status": response.status.value,
                    "belief": belief_payload(len(trajectory)),
                }
            )

        final_candidates = [item for item in snapshots if item.is_final]
        if not final_candidates:
            raise ValueError("Completed session has no final belief")
        final_belief = final_candidates[-1].belief
        ranked = sorted(final_belief.diagnoses, key=lambda item: item.rank)
        predicted = ranked[0].condition_id
        pathology_rank = next(
            (item.rank for item in ranked if item.condition_id == bundle.oracle.pathology),
            None,
        )
        positive_statuses = {TruthStatus.PRESENT, TruthStatus.VALUE}
        positive_truth = [
            response for response in bundle.truth
            if response.status in positive_statuses
        ]
        missed = [
            response for response in positive_truth
            if response.evidence_id not in asked_ids
            and response.evidence_id != initial.evidence_id
        ]
        graph = build_case_graph(
            bundle.case_id,
            self.repository.all_sessions(),
            {
                item.session_id: self.repository.events(item.session_id)
                for item in self.repository.all_sessions()
                if item.case_id == bundle.case_id
            },
            {
                item.session_id: self.repository.states(item.session_id)
                for item in self.repository.all_sessions()
                if item.case_id == bundle.case_id
            },
        )
        return {
            "session_id": session_id,
            "player_type": session.player.player_type.value,
            "case_id": bundle.case_id,
            "dataset_name": bundle.dataset.name,
            "case_type": bundle.case_type,
            "generation_mode": bundle.generation_mode,
            "terminology": (
                "workflow outcome"
                if bundle.case_type == "WORKFLOW_FOREST"
                else "diagnosis"
            ),
            "fidelity_note": bundle.fidelity_note,
            "comparison": {
                "is_correct": predicted == bundle.oracle.pathology,
                "predicted_diagnosis": predicted,
                "ground_truth_diagnosis": bundle.oracle.pathology,
                "predicted_label": outcomes.get(predicted, {}).get(
                    "condition_name", predicted
                ),
                "ground_truth_label": outcomes.get(
                    bundle.oracle.pathology, {}
                ).get("condition_name", bundle.oracle.display_name or bundle.oracle.pathology),
                "ground_truth_rank_in_submission": pathology_rank,
                "questions_asked": len(asked_ids),
                "positive_findings_discovered": sum(
                    bundle.truth_map()[evidence_id].status in positive_statuses
                    for evidence_id in asked_ids
                ),
                "positive_findings_missed": len(missed),
            },
            "trajectory": trajectory,
            "missed_positive_findings": [
                {
                    "evidence_id": response.evidence_id,
                    "question": catalog[response.evidence_id].question_en,
                    "answer": human_readable_response(
                        response,
                        catalog[response.evidence_id],
                    ),
                }
                for response in missed
            ],
            "oracle_differential": [
                item.model_dump(mode="json")
                for item in bundle.oracle.differential
            ],
            "case_graph": {
                "case_id": graph.case_id,
                "session_count": graph.session_count,
                "completed_session_count": graph.completed_session_count,
                "participant_count": graph.participant_count,
                "physician_count": graph.physician_count,
                "physician_session_count": graph.physician_session_count,
                "nodes": [node.model_dump(mode="json") for node in graph.nodes],
                "edges": [
                    {
                        **edge.model_dump(mode="json"),
                        "question": catalog[edge.action_evidence_id].question_en,
                    }
                    for edge in graph.edges
                ],
            },
        }

    def completed_session_artifact(self, session_id: str) -> dict:
        """Return the canonical, single-session JSON artifact after completion."""
        review = self.completed_session_review(session_id)
        session = self.repository.get_session(session_id)
        outcomes = self.cases.condition_catalog_for_case(session.case_id)
        beliefs = self.repository.beliefs(session_id)
        return {
            "schema_version": "clincforestbench.arena-run.v1",
            "export_type": "completed_arena_run",
            "generated_at": (
                session.completed_at.isoformat() if session.completed_at else None
            ),
            "capture_semantics": {
                "diagnosis_input": (
                    "clinician_selected_ranked_workflow_outcome_list"
                    if review["case_type"] == "WORKFLOW_FOREST"
                    else "clinician_selected_ranked_list"
                ),
                "probability": "rank_derived_not_clinician_entered",
                "overall_confidence": "not_collected",
            },
            "session": session.model_dump(mode="json"),
            "dataset_name": review["dataset_name"],
            "case_type": review["case_type"],
            "generation_mode": review["generation_mode"],
            "fidelity_note": review["fidelity_note"],
            "patient_path": review["trajectory"],
            "belief_history": [
                {
                    **snapshot.model_dump(mode="json"),
                    "submission_type": (
                        "FINAL_DIAGNOSIS" if snapshot.is_final else "STAGE_DIAGNOSIS"
                    ),
                }
                for snapshot in beliefs
            ],
            "event_log": [
                event.model_dump(mode="json")
                for event in self.repository.events(session_id)
            ],
            "observation_states": [
                state.model_dump(mode="json")
                for state in self.repository.states(session_id)
            ],
            "outcome": review["comparison"],
            "reference": {
                "oracle_differential": review["oracle_differential"],
                "missed_positive_findings": review["missed_positive_findings"],
                "outcome_labels": {
                    key: value.get("condition_name", key)
                    for key, value in outcomes.items()
                },
            },
        }
