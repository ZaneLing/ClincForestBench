from fastapi.testclient import TestClient

from backend.app.main import create_app


RESEARCH_HEADERS = {"X-Research-Key": "local-research-only"}


def _completion(decision):
    import json

    return {
        "id": "generation-test",
        "choices": [
            {"message": {"role": "assistant", "content": json.dumps(decision)}}
        ],
        "usage": {"prompt_tokens": 10, "completion_tokens": 10},
    }


def test_model_arena_runs_canonical_loop_and_persists_interactions(cases):
    app = create_app(cases)
    service = app.state.container.model_arena
    service.settings.openrouter_api_key = "test-key"
    case = cases.get(cases.case_ids()[0])
    environment = app.state.container.arena._new_environment(case.case_id)
    environment.reset(case.case_id)
    action_id = next(
        item.evidence_id
        for item in environment.get_available_actions().actions
        if item.dependency_met and item.evidence_id
    )
    decisions = iter(
        [
            {
                "diagnoses": [case.oracle.pathology],
                "next_action_id": action_id,
                "final": False,
                "final_condition_id": None,
                "rationale": "Need one more finding",
            },
            {
                "diagnoses": [case.oracle.pathology],
                "next_action_id": None,
                "final": True,
                "final_condition_id": case.oracle.pathology,
                "rationale": "Enough evidence",
            },
        ]
    )

    requests = []

    def fake_request(method, path, payload=None):
        if path == "/models":
            return {
                "data": [
                    {"id": "openai/test-model", "name": "Test Model"},
                    {"id": "anthropic/test-model", "name": "Other Model"},
                ]
            }
        requests.append(payload)
        return _completion(next(decisions))

    service._request = fake_request
    client = TestClient(app)
    models = client.get("/model-arena/models", headers=RESEARCH_HEADERS)
    assert models.status_code == 200
    assert {item["name"] for item in models.json()["providers"]} == {
        "OpenAI",
        "Anthropic",
    }

    created = client.post(
        "/model-arena/runs",
        headers=RESEARCH_HEADERS,
        json={"model_id": "openai/test-model", "case_id": case.case_id},
    )
    assert created.status_code == 201
    run_id = created.json()["run"]["run_id"]

    first = client.post(
        f"/model-arena/runs/{run_id}/step", headers=RESEARCH_HEADERS
    ).json()
    assert first["state"]["question_count"] == 1
    assert first["interactions"][0]["application_result"]["action_id"] == action_id
    assert len(first["belief_history"]) == 1

    completed = client.post(
        f"/model-arena/runs/{run_id}/step", headers=RESEARCH_HEADERS
    ).json()
    assert completed["run"]["status"] == "COMPLETED"
    assert completed["review"]["player_type"] == "MODEL"
    assert completed["review"]["comparison"]["is_correct"] is True
    assert completed["review"]["case_graph"]["participant_count"] == 1
    assert len(completed["artifact"]["interactions"]) == 2
    assert len(requests) == 2
    first_prompt = __import__("json").loads(requests[0]["messages"][1]["content"])
    second_prompt = __import__("json").loads(requests[1]["messages"][1]["content"])
    assert len(first_prompt["disease_or_outcome_library"]) == len(
        second_prompt["disease_or_outcome_library"]
    )
    assert len(first_prompt["question_or_action_library"]) == len(
        second_prompt["question_or_action_library"]
    )
    first_action = next(
        item
        for item in first_prompt["question_or_action_library"]
        if item["action_id"] == action_id
    )
    second_action = next(
        item
        for item in second_prompt["question_or_action_library"]
        if item["action_id"] == action_id
    )
    assert first_action["status"] == "AVAILABLE"
    assert second_action["status"] == "ALREADY_USED"
    assert first_prompt["stopping_policy"]["normal_target"]
    assert second_prompt["diagnostic_progress"]["previous_decisions"]
    assert second_prompt["diagnostic_progress"]["top1_history"] == [
        case.oracle.pathology
    ]


def test_model_arena_hard_question_limit_forces_top_ranked_final(cases):
    app = create_app(cases)
    service = app.state.container.model_arena
    service.settings.openrouter_api_key = "test-key"
    case = cases.get(cases.case_ids()[0])
    environment = app.state.container.arena._new_environment(case.case_id)
    environment.reset(case.case_id)
    root_actions = [
        item.evidence_id
        for item in environment.get_available_actions().actions
        if item.dependency_met and item.evidence_id
    ]
    decisions = iter(
        [
            {
                "diagnoses": [case.oracle.pathology],
                "next_action_id": root_actions[0],
                "final": False,
                "final_condition_id": None,
            },
            {
                "diagnoses": [case.oracle.pathology],
                "next_action_id": root_actions[1],
                "final": False,
                "final_condition_id": None,
            },
        ]
    )
    service._request = lambda method, path, payload=None: _completion(next(decisions))
    client = TestClient(app)
    created = client.post(
        "/model-arena/runs",
        headers=RESEARCH_HEADERS,
        json={
            "model_id": "openai/test-model",
            "case_id": case.case_id,
            "max_questions": 1,
        },
    ).json()
    run_id = created["run"]["run_id"]
    client.post(f"/model-arena/runs/{run_id}/step", headers=RESEARCH_HEADERS)
    result = client.post(
        f"/model-arena/runs/{run_id}/step", headers=RESEARCH_HEADERS
    ).json()
    assert result["state"]["question_count"] == 1
    assert result["run"]["status"] == "COMPLETED"
    assert result["run"]["forced_final"] is True
    assert result["interactions"][-1]["application_result"]["forced_final"] is True


def test_model_arena_rejects_duplicate_diagnoses_without_changing_state(cases):
    app = create_app(cases)
    service = app.state.container.model_arena
    service.settings.openrouter_api_key = "test-key"
    case = cases.get(cases.case_ids()[0])
    service._request = lambda method, path, payload=None: _completion(
        {
            "diagnoses": [case.oracle.pathology, case.oracle.pathology],
            "next_action_id": "invented-action",
            "final": False,
            "final_condition_id": None,
        }
    )
    client = TestClient(app)
    created = client.post(
        "/model-arena/runs",
        headers=RESEARCH_HEADERS,
        json={"model_id": "openai/test-model", "case_id": case.case_id},
    ).json()
    result = client.post(
        f"/model-arena/runs/{created['run']['run_id']}/step",
        headers=RESEARCH_HEADERS,
    ).json()
    assert result["run"]["status"] == "ACTIVE"
    assert result["state"]["question_count"] == 0
    assert result["belief_history"] == []
    assert "duplicate" in result["interactions"][0]["error"].lower()


def test_model_arena_normalizes_common_response_wrapper(cases):
    app = create_app(cases)
    service = app.state.container.model_arena
    service.settings.openrouter_api_key = "test-key"
    case = cases.get(cases.case_ids()[0])
    service._request = lambda method, path, payload=None: _completion(
        {
            "required_response": {
                "diagnoses": [case.oracle.pathology],
                "next_action_id": None,
                "final": True,
                "final_condition_id": case.oracle.pathology,
                "rationale": "One leading diagnosis; further questions are low yield",
            }
        }
    )
    client = TestClient(app)
    created = client.post(
        "/model-arena/runs",
        headers=RESEARCH_HEADERS,
        json={"model_id": "openai/test-model", "case_id": case.case_id},
    ).json()
    result = client.post(
        f"/model-arena/runs/{created['run']['run_id']}/step",
        headers=RESEARCH_HEADERS,
    ).json()
    assert result["run"]["status"] == "COMPLETED"
    assert result["interactions"][0]["error"] is None
    assert result["interactions"][0]["parsed_decision"]["diagnoses"] == [
        case.oracle.pathology
    ]
