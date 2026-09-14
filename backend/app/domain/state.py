from __future__ import annotations

import hashlib
import json
from typing import Any, Dict, Iterable, List

from pydantic import BaseModel, Field

from .evidence import EvidenceResponse


def compute_state_hash(
    case_id: str,
    responses: Iterable[EvidenceResponse],
    created_resource_ids: Iterable[str] = (),
) -> str:
    created = sorted(created_resource_ids)
    payload = {
        "case_id": case_id,
        "revealed": sorted(
            (response.canonical_payload() for response in responses),
            key=lambda item: item["evidence_id"],
        ),
    }
    # Empty created-resource state is omitted for backward compatibility with
    # existing DDXPlus session hashes.  Once a live FHIR write creates a
    # resource, its id becomes part of the canonical state identity.
    if created:
        payload["created_resource_ids"] = created
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


class ObservationState(BaseModel):
    case_id: str
    age: int
    sex: str
    dataset_name: str = "DDXPlus"
    case_type: str = "DIAGNOSTIC_QUESTIONING"
    generation_mode: str = "SOURCE_ASSERTED"
    initial_context: Dict[str, Any] = Field(default_factory=dict)
    initial_evidence_id: str
    initial_evidence_question: str = ""
    initial_evidence_answer: str = ""
    revealed: Dict[str, EvidenceResponse] = Field(default_factory=dict)
    question_count: int = 0
    created_resource_ids: List[str] = Field(default_factory=list)
    state_hash: str = ""

    def refreshed(self) -> "ObservationState":
        return self.model_copy(
            update={
                "state_hash": compute_state_hash(
                    self.case_id,
                    self.revealed.values(),
                    self.created_resource_ids,
                )
            }
        )

    def public_payload(self) -> Dict[str, object]:
        return {
            "case_id": self.case_id,
            "dataset_name": self.dataset_name,
            "case_type": self.case_type,
            "generation_mode": self.generation_mode,
            "demographics": {"age": self.age, "sex": self.sex},
            "initial_context": self.initial_context,
            "initial_evidence_id": self.initial_evidence_id,
            "initial_evidence_question": self.initial_evidence_question,
            "initial_evidence_answer": self.initial_evidence_answer,
            "revealed_evidences": [
                self.revealed[key].model_dump(mode="json")
                for key in sorted(self.revealed)
            ],
            "question_count": self.question_count,
            "created_resource_ids": self.created_resource_ids,
            "state_hash": self.state_hash,
        }
