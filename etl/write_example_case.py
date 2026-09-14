from __future__ import annotations

from backend.app.domain.enums import TruthStatus
from backend.app.domain.evidence import human_readable_response
from backend.app.services.case_service import CaseService
from etl.common import dump_json, load_json, path_from_root


def main() -> None:
    manifest = load_json(path_from_root("data/manifests/mvp50_manifest.json"))
    case_id = manifest["cases"][0]["case_id"]
    cases = CaseService()
    bundle = cases.get(case_id)
    catalog = cases.evidence_catalog

    def readable(response):
        definition = catalog[response.evidence_id]
        return {
            "evidence_id": response.evidence_id,
            "question": definition.question_en,
            "clinical_domain": "ANTECEDENT"
            if definition.is_antecedent
            else "SYMPTOM",
            "semantic_role": definition.semantic_role,
            "answer": human_readable_response(response, definition),
            "raw_response": response.model_dump(mode="json"),
        }

    positive = [
        readable(response)
        for response in bundle.truth
        if response.status in {TruthStatus.PRESENT, TruthStatus.VALUE}
    ]
    output = path_from_root("examples") / f"{case_id}.readable.json"
    dump_json(
        output,
        {
            "about": "Human-readable projection of one immutable benchmark case. This file is for demonstration/research review and must not be sent to an active player.",
            "case_id": bundle.case_id,
            "case_hash": bundle.case_hash,
            "versions": bundle.dataset.model_dump(mode="json"),
            "demographics": bundle.demographics.model_dump(mode="json"),
            "initial_presentation": readable(bundle.initial_evidence),
            "positive_findings": positive,
            "ground_truth": bundle.oracle.model_dump(mode="json"),
            "case_quality": bundle.metadata.model_dump(mode="json"),
            "dense_truth": {
                "evidence_count": len(bundle.truth),
                "full_bundle_path": next(
                    row["path"]
                    for row in manifest["cases"]
                    if row["case_id"] == case_id
                ),
            },
        },
    )
    print(output)


if __name__ == "__main__":
    main()
