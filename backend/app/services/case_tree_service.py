from __future__ import annotations

from collections import Counter
from pathlib import Path

from etl.common import load_json, path_from_root


class CaseTreeService:
    """Read immutable raw/tree audit artifacts across all Arena tracks."""

    MANIFESTS = (
        ("data/manifests/mvp50_tree_manifest.json", "DDXPlus", "DIAGNOSTIC_QUESTIONING", "SOURCE_ASSERTED"),
        ("data/manifests/synthea_mvp50_tree_manifest.json", "Synthea", "DIAGNOSTIC_EVIDENCE_ACQUISITION", "NATURAL_CSV_EXPORT"),
        ("data/manifests/medagentbench_mvp30_tree_manifest.json", "MedAgentBench", "WORKFLOW_FOREST", "OFFLINE_TASK_REPLAY"),
    )

    def __init__(self, root: Path | None = None) -> None:
        self.root = (root or path_from_root(".")).resolve()
        entries = []
        source_manifests = []
        for relative, dataset_name, case_type, generation_mode in self.MANIFESTS:
            manifest_path = self.root / relative
            if not manifest_path.exists():
                if dataset_name == "DDXPlus":
                    raise RuntimeError(
                        "Case-tree artifacts are missing; run `python -m etl.build_case_trees`"
                    )
                continue
            manifest = load_json(manifest_path)
            source_manifests.append(
                {
                    "dataset_name": dataset_name,
                    "manifest_version": manifest["manifest_version"],
                    "case_count": manifest["case_count"],
                    "path": relative,
                }
            )
            entries.extend(
                {
                    **item,
                    "dataset_name": item.get("dataset_name", dataset_name),
                    "case_type": item.get("case_type", case_type),
                    "generation_mode": item.get(
                        "generation_mode", generation_mode
                    ),
                }
                for item in manifest["cases"]
            )
        category_counts = Counter(item["disease_category"] for item in entries)
        self._manifest = {
            "manifest_name": "clincforestbench_multitrack_mvp",
            "manifest_version": "multitrack_mvp_v1",
            "tree_schema_version": "mixed_versioned_schemas",
            "taxonomy_version": "dataset_native_v1",
            "case_count": len(entries),
            "pathology_count": len({item["pathology"] for item in entries}),
            "taxonomy_condition_count": len(
                {item["pathology"] for item in entries}
            ),
            "category_count": len(category_counts),
            "category_case_counts": dict(sorted(category_counts.items())),
            "dataset_case_counts": dict(
                Counter(item["dataset_name"] for item in entries)
            ),
            "all_checks_pass": all(item["all_checks_pass"] for item in entries),
            "source_manifests": source_manifests,
            "cases": entries,
        }
        self._entries = {item["case_id"]: item for item in entries}

    def manifest(self) -> dict:
        return self._manifest

    def get(self, case_id: str) -> dict:
        try:
            entry = self._entries[case_id]
        except KeyError as exc:
            raise KeyError(f"Unknown case tree: {case_id}") from exc
        return {
            "manifest_entry": entry,
            "raw_case": load_json(self.root / entry["raw_case_path"]),
            "processed_tree": load_json(self.root / entry["tree_path"]),
        }
