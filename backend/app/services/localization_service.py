from __future__ import annotations

import ast
from functools import lru_cache
import json
from pathlib import Path
from typing import Any

from etl.common import load_json, path_from_root


SUPPORTED_LOCALES = {"en", "zh-CN"}
DEFAULT_LOCALE = "en"

# These values are contracts used by the API or frontend, not display copy.
PROTECTED_KEYS = {
    "access_class",
    "action",
    "action_id",
    "anchor_type",
    "availability_semantics",
    "canonical_id",
    "case_hash",
    "case_id",
    "case_type",
    "case_version",
    "code",
    "condition_id",
    "dataset",
    "dataset_version",
    "documented_time",
    "edge_id",
    "edge_type",
    "end_time",
    "event_id",
    "event_type",
    "generation_mode",
    "hidden_evidence_pool",
    "lane",
    "leakage_risk",
    "manifest_version",
    "media_asset",
    "modality",
    "node_id",
    "node_type",
    "order_time",
    "outcome_kind",
    "path",
    "privacy",
    "reference_quality",
    "result_origin",
    "result_status",
    "root_id",
    "schema_version",
    "source_code",
    "source_event_id",
    "source_node",
    "source_path",
    "source_row_id",
    "source_table",
    "source_system",
    "split",
    "start_time",
    "status",
    "strategy",
    "target_node",
    "task_type",
    "temporal_confidence",
    "temporal_replay_mode",
    "time_mode",
    "time_semantics",
    "timezone_policy",
    "unobserved_action_result",
}


def normalize_locale(locale: str | None) -> str:
    if not locale:
        return DEFAULT_LOCALE
    normalized = locale.strip().replace("_", "-").lower()
    if normalized.startswith("zh"):
        return "zh-CN"
    return "en"


@lru_cache(maxsize=2)
def translations_for(locale: str) -> dict[str, str]:
    normalized = normalize_locale(locale)
    translations: dict[str, str] = {}
    paths = (
        path_from_root(f"locales/cases/{normalized}.json"),
        path_from_root(f"data/processed/locales/cases/{normalized}.json"),
    )
    for path in paths:
        if not path.exists():
            continue
        document = load_json(path)
        translations.update(
            {
                str(source): str(target)
                for source, target in document.get("translations", {}).items()
            }
        )
    return translations


@lru_cache(maxsize=2)
def source_by_translation(locale: str) -> dict[str, str]:
    return {
        translated: source
        for source, translated in translations_for(normalize_locale(locale)).items()
    }


def source_text(value: str, locale: str | None) -> str:
    return source_by_translation(normalize_locale(locale)).get(value.strip(), value)


def parse_embedded_collection(value: str) -> Any | None:
    text = value.strip()
    if not text or text[0] not in "[{":
        return None
    for loader in (json.loads, ast.literal_eval):
        try:
            parsed = loader(text)
        except (ValueError, SyntaxError, json.JSONDecodeError):
            continue
        if isinstance(parsed, (dict, list)):
            return parsed
    return None


def localize_payload(payload: Any, locale: str | None, key: str = "") -> Any:
    """Return a localized copy while preserving machine-readable contracts."""

    translations = translations_for(normalize_locale(locale))
    if isinstance(payload, dict):
        return {
            child_key: localize_payload(child, locale, child_key)
            for child_key, child in payload.items()
        }
    if isinstance(payload, list):
        return [localize_payload(child, locale, key) for child in payload]
    if isinstance(payload, str) and key not in PROTECTED_KEYS:
        embedded = parse_embedded_collection(payload)
        if embedded is not None:
            localized = localize_payload(embedded, locale, key)
            if localized != embedded:
                return json.dumps(localized, ensure_ascii=False)
        return translations.get(payload.strip(), payload)
    return payload


def localization_status(root: Path | None = None) -> dict[str, Any]:
    base = (root or path_from_root(".")).resolve()
    locales: dict[str, Any] = {}
    for locale in sorted(SUPPORTED_LOCALES):
        public_path = base / f"locales/cases/{locale}.json"
        private_path = base / f"data/processed/locales/cases/{locale}.json"
        public = load_json(public_path) if public_path.exists() else {}
        private = load_json(private_path) if private_path.exists() else {}
        locales[locale] = {
            "ready": public_path.exists(),
            "public_translation_count": len(public.get("translations", {})),
            "private_translation_count": len(private.get("translations", {})),
            "translation_count": len(translations_for(locale)),
        }
    return {"default_locale": DEFAULT_LOCALE, "locales": locales}
