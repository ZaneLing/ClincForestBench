from __future__ import annotations

from pathlib import Path
from typing import Dict

from backend.app.domain.temporal import TemporalCase
from etl.common import load_json, path_from_root


class TemporalCaseService:
    """Loads local-only Temporal Forest v2 MVP artifacts.

    The generated manifest and case bundles contain restricted record-level
    derivatives, so this service is exposed only through research-key routes.
    """

    def __init__(self, root: Path | None = None) -> None:
        self.root = (root or path_from_root(".")).resolve()
        self.manifest_path = self.root / "data/processed/temporal/v2/manifest.json"
        self._manifest: dict = {}
        self._entries: Dict[str, dict] = {}
        self._cache: Dict[str, TemporalCase] = {}
        self.reload()

    def reload(self) -> None:
        self._cache = {}
        if not self.manifest_path.exists():
            self._manifest = {
                "schema_version": "clincforestbench.temporal-mvp-manifest.v2",
                "case_version": "2.0.0",
                "case_count": 0,
                "dataset_case_counts": {},
                "all_checks_pass": False,
                "status": "NOT_BUILT",
                "build_command": "make preprocess-temporal",
                "privacy": "RESTRICTED_LOCAL_ONLY",
                "cases": [],
            }
            self._entries = {}
            return
        self._manifest = load_json(self.manifest_path)
        self._manifest["status"] = "READY"
        self._entries = {item["case_id"]: item for item in self._manifest["cases"]}

    def manifest(self) -> dict:
        return self._manifest

    def get(self, case_id: str) -> TemporalCase:
        if case_id in self._cache:
            return self._cache[case_id]
        try:
            entry = self._entries[case_id]
        except KeyError as exc:
            raise KeyError(f"Unknown Temporal v2 case: {case_id}") from exc
        case = TemporalCase.model_validate(load_json(self.root / entry["path"]))
        self._cache[case_id] = case
        return case

    def detail(self, case_id: str) -> dict:
        case = self.get(case_id)
        return {
            "manifest_entry": self._entries[case_id],
            "case": case.model_dump(mode="json"),
        }
