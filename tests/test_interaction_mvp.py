import pytest

from backend.app.domain.temporal import TemporalCase
from backend.app.services.clinical_presentation import event_presentation
from backend.app.services.temporal_arena_service import TemporalArenaService
from backend.app.services.temporal_case_service import TemporalCaseService
from etl.common import dump_json
from etl.temporal_v2.common import build_temporal_graph, make_event
from etl.temporal_v2.interaction import (
    _medical_record_facts,
    consultation_pairs,
    extract_questions,
    parse_speaker_turns,
)


def test_parse_mediscope_turns_and_preserve_source_answers():
    text = (
        "患者：胸痛两小时<attachment>.jpg<attachment>\n\n"
        "医生：疼痛会放射到左臂吗？\n\n"
        "患者：会，而且出冷汗。\n\n"
        "医生：有没有发热？\n\n患者：没有。"
    )
    turns = parse_speaker_turns(text)
    initial, pairs = consultation_pairs(
        turns, doctor_roles=("doctor",), patient_roles=("patient",)
    )
    assert "已上传检查报告" in initial
    assert [item["answer"] for item in pairs] == ["会，而且出冷汗。", "没有。"]


def test_extract_questions_does_not_include_non_question_conclusion():
    value = extract_questions("先了解一下。疼痛多久了？有没有发热？建议稍后复查。")
    assert value == "疼痛多久了？ 有没有发热？"
    assert "建议" not in value


def test_rubric_fact_pool_excludes_the_protected_final_diagnosis():
    facts = _medical_record_facts(
        "患者咳嗽三天 患者无高热 2025-01-01胸片未见浸润影 患者诊断为急性支气管炎"
    )
    assert any("无高热" in fact for fact in facts)
    assert not any("诊断为" in fact for fact in facts)


def test_patient_answer_is_rendered_as_natural_language_block():
    event = make_event(
        case_id="C",
        event_id="E",
        event_type="CONSULTATION_QUESTION_ANSWER",
        display="有没有发热？",
        modality="HISTORY",
        dataset="TEST",
        source_table="turns",
        source_row_id="1",
        relative_order_min=1,
        relative_available_min=2,
        confidence="HIGH",
        availability_semantics="SOURCE_TURN",
        result={"patient_answer": "没有发热，但有寒战。"},
    )
    presentation = event_presentation(event)
    assert presentation["blocks"][0] == {
        "title": "患者回答",
        "kind": "NARRATIVE",
        "text": "没有发热，但有寒战。",
    }


def test_media_metadata_is_preserved_for_frontend_rendering():
    event = make_event(
        case_id="C",
        event_id="IMG",
        event_type="SOURCE_IMAGE_REVIEW",
        display="查看报告",
        modality="IMAGING",
        dataset="TEST",
        source_table="images",
        source_row_id="2",
        relative_order_min=0,
        relative_available_min=1,
        confidence="HIGH",
        availability_semantics="SOURCE_TURN",
        result={
            "media_asset": "report.jpg",
            "media_type": "image/jpeg",
            "caption": "源报告",
        },
    )
    assert event_presentation(event)["media"] == [
        {
            "asset": "report.jpg",
            "media_type": "image/jpeg",
            "caption": "源报告",
        }
    ]


def _case(case_id: str, action_names: list[str], *, sequential: bool) -> TemporalCase:
    events = [
        make_event(
            case_id=case_id,
            event_id=f"{case_id}::E{index}",
            event_type="CONSULTATION_QUESTION_ANSWER",
            display=f"Question {name}?",
            modality="HISTORY",
            dataset="INTERACTION_TEST",
            source_table="turns",
            source_row_id=str(index),
            relative_order_min=index * 2,
            relative_available_min=index * 2 + 1,
            confidence="HIGH",
            availability_semantics="SOURCE_TURN",
            result={"patient_answer": f"Answer {name}."},
            action_id=name,
        )
        for index, name in enumerate(action_names, 1)
    ]
    reference = {
        "reference_diagnosis": "Example",
        "reference_strength": "PROXY",
        "is_absolute_ground_truth": False,
    }
    return TemporalCase(
        case_id=case_id,
        task_type="MULTI_TURN_CONSULTATION_REPLAY",
        source={"dataset_family": "INTERACTION_TEST", "access_class": "PUBLIC_TEST"},
        anchor={"anchor_type": "SOURCE_SEQUENCE", "relative_zero": 0},
        initial_state={"presentation": "Initial complaint"},
        timeline_events=events,
        hidden_evidence_pool=[event.event_id for event in events],
        realized_trajectory=[],
        reference=reference,
        case_quality={"checks": {"source_backed_results_only": True}},
        temporal_quality={"warnings": []},
        arena_config={
            "max_questions": 30,
            "action_catalog_scope": "CASE",
            "sequential_actions": sequential,
        },
        temporal_graph=build_temporal_graph(case_id, events, reference),
    )


def test_case_scoped_sequential_catalog_never_leaks_another_patient_action(tmp_path):
    first = _case("CASE_A", ["ASK_A1", "ASK_A2"], sequential=True)
    other = _case("CASE_B", ["ASK_B1"], sequential=False)

    class Cases:
        root = tmp_path

        @staticmethod
        def get(case_id):
            return {"CASE_A": first, "CASE_B": other}[case_id]

        @staticmethod
        def manifest():
            return {
                "cases": [
                    {"case_id": "CASE_A", "reference_label": "Example"},
                    {"case_id": "CASE_B", "reference_label": "Other"},
                ]
            }

    arena = TemporalArenaService(Cases(), tmp_path)
    state = arena.create("CASE_A", "doctor")
    assert [item["action_id"] for item in state["available_actions"]] == ["ASK_A1"]
    state = arena.submit_belief(state["session_id"], "doctor", ["Example"])
    state = arena.order(state["session_id"], "doctor", "ASK_A1")
    assert [item["action_id"] for item in state["available_actions"]] == ["ASK_A2"]


def test_public_case_media_is_confined_to_its_bundle(tmp_path):
    case = _case("CASE_MEDIA", ["ASK"], sequential=False)
    bundle = tmp_path / "data/processed/temporal/v2/case_bundles/test/CASE_MEDIA"
    dump_json(bundle / "case.json", case.model_dump(mode="json"))
    (bundle / "media").mkdir()
    (bundle / "media/report.jpg").write_bytes(b"jpeg-test")
    dump_json(
        tmp_path / "data/processed/temporal/v2/manifest.json",
        {
            "cases": [
                {
                    "case_id": "CASE_MEDIA",
                    "path": str((bundle / "case.json").relative_to(tmp_path)),
                }
            ]
        },
    )
    service = TemporalCaseService(tmp_path)
    assert service.public_media_path("CASE_MEDIA", "report.jpg").read_bytes() == b"jpeg-test"
    with pytest.raises(KeyError):
        service.public_media_path("CASE_MEDIA", "../case.json")
