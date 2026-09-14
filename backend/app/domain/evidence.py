from __future__ import annotations

from collections import defaultdict
from typing import Any, Dict, Iterable, List, Optional

from pydantic import BaseModel, Field

from .enums import EvidenceDataType, TruthStatus


DATA_TYPE_MAP = {
    "B": EvidenceDataType.BINARY,
    "C": EvidenceDataType.CATEGORICAL,
    "M": EvidenceDataType.MULTI_CHOICE,
    "binary": EvidenceDataType.BINARY,
    "categorical": EvidenceDataType.CATEGORICAL,
    "multi_choice": EvidenceDataType.MULTI_CHOICE,
}


class ParsedEvidenceToken(BaseModel):
    evidence_id: str
    value: Any = True


class EvidenceDefinition(BaseModel):
    evidence_id: str
    question_en: str
    is_antecedent: bool
    data_type: EvidenceDataType
    default_value: Any = None
    possible_values: List[Any] = Field(default_factory=list)
    value_meanings: Dict[str, Any] = Field(default_factory=dict)
    code_question: str
    parent_evidence_id: Optional[str] = None
    is_root_question: bool
    semantic_role: str
    exposure_tier: int
    mapping_version: str
    # Dataset-neutral action metadata.  DDXPlus definitions rely on the
    # defaults, while Synthea and MedAgentBench describe their native action
    # and resource semantics explicitly.
    clinical_domain: str = "SYMPTOM"
    action_kind: str = "ASK_QUESTION"
    resource_type: Optional[str] = None
    mutates_state: bool = False


class EvidenceResponse(BaseModel):
    evidence_id: str
    status: TruthStatus
    data_type: EvidenceDataType
    value: Any = None
    values: List[Any] = Field(default_factory=list)

    def canonical_payload(self) -> Dict[str, Any]:
        return {
            "evidence_id": self.evidence_id,
            "status": self.status.value,
            "data_type": self.data_type.value,
            "value": self.value,
            "values": sorted(self.values, key=str),
        }


def parse_evidence_token(token: str) -> ParsedEvidenceToken:
    """Parse a DDXPlus token, splitting only on the first `_@_`."""

    if not isinstance(token, str) or not token.strip():
        raise ValueError("Evidence token must be a non-empty string")
    token = token.strip()
    evidence_id, separator, value = token.partition("_@_")
    if not evidence_id:
        raise ValueError(f"Invalid evidence token: {token!r}")
    if separator and value == "":
        raise ValueError(f"Evidence token has an empty value: {token!r}")
    return ParsedEvidenceToken(
        evidence_id=evidence_id,
        value=value if separator else True,
    )


def group_evidence_tokens(tokens: Iterable[str]) -> Dict[str, List[Any]]:
    grouped: Dict[str, List[Any]] = defaultdict(list)
    for raw in tokens:
        parsed = parse_evidence_token(raw)
        if parsed.value not in grouped[parsed.evidence_id]:
            grouped[parsed.evidence_id].append(parsed.value)
    return dict(grouped)


def build_dense_truth(
    tokens: Iterable[str], catalog: Dict[str, EvidenceDefinition]
) -> List[EvidenceResponse]:
    """Expand one selected benchmark case to all catalog evidences."""

    grouped = group_evidence_tokens(tokens)
    responses: Dict[str, EvidenceResponse] = {}

    for evidence_id in sorted(catalog):
        definition = catalog[evidence_id]
        observed_values = grouped.get(evidence_id)
        if observed_values:
            if definition.data_type == EvidenceDataType.BINARY:
                response = EvidenceResponse(
                    evidence_id=evidence_id,
                    status=TruthStatus.PRESENT,
                    data_type=definition.data_type,
                    value=True,
                )
            elif definition.data_type == EvidenceDataType.MULTI_CHOICE:
                response = EvidenceResponse(
                    evidence_id=evidence_id,
                    status=TruthStatus.VALUE,
                    data_type=definition.data_type,
                    values=observed_values,
                )
            else:
                response = EvidenceResponse(
                    evidence_id=evidence_id,
                    status=TruthStatus.VALUE,
                    data_type=definition.data_type,
                    value=observed_values[0],
                )
        elif definition.data_type == EvidenceDataType.BINARY:
            response = EvidenceResponse(
                evidence_id=evidence_id,
                status=TruthStatus.ABSENT,
                data_type=definition.data_type,
                value=False,
            )
        else:
            response = EvidenceResponse(
                evidence_id=evidence_id,
                status=TruthStatus.DEFAULT,
                data_type=definition.data_type,
                value=definition.default_value,
            )
        responses[evidence_id] = response

    for evidence_id in sorted(catalog):
        definition = catalog[evidence_id]
        parent_id = definition.parent_evidence_id
        if not parent_id:
            continue
        parent = responses[parent_id]
        parent_active = parent.status in {TruthStatus.PRESENT, TruthStatus.VALUE}
        if not parent_active:
            responses[evidence_id] = EvidenceResponse(
                evidence_id=evidence_id,
                status=TruthStatus.NOT_APPLICABLE,
                data_type=definition.data_type,
            )

    return [responses[evidence_id] for evidence_id in sorted(responses)]


def human_readable_response(
    response: EvidenceResponse, definition: EvidenceDefinition
) -> str:
    def label(value: Any) -> str:
        meaning = definition.value_meanings.get(str(value), {})
        if isinstance(meaning, dict) and meaning.get("en"):
            readable = str(meaning["en"])
        else:
            readable = str(value)
        return {"N": "No", "Y": "Yes"}.get(readable, readable)

    if response.status == TruthStatus.PRESENT:
        return "Yes"
    if response.status == TruthStatus.ABSENT:
        return "No"
    if response.status == TruthStatus.NOT_APPLICABLE:
        return "Not applicable"
    if response.status == TruthStatus.DEFAULT:
        return label(response.value) if response.value is not None else "No recorded value"

    if response.values:
        return ", ".join(label(value) for value in response.values)
    return label(response.value)
