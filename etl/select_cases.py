from __future__ import annotations

from collections import defaultdict

import pyarrow as pa
import pyarrow.parquet as pq

from etl.common import ddx_config, dump_json, path_from_root, selection_config


def main() -> None:
    config = ddx_config()
    selection = selection_config()
    processed = path_from_root(config["paths"]["processed_dir"])
    table = pq.read_table(processed / "case_quality.parquet")
    candidates = [
        row
        for row in table.to_pylist()
        if row["evidence_count"] >= selection["min_evidence_count"]
        and row["differential_size"] >= selection["min_differential_size"]
        and (
            not selection["prefer_initial_symptom"]
            or row["initial_evidence_type"] == "SYMPTOM"
        )
    ]
    groups = defaultdict(list)
    for row in candidates:
        groups[row["pathology"]].append(row)
    for rows in groups.values():
        rows.sort(key=lambda row: (-row["branchability_score"], row["case_id"]))

    selected = []
    max_per = int(selection["max_cases_per_pathology"])
    for round_index in range(max_per):
        for pathology in sorted(groups):
            if len(groups[pathology]) > round_index:
                selected.append(groups[pathology][round_index])
                if len(selected) == int(selection["target_cases"]):
                    break
        if len(selected) == int(selection["target_cases"]):
            break
    if len(selected) < int(selection["target_cases"]):
        raise RuntimeError(
            f"Only selected {len(selected)} of {selection['target_cases']} cases"
        )

    manifest_dir = path_from_root(config["paths"]["manifests_dir"])
    manifest_dir.mkdir(parents=True, exist_ok=True)
    pq.write_table(
        pa.Table.from_pylist(selected),
        manifest_dir / "mvp50_case_selection.parquet",
        compression="zstd",
    )
    dump_json(
        manifest_dir / "mvp50_selection.json",
        {
            "manifest_name": selection["manifest_name"],
            "manifest_version": selection["manifest_version"],
            "source_split": selection["source_split"],
            "random_seed": selection["random_seed"],
            "selection_config": selection,
            "case_ids": [row["case_id"] for row in selected],
            "pathology_count": len({row["pathology"] for row in selected}),
        },
    )
    print(
        f"Selected {len(selected)} cases across "
        f"{len({row['pathology'] for row in selected})} pathologies"
    )


if __name__ == "__main__":
    main()
