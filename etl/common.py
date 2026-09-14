from __future__ import annotations

import ast
import hashlib
import json
import math
from pathlib import Path
from typing import Any, Dict, Iterable, List

import yaml


ROOT = Path(__file__).resolve().parents[1]


def load_yaml(relative_path: str) -> Dict[str, Any]:
    with (ROOT / relative_path).open(encoding="utf-8") as handle:
        return yaml.safe_load(handle)


def ddx_config() -> Dict[str, Any]:
    return load_yaml("configs/ddxplus.yaml")


def selection_config() -> Dict[str, Any]:
    return load_yaml("configs/case_selection.yaml")


def path_from_root(value: str) -> Path:
    return ROOT / value


def load_json(path: Path) -> Any:
    with path.open(encoding="utf-8") as handle:
        return json.load(handle)


def dump_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        json.dump(payload, handle, ensure_ascii=False, indent=2, sort_keys=True)
        handle.write("\n")


def parse_python_literal(value: str) -> Any:
    return ast.literal_eval(value)


def entropy(probabilities: Iterable[float]) -> float:
    return -sum(p * math.log(p) for p in probabilities if p > 0)


def sha256_file(path: Path, chunk_size: int = 1024 * 1024) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(chunk_size):
            digest.update(chunk)
    return digest.hexdigest()


def source_files() -> Dict[str, List[str]]:
    config = ddx_config()
    return config["splits"]
