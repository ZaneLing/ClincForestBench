"""Read-only projection of persisted demo visits into the classic state graph.

No legacy sessions, beliefs, probabilities, or clinician statistics are inserted.
Node identity and merging reuse the actual DDXPlus environment and graph builder.
"""
from __future__ import annotations

from collections import Counter
from datetime import datetime

from backend.app.domain.action import ClinicalAction
from backend.app.domain.enums import ActionResultType, ActionType, ArenaMode, BeliefCaptureMode, PlayerType, SessionStatus
from backend.app.domain.environment import DDXPlusEnvironment
from backend.app.domain.session import Player, SessionEvent, SessionRecord, StateSnapshot
from backend.app.domain.evidence import human_readable_response
from backend.app.services.encounter_catalog import bilingual
from backend.app.services.graph_builder import build_case_graph


def simulation_case_index(cases, documents):
    grouped = {}
    for doc in documents:
        if doc.get("is_simulation") and doc["case_id"] in cases.cases:
            grouped.setdefault(doc["case_id"], []).append(doc)
    rows = []
    for case_id, visits in sorted(grouped.items()):
        case = cases.get(case_id)
        if case.dataset.name != "DDXPlus":
            continue
        rows.append({"case_id": case_id, "dataset_name": case.dataset.name,
                     "case_type": case.case_type, "pathology": case.oracle.pathology,
                     "pathology_label": case.oracle.display_name or case.oracle.pathology,
                     "disease_category": "", "physician_count": 0, "physician_session_count": 0,
                     "simulation_count": len({doc["owner"] for doc in visits}), "simulation_session_count": len(visits),
                     "completed_session_count": sum(doc["status"] == "COMPLETED" for doc in visits)})
    return {"case_count": len(rows), "cases": rows, "record_type": "SIMULATION"}


def project_classic_simulations(cases, documents, case_id, locale="en"):
    case = cases.get(case_id)
    if case.dataset.name != "DDXPlus":
        raise ValueError("Classic simulation projection currently supports DDXPlus evidence actions only")
    selected = [doc for doc in documents if doc.get("is_simulation") and doc["case_id"] == case_id]
    sessions, states_by_session, events_by_session, paths = [], {}, {}, []
    state_steps, state_payloads, final_labels = {}, {}, Counter()
    for index, doc in enumerate(selected, 1):
        session_id = doc["id"]
        environment = DDXPlusEnvironment(cases.cases, cases.catalog_for_case(case_id))
        initial = environment.reset(case_id)
        snapshots = [StateSnapshot(session_id=session_id, step=0, state=initial)]
        events, evidence_ids = [], []
        for event in doc["events"]:
            if event["type"] != "ACTION":
                continue
            if event.get("result_status") != "RECORDED":
                break
            records = event.get("records", [])
            if len(records) != 1 or not records[0]["source_id"].startswith("E_"):
                raise ValueError("Cannot safely project a non-evidence or multi-record action into the classic graph")
            evidence_id = records[0]["source_id"]
            action = ClinicalAction(action_type=ActionType.ASK_EVIDENCE, evidence_id=evidence_id,
                                    client_event_id=event["client_event_id"])
            result = environment.step(action)
            if result.result_type != ActionResultType.OBSERVATION or result.observation is None:
                raise ValueError("Recorded demo action cannot be replayed by the classic environment")
            # Saved answer and original source response must agree.
            source_result = records[0].get("result", {})
            source_status = source_result.get("status")
            if source_status != result.observation.status.value or source_result.get("answer") != human_readable_response(result.observation, cases.catalog_for_case(case_id)[evidence_id]):
                raise ValueError("Recorded demo answer differs from the classic source response")
            evidence_ids.append(evidence_id)
            events.append(SessionEvent(event_id=event["id"], session_id=session_id,
                sequence=len(events) + 1, event_type=ActionType.ASK_EVIDENCE.value,
                client_event_id=event["client_event_id"], action=action.model_dump(mode="json"),
                observation=result.observation.model_dump(mode="json"),
                state_before_hash=result.state_before_hash, state_after_hash=result.state_after_hash,
                result_type=result.result_type.value))
            snapshots.append(StateSnapshot(session_id=session_id, step=result.state.question_count, state=result.state))
        final_state = environment.get_state()
        sessions.append(SessionRecord(session_id=session_id, case_id=case_id, case_hash=case.case_hash,
            player=Player(player_id="simulation-%d" % index, player_type=PlayerType.RESEARCHER),
            arena_mode=ArenaMode.FREE_EXPLORATION, belief_capture_mode=BeliefCaptureMode.ON_CHANGE,
            dataset_version=case.dataset.dataset_version, case_version=case.dataset.case_manifest_version,
            arena_version="classic-simulation-projection.v1", ui_version="0.1.0", random_seed=0,
            status=(SessionStatus.COMPLETED if doc["status"] == "COMPLETED" else
                    SessionStatus.ACTIVE if doc["status"] == "ACTIVE" else SessionStatus.ABORTED),
            started_at=datetime.fromisoformat(doc["created_at"]),
            completed_at=datetime.fromisoformat(doc["completed_at"]) if doc.get("completed_at") else None,
            final_state_hash=final_state.state_hash))
        states_by_session[session_id], events_by_session[session_id] = snapshots, events
        for snapshot in snapshots:
            state_steps[snapshot.state.state_hash] = snapshot.step
            state_payloads[snapshot.state.state_hash] = snapshot.state.public_payload()
        final_labels.update(doc.get("diagnoses", []))
        paths.append({"label": "模拟轨迹 %d" % index, "evidence_ids": evidence_ids,
                      "state_hashes": [snapshot.state.state_hash for snapshot in snapshots],
                      "final_state_hash": final_state.state_hash, "diagnoses": doc.get("diagnoses", []),
                      "status": doc["status"]})
    graph = build_case_graph(case_id, sessions, events_by_session, states_by_session)
    nodes = [{**node.model_dump(mode="json"), "step": state_steps[node.state_hash],
              "visit_rate": node.support / len(selected) if selected else 0,
              "belief_submission_count": 0, "diagnoses": [],
              "observations": state_payloads[node.state_hash]["revealed_evidences"]}
             for node in graph.nodes]
    catalog = cases.catalog_for_case(case_id)
    return {"case_id": case_id, "dataset_name": case.dataset.name, "case_type": case.case_type,
            "record_type": "SIMULATION", "player_type": "RESEARCHER", "projection_mode": "READ_ONLY_SOURCE_REPLAY",
            "summary": {"participant_count": len({doc["owner"] for doc in selected}), "session_count": len(selected),
                        "physician_count": 0, "physician_session_count": 0,
                        "simulation_count": len({doc["owner"] for doc in selected}), "simulation_session_count": len(selected),
                        "completed_session_count": graph.completed_session_count, "state_node_count": len(nodes)},
            "reference": {"pathology": case.oracle.pathology,
                          "pathology_label": case.oracle.display_name or case.oracle.pathology,
                          "differential": [item.model_dump(mode="json") for item in case.oracle.differential]},
            "stages": [], "final_diagnoses": [], "final_diagnosis_texts": [
                {"text": text, "count": count} for text, count in sorted(final_labels.items())],
            "nodes": nodes, "evidence_labels": {evidence_id: bilingual(definition.question_en).get(locale, definition.question_en)
                                                     for evidence_id, definition in catalog.items()},
            "edges": [{**edge.model_dump(mode="json"),
                       "question": bilingual(catalog[edge.action_evidence_id].question_en).get(locale, catalog[edge.action_evidence_id].question_en)} for edge in graph.edges],
            "source_trajectories": paths,
            "limitations": ["模拟演示，不是真实医生决策；不会写入或影响旧版真人会话。",
                             "按已获得证据集合合并状态：不同问询顺序可能汇合，不表示决策顺序相同。",
                             "原轨迹没有逐轮诊断排序或置信度，保持未记录，不补造概率。",
                             "原模拟诊断为自由文本，仅展示原文，不当作已验证诊断或排行榜成绩。"]}
