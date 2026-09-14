from __future__ import annotations

from pathlib import Path
from typing import Dict, List

from backend.app.domain.case import CaseBundle
from backend.app.domain.evidence import DATA_TYPE_MAP, EvidenceDefinition
from etl.common import ddx_config, load_json, path_from_root


class CaseService:
    """Load all tracks while retaining each case's native action vocabulary."""

    OPTIONAL_MANIFESTS = (
        "data/manifests/synthea_mvp50_manifest.json",
        "data/manifests/medagentbench_mvp30_manifest.json",
    )

    def __init__(self, root: Path | None = None) -> None:
        self.root = (root or path_from_root(".")).resolve()
        self.config = ddx_config()
        self._cases: Dict[str, CaseBundle] = {}
        self._evidences: Dict[str, EvidenceDefinition] = {}
        self._conditions: Dict[str, dict] = {}
        self._all_evidences: Dict[str, EvidenceDefinition] = {}
        self._all_conditions: Dict[str, dict] = {}
        self._catalog_by_case: Dict[str, Dict[str, EvidenceDefinition]] = {}
        self._outcomes_by_case: Dict[str, Dict[str, dict]] = {}
        self._manifest_documents: Dict[str, dict] = {}
        self.reload()

    def reload(self) -> None:
        raw_dir = path_from_root(self.config["paths"]["raw_dir"])
        manifest_path = (
            path_from_root(self.config["paths"]["manifests_dir"])
            / "mvp50_manifest.json"
        )
        if not manifest_path.exists():
            raise RuntimeError("Case bundles are missing; run `python -m etl.run_pipeline`")
        ddx_manifest = load_json(manifest_path)
        self._manifest_documents = {"mvp50_v1": ddx_manifest}
        self._cases = {
            row["case_id"]: CaseBundle.model_validate(
                load_json(self.root / row["path"])
            )
            for row in ddx_manifest["cases"]
        }

        raw_evidences = load_json(raw_dir / "release_evidences.json")
        mapping_version = self.config["dataset"]["semantic_mapping_version"]
        self._evidences = {}
        for evidence_id, item in raw_evidences.items():
            is_root = (
                item["code_question"] == evidence_id
                or item["code_question"] not in raw_evidences
            )
            is_antecedent = bool(item["is_antecedent"])
            self._evidences[evidence_id] = EvidenceDefinition(
                evidence_id=evidence_id,
                question_en=item["question_en"],
                is_antecedent=is_antecedent,
                data_type=DATA_TYPE_MAP[item["data_type"]],
                default_value=item["default_value"],
                possible_values=item.get("possible-values", []),
                value_meanings=item.get("value_meaning", {}),
                code_question=item["code_question"],
                parent_evidence_id=None if is_root else item["code_question"],
                is_root_question=is_root,
                semantic_role=(
                    "OTHER_ANTECEDENT"
                    if is_antecedent
                    else ("PRESENTING_SYMPTOM" if is_root else "SYMPTOM_ATTRIBUTE")
                ),
                exposure_tier=3 if is_antecedent else (2 if is_root else 1),
                mapping_version=mapping_version,
                clinical_domain="ANTECEDENT" if is_antecedent else "SYMPTOM",
                action_kind="ASK_QUESTION",
            )
        self._conditions = load_json(raw_dir / "release_conditions.json")
        self._all_evidences = dict(self._evidences)
        self._all_conditions = dict(self._conditions)
        self._catalog_by_case = {
            case_id: self._evidences for case_id in self._cases
        }
        self._outcomes_by_case = {
            case_id: self._conditions for case_id in self._cases
        }

        for relative_manifest in self.OPTIONAL_MANIFESTS:
            optional_path = self.root / relative_manifest
            if not optional_path.exists():
                continue
            document = load_json(optional_path)
            self._manifest_documents[document["manifest_version"]] = document
            for row in document["cases"]:
                bundle = CaseBundle.model_validate(load_json(self.root / row["path"]))
                if not bundle.action_space:
                    raise RuntimeError(f"{bundle.case_id} has no case-local action space")
                self._cases[bundle.case_id] = bundle
                catalog = {item.evidence_id: item for item in bundle.action_space}
                if set(catalog) != set(bundle.truth_map()):
                    raise RuntimeError(
                        f"{bundle.case_id} action/truth catalogs are not aligned"
                    )
                self._catalog_by_case[bundle.case_id] = catalog
                self._outcomes_by_case[bundle.case_id] = bundle.outcome_catalog
                for evidence_id, definition in catalog.items():
                    existing = self._all_evidences.get(evidence_id)
                    if existing and existing != definition:
                        raise RuntimeError(f"Conflicting evidence id: {evidence_id}")
                    self._all_evidences[evidence_id] = definition
                for outcome_id, outcome in bundle.outcome_catalog.items():
                    existing = self._all_conditions.get(outcome_id)
                    if existing and existing != outcome:
                        raise RuntimeError(f"Conflicting outcome id: {outcome_id}")
                    self._all_conditions[outcome_id] = outcome

    @property
    def cases(self) -> Dict[str, CaseBundle]:
        return self._cases

    @property
    def evidence_catalog(self) -> Dict[str, EvidenceDefinition]:
        """Legacy DDXPlus dictionary used by the evidence translation view."""
        return self._evidences

    @property
    def all_evidence_catalog(self) -> Dict[str, EvidenceDefinition]:
        return self._all_evidences

    @property
    def condition_catalog(self) -> Dict[str, dict]:
        """Legacy DDXPlus diagnosis dictionary."""
        return self._conditions

    @property
    def all_condition_catalog(self) -> Dict[str, dict]:
        return self._all_conditions

    @property
    def manifest_documents(self) -> Dict[str, dict]:
        return self._manifest_documents

    def case_ids(self) -> List[str]:
        return list(self._cases)

    def get(self, case_id: str) -> CaseBundle:
        try:
            return self._cases[case_id]
        except KeyError as exc:
            raise KeyError(f"Unknown case: {case_id}") from exc

    def catalog_for_case(self, case_id: str) -> Dict[str, EvidenceDefinition]:
        self.get(case_id)
        return self._catalog_by_case[case_id]

    def condition_catalog_for_case(self, case_id: str) -> Dict[str, dict]:
        self.get(case_id)
        return self._outcomes_by_case[case_id]

    def safe_condition_catalog(self, case_id: str | None = None) -> List[dict]:
        catalog = (
            self.condition_catalog_for_case(case_id)
            if case_id
            else self._conditions
        )
        return [
            {
                "condition_id": key,
                "name": value.get("condition_name", key),
                "kind": value.get("kind", "DIAGNOSIS"),
            }
            for key, value in sorted(catalog.items())
        ]

    def case_summaries(self) -> List[dict]:
        return [
            {
                "case_id": bundle.case_id,
                "dataset_name": bundle.dataset.name,
                "case_type": bundle.case_type,
                "generation_mode": bundle.generation_mode,
                "action_count": max(
                    0, len(self.catalog_for_case(bundle.case_id)) - 1
                ),
                "outcome_kind": bundle.oracle.outcome_kind,
                "terminology": (
                    "workflow outcome"
                    if bundle.case_type == "WORKFLOW_FOREST"
                    else "diagnosis"
                ),
                "runtime_status": bundle.initial_context.get(
                    "runtime_status", "READY"
                ),
            }
            for bundle in self._cases.values()
        ]

    def question_scope(
        self,
        condition_ids: List[str],
        initial_evidence_id: str,
        case_id: str | None = None,
    ) -> Dict[str, List[str]]:
        """Return safe relevance annotations without inspecting case truth."""

        if case_id and self.get(case_id).dataset.name != "DDXPlus":
            bundle = self.get(case_id)
            return {
                evidence_id: [
                    "Source encounter action"
                    if bundle.dataset.name == "Synthea"
                    else "Task-derived workflow"
                ]
                for evidence_id in self.catalog_for_case(case_id)
                if evidence_id != initial_evidence_id
            }

        suggested_by: Dict[str, List[str]] = {}
        if initial_evidence_id in self._evidences:
            suggested_by[initial_evidence_id] = ["Initial presentation"]
        for condition_id in condition_ids:
            condition = self._conditions.get(condition_id)
            if condition is None:
                continue
            for section in ("symptoms", "antecedents"):
                for evidence_id in condition.get(section, {}):
                    if evidence_id in self._evidences:
                        suggested_by.setdefault(evidence_id, []).append(
                            "Current differential"
                        )
        for evidence_id in list(suggested_by):
            parent = self._evidences[evidence_id].parent_evidence_id
            if parent:
                suggested_by.setdefault(parent, []).extend(suggested_by[evidence_id])
        for evidence_id, definition in self._evidences.items():
            if definition.parent_evidence_id in suggested_by:
                suggested_by.setdefault(evidence_id, []).extend(
                    suggested_by[definition.parent_evidence_id]
                )
        suggested_by.pop(initial_evidence_id, None)
        return {
            evidence_id: sorted(set(names))
            for evidence_id, names in suggested_by.items()
        }
