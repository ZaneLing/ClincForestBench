from backend.app.domain.case import CaseBundle
from backend.app.domain.evidence import EvidenceResponse


class DeterministicResponseEngine:
    def resolve(self, case: CaseBundle, evidence_id: str) -> EvidenceResponse:
        try:
            return case.truth_map()[evidence_id].model_copy(deep=True)
        except KeyError as exc:
            raise KeyError(f"Unknown evidence: {evidence_id}") from exc

