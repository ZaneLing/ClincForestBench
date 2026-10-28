
from backend.app.services.clinical_presentation import event_presentation
from etl.source_adapters.common import make_event
from etl.source_adapters.interaction import (
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


def test_interaction_answers_are_case_scoped_without_sequential_unlocking(cases):
    from backend.app.domain.environment import DDXPlusEnvironment
    for case in cases.cases.values():
        if case.dataset.name not in {"MedPI", "MediScope", "MedMemoryBench"}:
            continue
        environment = DDXPlusEnvironment(cases.cases, cases.catalog_for_case(case.case_id))
        environment.reset(case.case_id)
        assert all(action.dependency_met for action in environment.get_available_actions().actions)
        for evidence_id, records in case.evidence_records.items():
            assert case.truth_map()[evidence_id].value == [r["result"] for r in records]
