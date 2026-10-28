"""Read local source selections for the unordered case builder."""
from __future__ import annotations

from pathlib import Path

from etl.common import load_json, path_from_root
from .schema import SourceCase


class SourceCaseLoader:
    def __init__(self, root: Path | None = None):
        self.root = (root or path_from_root(".")).resolve()
        path = self.root / "data/processed/sources/manifest.json"
        self.document = load_json(path) if path.exists() else {"cases": []}
        self.entries = {row["case_id"]: row for row in self.document["cases"]}
        self.cache: dict[str, SourceCase] = {}

    def manifest(self):
        return self.document

    def get(self, case_id):
        if case_id not in self.cache:
            self.cache[case_id] = SourceCase.model_validate(
                load_json(self.root / self.entries[case_id]["path"])
            )
        return self.cache[case_id]
