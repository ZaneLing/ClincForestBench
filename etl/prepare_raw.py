from __future__ import annotations

import os
from pathlib import Path

from etl.common import ddx_config, dump_json, path_from_root, sha256_file


def main() -> None:
    config = ddx_config()
    source_dir = path_from_root(config["paths"]["source_dir"])
    raw_dir = path_from_root(config["paths"]["raw_dir"])
    raw_dir.mkdir(parents=True, exist_ok=True)

    names = [
        name
        for split_names in config["splits"].values()
        for name in split_names
    ] + ["release_evidences.json", "release_conditions.json"]

    manifest = {
        "dataset_version": config["dataset"]["dataset_version"],
        "immutable_source": True,
        "files": [],
    }
    for name in names:
        source = (source_dir / name).resolve()
        if not source.is_file():
            raise FileNotFoundError(f"Missing source file: {source}")
        target = raw_dir / name
        if target.is_symlink():
            if target.resolve() != source:
                raise RuntimeError(f"Raw link points at wrong source: {target}")
        elif target.exists():
            raise RuntimeError(f"Refusing to overwrite raw file: {target}")
        else:
            target.symlink_to(os.path.relpath(source, raw_dir))
        item = {"name": name, "bytes": source.stat().st_size}
        if source.suffix == ".json":
            item["sha256"] = sha256_file(source)
        manifest["files"].append(item)

    dump_json(path_from_root("data/manifests/raw_ddxplus_v1.json"), manifest)
    print(f"Prepared immutable raw links in {raw_dir}")


if __name__ == "__main__":
    main()
