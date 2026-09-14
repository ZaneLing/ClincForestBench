from backend.app.domain.enums import EvidenceDataType, TruthStatus
from backend.app.domain.evidence import (
    EvidenceDefinition,
    EvidenceResponse,
    build_dense_truth,
    group_evidence_tokens,
    human_readable_response,
    parse_evidence_token,
)


def definition(evidence_id: str, data_type: EvidenceDataType, parent=None):
    return EvidenceDefinition(
        evidence_id=evidence_id,
        question_en=evidence_id,
        is_antecedent=False,
        data_type=data_type,
        possible_values=[],
        value_meanings={},
        code_question=parent or evidence_id,
        parent_evidence_id=parent,
        is_root_question=parent is None,
        semantic_role="PRESENTING_SYMPTOM" if parent is None else "SYMPTOM_ATTRIBUTE",
        exposure_tier=1,
        mapping_version="test",
    )


def test_evidence_parser_covers_all_ddxplus_shapes():
    assert parse_evidence_token("E_1").value is True
    assert parse_evidence_token("E_2_@_V_10").value == "V_10"
    assert parse_evidence_token("E_3_@_4").value == "4"
    assert group_evidence_tokens(["E_4_@_V_1", "E_4_@_V_2"])["E_4"] == ["V_1", "V_2"]


def test_negative_parent_makes_child_not_applicable():
    catalog = {
        "E_1": definition("E_1", EvidenceDataType.BINARY),
        "E_2": definition("E_2", EvidenceDataType.CATEGORICAL, "E_1"),
    }
    truth = {item.evidence_id: item for item in build_dense_truth([], catalog)}
    assert truth["E_1"].status == TruthStatus.ABSENT
    assert truth["E_2"].status == TruthStatus.NOT_APPLICABLE


def test_multi_choice_values_are_preserved():
    catalog = {"E_4": definition("E_4", EvidenceDataType.MULTI_CHOICE)}
    truth = build_dense_truth(["E_4_@_V_1", "E_4_@_V_2"], catalog)[0]
    assert truth.status == TruthStatus.VALUE
    assert truth.values == ["V_1", "V_2"]


def test_human_readable_categorical_yes_no_codes():
    item = definition("E_5", EvidenceDataType.CATEGORICAL)
    item = item.model_copy(
        update={"value_meanings": {"V_10": {"en": "N"}}}
    )
    response = EvidenceResponse(
        evidence_id="E_5",
        status=TruthStatus.VALUE,
        data_type=EvidenceDataType.CATEGORICAL,
        value="V_10",
    )
    assert human_readable_response(response, item) == "No"
