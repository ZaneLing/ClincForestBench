from __future__ import annotations

import hashlib
import json
from typing import Any, Dict, List

from pydantic import BaseModel, Field

from .evidence import EvidenceDefinition, EvidenceResponse


class DatasetIdentity(BaseModel):
    name: str = "DDXPlus"
    split: str
    dataset_version: str
    pipeline_version: str
    semantic_mapping_version: str
    case_manifest_version: str


class Demographics(BaseModel):
    age: int
    sex: str


class OracleDifferentialItem(BaseModel):
    condition: str
    probability: float


class OracleReference(BaseModel):
    pathology: str
    severity: int
    differential: List[OracleDifferentialItem] = Field(default_factory=list)
    outcome_kind: str = "DIAGNOSIS"
    display_name: str = ""


class CaseMetadata(BaseModel):
    evidence_count: int = 0
    symptom_count: int = 0
    antecedent_count: int = 0
    independent_root_count: int = 0
    child_attribute_count: int = 0
    nonbinary_count: int = 0
    differential_size: int = 0
    differential_entropy: float = 0.0
    top1_probability: float = 0.0
    top1_top2_margin: float = 0.0
    branchability_score: float = 0.0


class CaseBundle(BaseModel):
    case_id: str
    dataset: DatasetIdentity
    demographics: Demographics
    initial_evidence: EvidenceResponse
    truth: List[EvidenceResponse]
    oracle: OracleReference
    metadata: CaseMetadata
    case_type: str = "DIAGNOSTIC_QUESTIONING"
    generation_mode: str = "SOURCE_ASSERTED"
    initial_context: Dict[str, Any] = Field(default_factory=dict)
    action_space: List[EvidenceDefinition] = Field(default_factory=list)
    outcome_catalog: Dict[str, Dict[str, Any]] = Field(default_factory=dict)
    original_trajectory: List[Dict[str, Any]] = Field(default_factory=list)
    fidelity_note: str = ""
    case_hash: str = ""

    def truth_map(self) -> Dict[str, EvidenceResponse]:
        return {item.evidence_id: item for item in self.truth}

    def compute_hash(self) -> str:
        payload: Dict[str, Any] = self.model_dump(mode="json")
        payload.pop("case_hash", None)
        # Preserve the immutable v1 DDXPlus hashes.  These fields were added
        # for Guidance2 tracks and are absent from the original bundle schema.
        if self.dataset.name == "DDXPlus" and not self.action_space:
            for key in (
                "case_type",
                "generation_mode",
                "initial_context",
                "action_space",
                "outcome_catalog",
                "original_trajectory",
                "fidelity_note",
            ):
                payload.pop(key, None)
            payload["oracle"].pop("outcome_kind", None)
            payload["oracle"].pop("display_name", None)
        canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()

    def with_hash(self) -> "CaseBundle":
        return self.model_copy(update={"case_hash": self.compute_hash()})

    def public_initial_state(self) -> Dict[str, Any]:
        return {
            "case_id": self.case_id,
            "dataset_name": self.dataset.name,
            "case_type": self.case_type,
            "generation_mode": self.generation_mode,
            "demographics": self.demographics.model_dump(mode="json"),
            "initial_evidence": self.initial_evidence.model_dump(mode="json"),
            "initial_context": self.initial_context,
            "case_hash": self.case_hash,
        }
