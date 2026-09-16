from backend.app.domain.temporal import (
    PendingAction,
    PendingStatus,
    TemporalCase,
    TemporalReplayMode,
    TemporalState,
    compute_temporal_state_hash,
)
from backend.app.domain.temporal_environment import TemporalReplayEnvironment
from etl.temporal_v2.common import build_temporal_graph, make_event


def temporal_case() -> TemporalCase:
    event = make_event(
        case_id="CFB_TEST_TEMPORAL",
        event_id="E_TROP_1",
        event_type="LAB_RESULT",
        display="Troponin",
        modality="LAB",
        dataset="TEST",
        source_table="labs",
        source_row_id="1",
        relative_order_min=10,
        relative_available_min=40,
        confidence="EXACT",
        availability_semantics="TEST_RESULT_TIME",
        result={"value": 0.08, "flag": "elevated"},
    )
    reference = {
        "adjudicated_primary_diagnosis": "Pulmonary embolism",
        "reference_strength": "TEST",
    }
    return TemporalCase(
        case_id="CFB_TEST_TEMPORAL",
        task_type="ED_TEMPORAL_DIAGNOSIS",
        source={"dataset_family": "TEST"},
        anchor={"anchor_type": "ED_ARRIVAL", "relative_zero": 0},
        initial_state={"chief_complaint": "chest pain"},
        timeline_events=[event],
        hidden_evidence_pool=[event.event_id],
        realized_trajectory=[],
        reference=reference,
        case_quality={"checks": {"real_results_only": True}},
        temporal_quality={"warnings": []},
        arena_config={
            "time_mode": "WAIT_FOR_NEXT_RESULT",
            "unobserved_action_result": "UNOBSERVED_IN_RECORDED_EPISODE",
        },
        temporal_graph=build_temporal_graph("CFB_TEST_TEMPORAL", [event], reference),
    )


def test_temporal_hash_distinguishes_time_and_pending_state():
    pending = PendingAction(
        pending_id="P1",
        action_id="ORDER_TROPONIN",
        ordered_game_time=5,
        expected_available_game_time=35,
        source_event_id="E_TROP_1",
        temporal_replay_mode=TemporalReplayMode.OBSERVED_RESULT_WITH_SHIFTED_TAT,
        status=PendingStatus.PENDING,
    )
    early = compute_temporal_state_hash("CASE", [], [pending], 15)
    late = compute_temporal_state_hash("CASE", [], [pending], 60)
    available = compute_temporal_state_hash(
        "CASE",
        ["E_TROP_1"],
        [pending.model_copy(update={"status": PendingStatus.AVAILABLE})],
        60,
    )
    assert early != late
    assert late != available


def test_temporal_environment_shifts_real_tat_without_inventing_result():
    environment = TemporalReplayEnvironment(temporal_case())
    environment.state = TemporalState(
        case_id="CFB_TEST_TEMPORAL", current_time_min=5
    ).refreshed()
    pending = environment.order("ORDER_TROPONIN")
    assert pending.expected_available_game_time == 35
    assert environment.state.revealed_event_ids == []
    resolved = environment.wait_for_next_result()
    assert environment.state.current_time_min == 35
    assert resolved[0].result["value"] == 0.08
    assert environment.event_log[-1]["resolved_event_ids"] == ["E_TROP_1"]

    missing = TemporalReplayEnvironment(temporal_case()).order("ORDER_D_DIMER")
    assert missing.status == PendingStatus.UNOBSERVED
    assert missing.temporal_replay_mode == TemporalReplayMode.UNOBSERVED
    assert missing.source_event_id is None


def test_temporal_graph_keeps_action_and_result_as_separate_time_nodes():
    case = temporal_case()
    by_id = {node.node_id: node for node in case.temporal_graph.nodes}
    assert by_id["E_TROP_1::ACTION"].reveal_time_min == 10
    assert by_id["E_TROP_1::RESULT"].reveal_time_min == 40
    edge = next(
        item
        for item in case.temporal_graph.edges
        if item.edge_type == "RESULT_AVAILABLE"
    )
    assert edge.latency_min == 30


def test_doctor_arena_returns_natural_presentation_and_reveals_without_wait(
    tmp_path,
):
    from backend.app.services.temporal_arena_service import TemporalArenaService

    case = temporal_case()

    class Cases:
        root = tmp_path

        @staticmethod
        def get(case_id):
            if case_id != case.case_id:
                raise KeyError(case_id)
            return case

        @staticmethod
        def manifest():
            return {
                "case_count": 1,
                "dataset_case_counts": {"TEST": 1},
                "cases": [
                    {
                        "case_id": case.case_id,
                        "dataset_name": "TEST",
                        "task_type": case.task_type,
                        "event_count": 1,
                        "eligible_event_count": 1,
                        "max_time_min": 45,
                    }
                ],
            }

    arena = TemporalArenaService(Cases(), tmp_path)
    state = arena.create(case.case_id, "doctor")
    assert state["initial_presentation"]["headline"]
    assert state["initial_presentation"]["sections"][0]["rows"][0] == {
        "label": "主诉",
        "value": "chest pain",
    }

    state = arena.submit_belief(
        state["session_id"], "doctor", ["Pulmonary embolism"]
    )
    state = arena.order(state["session_id"], "doctor", "ORDER_TROPONIN")

    assert state["last_action_outcome"]["status"] == "AVAILABLE"
    assert state["current_time_min"] == 30
    assert state["checkpoint"] == 1
    assert state["belief_required"] is True
    assert state["pending_actions"][0]["status"] == "AVAILABLE"
    assert state["newly_revealed_event_ids"] == ["E_TROP_1"]
    assert state["revealed_events"][0]["presentation"]["blocks"][0]["rows"] == [
        {"label": "Troponin", "value": "0.08"}
    ]
    assert any(
        item["event_type"] == "RESULT_REVEALED"
        for item in arena._load_owned(state["session_id"], "doctor")["event_log"]
    )


def test_temporal_research_endpoint_is_protected(cases):
    from fastapi.testclient import TestClient

    from backend.app.main import create_app

    client = TestClient(create_app(cases))
    assert client.get("/research/temporal/cases").status_code == 403
    response = client.get(
        "/research/temporal/cases",
        headers={"X-Research-Key": "local-research-only"},
    )
    assert response.status_code == 200
    assert response.json()["case_version"] == "2.0.0"


def test_temporal_sidebar_indexes_share_the_complete_manifest(cases):
    from fastapi.testclient import TestClient

    from backend.app.main import create_app

    client = TestClient(create_app(cases))
    manifest = client.get(
        "/research/temporal/cases",
        headers={"X-Research-Key": "local-research-only"},
    ).json()
    arena = client.get("/temporal/cases").json()
    forest = client.get(
        "/research/temporal/forest/cases",
        headers={"X-Research-Key": "local-research-only"},
    ).json()

    manifest_ids = {item["case_id"] for item in manifest["cases"]}
    assert manifest["case_count"] >= 40
    assert {item["case_id"] for item in arena["cases"]} == manifest_ids
    assert {item["case_id"] for item in forest["cases"]} == manifest_ids
    expected_base_counts = {
        "MC-MED v1.0.1": 10,
        "MIMIC-IV multimodal": 10,
        "NEJM CPC": 5,
        "PMC Case Reports": 5,
        "eICU-CRD v2.0": 10,
    }
    for dataset, count in expected_base_counts.items():
        assert arena["dataset_case_counts"][dataset] == count
    if manifest.get("interaction_mvp", {}).get("status") == "READY":
        for dataset in (
            "MediScope",
            "MedPI",
            "PatientSim",
            "Meddies Persona VIE",
            "MedMemoryBench",
            "MedDialogRubrics",
        ):
            assert arena["dataset_case_counts"][dataset] >= 1
    case_id = next(iter(manifest_ids))
    detail = client.get(
        f"/research/temporal/forest/cases/{case_id}",
        headers={"X-Research-Key": "local-research-only"},
    ).json()
    evaluation = detail["trajectory_evaluation"]
    assert evaluation["status"] in {"READY", "NO_COMPLETED_TRAJECTORIES"}
    assert "exact_top1_accuracy" in evaluation["aggregate"]
    assert any(
        item["key"] == "mean_recorded_action_overlap_rate"
        for item in evaluation["metric_definitions"]
    )
    assert evaluation["interpretation_limits"]
    case_detail = client.get(
        f"/research/temporal/cases/{case_id}",
        headers={"X-Research-Key": "local-research-only"},
    ).json()
    assert case_detail["trajectory_evaluation"]["metric_definitions"]


def test_temporal_model_decision_contract_accepts_final_alias():
    from backend.app.services.temporal_model_arena_service import (
        TemporalModelArenaService,
    )

    decision = TemporalModelArenaService._validate_decision(
        {
            "diagnoses": ["Pulmonary embolism", "Acute coronary syndrome"],
            "next_action_id": None,
            "final": True,
            "final_condition_id": "Pulmonary embolism",
            "rationale": "Leading diagnosis is stable.",
        }
    )
    assert decision["final_diagnosis"] == "Pulmonary embolism"
    assert decision["diagnoses"] == [
        "Pulmonary embolism",
        "Acute coronary syndrome",
    ]


def test_temporal_model_prompt_uses_model_decided_stop_and_catalog_actions():
    import json

    from backend.app.services.temporal_model_arena_service import (
        TemporalModelArenaService,
    )

    service = TemporalModelArenaService.__new__(TemporalModelArenaService)
    request = service._build_request(
        {
            "model_id": "test/model",
            "max_actions": 30,
            "interactions": [
                {
                    "error": None,
                    "parsed_decision": {
                        "diagnoses": ["Pulmonary embolism"],
                        "final": False,
                    },
                    "application_result": {"status": "REVEALED"},
                    "step": step,
                }
                for step in range(1, 5)
            ],
        },
        {
            "dataset_name": "TEST",
            "case_id": "CFB_TEST_TEMPORAL",
            "task_type": "ED_TEMPORAL_DIAGNOSIS",
            "action_count": 4,
            "initial_state": {"chief_complaint": "chest pain"},
            "current_time_min": 12,
            "revealed_events": [],
            "pending_actions": [],
            "available_actions": [
                {
                    "action_id": "ORDER_TROPONIN",
                    "display": "Troponin",
                    "modality": "LAB",
                }
            ],
            "diagnosis_catalog": ["Pulmonary embolism"],
        },
    )
    turn = json.loads(request["messages"][1]["content"])

    assert turn["arena"]["early_stop_policy"] == "MODEL_DECIDES"
    assert turn["arena"]["automatic_early_stop"] is False
    assert "recommend_finalize_now" not in turn["diagnostic_progress"]
    assert "current_top1_streak" not in turn["diagnostic_progress"]
    assert turn["action_library"] == [
        {
            "action_id": "ORDER_TROPONIN",
            "display": "Troponin",
            "modality": "LAB",
            "status": "AVAILABLE",
        }
    ]
    rules = " ".join(turn["rules"])
    assert "no automatic early-stop threshold" in rules
    assert "UNOBSERVED_IN_RECORDED_EPISODE" in rules
    assert "free-form or invented actions are rejected" in rules
    assert "never request WAIT" in request["messages"][0]["content"]
    assert all(item["action_id"] != "WAIT" for item in turn["action_library"])


def test_temporal_model_evaluation_detects_wrong_early_stop():
    from backend.app.services.temporal_model_arena_service import (
        TemporalModelArenaService,
    )

    run = {
        "max_actions": 5,
        "forced_final": False,
        "interactions": [
            {
                "latency_ms": 120,
                "error": None,
                "response_payload": {
                    "usage": {
                        "prompt_tokens": 100,
                        "completion_tokens": 20,
                        "total_tokens": 120,
                        "cost": 0.001,
                        "completion_tokens_details": {"reasoning_tokens": 5},
                    }
                },
            }
        ],
    }
    session = {
        "action_count": 1,
        "ordered_event_ids": ["E_TROP_1"],
        "revealed_event_ids": [],
        "pending_actions": [{"status": "PENDING"}],
        "belief_history": [
            {
                "checkpoint": 0,
                "game_time_min": 0,
                "diagnoses": ["Acute coronary syndrome"],
            }
        ],
        "event_log": [{"event_type": "ORDER_ACTION"}],
    }
    evaluation = TemporalModelArenaService._evaluate_run(
        run,
        session,
        temporal_case(),
        {
            "predicted_diagnosis": "Acute coronary syndrome",
            "ground_truth_diagnosis": "Pulmonary embolism",
            "is_exact_match": False,
            "elapsed_game_time_min": 0,
        },
    )

    assert evaluation["outcome"]["reference_ever_considered"] is False
    assert evaluation["evidence_acquisition"]["recorded_action_precision"] == 1.0
    assert evaluation["evidence_acquisition"]["source_evidence_reveal_coverage"] == 0.0
    assert evaluation["flags"]["ended_with_pending_results"] is True
    assert evaluation["flags"]["premature_finalization_proxy"] is True
    assert evaluation["execution"]["total_tokens"] == 120
