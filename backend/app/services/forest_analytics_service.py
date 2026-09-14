from __future__ import annotations

from collections import defaultdict
from typing import Iterable

from backend.app.domain.enums import PlayerType, SessionStatus
from backend.app.domain.session import BeliefSnapshot, SessionRecord
from backend.app.repositories.base import ArenaRepository
from backend.app.services.case_service import CaseService
from backend.app.services.case_tree_service import CaseTreeService
from backend.app.services.graph_builder import build_case_graph


class ForestAnalyticsService:
    def __init__(
        self,
        cases: CaseService,
        repository: ArenaRepository,
        case_trees: CaseTreeService,
    ) -> None:
        self.cases = cases
        self.repository = repository
        self.case_trees = case_trees

    def case_index(self) -> dict:
        sessions_by_case = defaultdict(list)
        for session in self.repository.all_sessions():
            if session.player.player_type == PlayerType.PHYSICIAN:
                sessions_by_case[session.case_id].append(session)
        entries = {
            item["case_id"]: item for item in self.case_trees.manifest()["cases"]
        }
        cases = []
        for case_id in self.cases.case_ids():
            sessions = sessions_by_case[case_id]
            completed = [
                item for item in sessions if item.status == SessionStatus.COMPLETED
            ]
            entry = entries[case_id]
            bundle = self.cases.get(case_id)
            outcome = self.cases.condition_catalog_for_case(case_id).get(
                bundle.oracle.pathology, {}
            )
            cases.append(
                {
                    "case_id": case_id,
                    "pathology": bundle.oracle.pathology,
                    "pathology_label": outcome.get(
                        "condition_name", bundle.oracle.display_name or bundle.oracle.pathology
                    ),
                    "dataset_name": bundle.dataset.name,
                    "case_type": bundle.case_type,
                    "disease_category": entry["disease_category"],
                    "physician_count": len(
                        {item.player.player_id for item in sessions}
                    ),
                    "physician_session_count": len(sessions),
                    "completed_session_count": len(completed),
                }
            )
        return {"case_count": len(cases), "cases": cases}

    def case_detail(
        self,
        case_id: str,
        player_type: PlayerType = PlayerType.PHYSICIAN,
    ) -> dict:
        bundle = self.cases.get(case_id)
        catalog = self.cases.catalog_for_case(case_id)
        outcome_catalog = self.cases.condition_catalog_for_case(case_id)
        selected_sessions = [
            session
            for session in self.repository.all_sessions()
            if session.case_id == case_id
            and session.player.player_type == player_type
        ]
        completed_sessions = [
            session for session in selected_sessions
            if session.status == SessionStatus.COMPLETED
        ]
        events_by_session = {
            session.session_id: self.repository.events(session.session_id)
            for session in selected_sessions
        }
        states_by_session = {
            session.session_id: self.repository.states(session.session_id)
            for session in selected_sessions
        }
        beliefs_by_session = {
            session.session_id: self.repository.beliefs(session.session_id)
            for session in selected_sessions
        }
        graph = build_case_graph(
            case_id,
            selected_sessions,
            events_by_session,
            states_by_session,
        )

        state_steps: dict[str, int] = {}
        for states in states_by_session.values():
            for snapshot in states:
                state_steps[snapshot.state.state_hash] = snapshot.step

        staged = self._latest_stage_beliefs(beliefs_by_session)
        node_beliefs: dict[str, list[BeliefSnapshot]] = defaultdict(list)
        stage_beliefs: dict[int, list[BeliefSnapshot]] = defaultdict(list)
        for snapshot in staged:
            node_beliefs[snapshot.state_hash].append(snapshot)
            stage_beliefs[snapshot.step].append(snapshot)

        selected_session_count = len(selected_sessions)
        nodes = []
        for node in graph.nodes:
            submissions = node_beliefs[node.state_hash]
            nodes.append(
                {
                    **node.model_dump(mode="json"),
                    "step": state_steps.get(node.state_hash, 0),
                    "visit_rate": self._ratio(
                        node.support, selected_session_count
                    ),
                    "belief_submission_count": len(submissions),
                    "diagnoses": self._with_labels(
                        self._diagnosis_distribution(
                            submissions, bundle.oracle.pathology
                        ),
                        outcome_catalog,
                    ),
                }
            )

        final_beliefs = []
        completed_ids = {item.session_id for item in completed_sessions}
        for session_id, snapshots in beliefs_by_session.items():
            if session_id not in completed_ids:
                continue
            final_beliefs.extend(item for item in snapshots if item.is_final)

        return {
            "case_id": case_id,
            "dataset_name": bundle.dataset.name,
            "case_type": bundle.case_type,
            "player_type": player_type.value,
            "summary": {
                "participant_count": len(
                    {item.player.player_id for item in selected_sessions}
                ),
                "session_count": selected_session_count,
                "physician_count": (
                    len({item.player.player_id for item in selected_sessions})
                    if player_type == PlayerType.PHYSICIAN
                    else 0
                ),
                "physician_session_count": (
                    selected_session_count
                    if player_type == PlayerType.PHYSICIAN
                    else 0
                ),
                "model_count": (
                    len({item.player.player_id for item in selected_sessions})
                    if player_type == PlayerType.MODEL
                    else 0
                ),
                "model_session_count": (
                    selected_session_count
                    if player_type == PlayerType.MODEL
                    else 0
                ),
                "completed_session_count": len(completed_sessions),
                "state_node_count": len(nodes),
            },
            "reference": {
                "pathology": bundle.oracle.pathology,
                "pathology_label": outcome_catalog.get(
                    bundle.oracle.pathology, {}
                ).get("condition_name", bundle.oracle.display_name or bundle.oracle.pathology),
                "differential": [
                    {
                        **item.model_dump(mode="json"),
                        "label": outcome_catalog.get(item.condition, {}).get(
                            "condition_name", item.condition
                        ),
                    }
                    for item in bundle.oracle.differential
                ],
            },
            "stages": [
                {
                    "step": step,
                    "submission_count": len(snapshots),
                    "diagnoses": self._with_labels(
                        self._diagnosis_distribution(
                            snapshots, bundle.oracle.pathology
                        ),
                        outcome_catalog,
                    ),
                }
                for step, snapshots in sorted(stage_beliefs.items())
            ],
            "final_diagnoses": self._with_labels(
                self._diagnosis_distribution(
                    final_beliefs, bundle.oracle.pathology
                ),
                outcome_catalog,
            ),
            "nodes": nodes,
            "edges": [
                {
                    **edge.model_dump(mode="json"),
                    "question": catalog[edge.action_evidence_id].question_en,
                }
                for edge in graph.edges
            ],
        }

    @staticmethod
    def _latest_stage_beliefs(
        beliefs_by_session: dict[str, list[BeliefSnapshot]],
    ) -> list[BeliefSnapshot]:
        selected: dict[tuple[str, int], BeliefSnapshot] = {}
        for session_id, snapshots in beliefs_by_session.items():
            for snapshot in snapshots:
                if snapshot.is_final:
                    continue
                selected[(session_id, snapshot.step)] = snapshot
        return list(selected.values())

    @staticmethod
    def _diagnosis_distribution(
        snapshots: Iterable[BeliefSnapshot],
        pathology: str,
    ) -> list[dict]:
        values = list(snapshots)
        denominator = len(values)
        aggregate: dict[str, dict[str, float | int]] = defaultdict(
            lambda: {
                "selection_count": 0,
                "rank_sum": 0.0,
                "rank_weight_sum": 0.0,
                "top1_count": 0,
            }
        )
        for snapshot in values:
            for diagnosis in snapshot.belief.diagnoses:
                item = aggregate[diagnosis.condition_id]
                item["selection_count"] += 1
                item["rank_sum"] += diagnosis.rank
                item["rank_weight_sum"] += diagnosis.probability
                if diagnosis.rank == 1:
                    item["top1_count"] += 1
        result = []
        for condition, item in aggregate.items():
            count = int(item["selection_count"])
            result.append(
                {
                    "condition": condition,
                    "is_ground_truth": condition == pathology,
                    "selection_count": count,
                    "selection_rate": ForestAnalyticsService._ratio(
                        count, denominator
                    ),
                    "top1_rate": ForestAnalyticsService._ratio(
                        int(item["top1_count"]), denominator
                    ),
                    "mean_rank_when_selected": round(
                        float(item["rank_sum"]) / count, 6
                    ),
                    "mean_rank_weight": round(
                        float(item["rank_weight_sum"]) / denominator, 6
                    )
                    if denominator
                    else 0.0,
                }
            )
        return sorted(
            result,
            key=lambda item: (
                -item["mean_rank_weight"],
                -item["selection_rate"],
                item["condition"],
            ),
        )

    @staticmethod
    def _ratio(numerator: int, denominator: int) -> float:
        return round(numerator / denominator, 6) if denominator else 0.0

    @staticmethod
    def _with_labels(rows: list[dict], catalog: dict[str, dict]) -> list[dict]:
        return [
            {
                **row,
                "label": catalog.get(row["condition"], {}).get(
                    "condition_name", row["condition"]
                ),
            }
            for row in rows
        ]
