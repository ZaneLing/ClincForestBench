import json
from pathlib import Path

from analysis.reference_bayes import ReferenceNaiveBayes


def test_ddxplus_manifest_and_case_hashes(cases):
    manifest = json.loads(Path("data/manifests/ddxplus_manifest.json").read_text())
    assert len(manifest["cases"]) == 30
    assert len({row["pathology"] for row in manifest["cases"]}) >= 30
    ddx_cases = [
        bundle for bundle in cases.cases.values()
        if bundle.dataset.name == "DDXPlus"
    ]
    assert len(ddx_cases) == 30
    for bundle in ddx_cases:
        assert len(bundle.truth) == len(cases.evidence_catalog) == 223
        assert bundle.case_hash == bundle.compute_hash()
        assert bundle.dataset.split == "test"


def test_train_only_reference_bayes_is_normalized(cases):
    model = ReferenceNaiveBayes()
    case = cases.get(cases.case_ids()[0])
    posterior = model.posterior([case.initial_evidence])
    assert set(posterior) == set(cases.condition_catalog)
    assert abs(sum(posterior.values()) - 1.0) < 1e-9


def test_quality_exceptions_are_explicit_and_stable():
    report = json.loads(Path("data/manifests/raw_quality.json").read_text())
    # This is refreshed by the one-command pipeline; source drift must never be
    # silently accepted as a new baseline.
    if "quality_status" in report:
        assert report["quality_status"] == "PASSED_WITH_VERSIONED_UPSTREAM_EXCEPTIONS"
        assert report["exception_drift"] == []
