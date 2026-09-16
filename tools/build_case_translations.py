#!/usr/bin/env python3
"""Build English and Simplified Chinese overlays for generated MVP cases."""

from __future__ import annotations

import argparse
import ast
from concurrent.futures import ThreadPoolExecutor, as_completed
import json
import os
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any, Iterable


ROOT = Path(__file__).resolve().parents[1]
PUBLIC_OUTPUT_DIR = ROOT / "locales" / "cases"
PRIVATE_OUTPUT_DIR = ROOT / "data" / "processed" / "locales" / "cases"
DEFAULT_MODEL = "inclusionai/ling-3.0-flash-vl:free"
DEFAULT_BASE_URL = "https://openrouter.ai/api/v1"
GOOGLE_MODEL = "google-translate-gtx"
GOOGLE_SEPARATOR = "\n[[[CFB_TRANSLATION_SPLIT]]]\n"

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

ID_LIKE = re.compile(
    r"^(?:[A-Z][A-Z0-9_-]{2,}|[A-Za-z]+://|(?:GET|POST|PUT|PATCH|DELETE)\s+[/\{].*|"
    r"[0-9a-f]{32,}|[A-Za-z]\w*(?:\.[A-Za-z]\w*)+|"
    r"[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}|"
    r"\d{4}-\d{2}-\d{2}(?:T.*)?|[\w./-]+\.(?:json|csv|parquet|png|jpg|jpeg|dcm))$",
    re.IGNORECASE,
)
HAS_WORD = re.compile(
    r"[A-Za-zÀ-ỹ\u3400-\u9fff\u3040-\u30ff"
    r"\uac00-\ud7af\u0400-\u04ff\u0600-\u06ff]{2}"
)
HAS_NON_ENGLISH_SCRIPT = re.compile(
    r"[ÀÁÂÃÈÉÊÌÍÒÓÔÕÙÚĂĐĨŨƠƯẠ-ỹ"
    r"\u3400-\u9fff\u3040-\u30ff\uac00-\ud7af\u0400-\u04ff\u0600-\u06ff]"
)
HAS_EAST_ASIAN_SCRIPT = re.compile(
    r"[\u3400-\u9fff\u3040-\u30ff\uac00-\ud7af]"
)
ENGLISH_WORD = re.compile(r"[A-Za-z][A-Za-z'-]*")
ENGLISH_OVERRIDES = {
    "Nạo VA": "Adenoidectomy",
}


def load_env(path: Path) -> None:
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip("\"'"))


def manifest_case_paths() -> list[Path]:
    paths: list[Path] = []
    manifests = [
        ROOT / "data/manifests/mvp50_manifest.json",
        ROOT / "data/manifests/synthea_mvp50_manifest.json",
        ROOT / "data/manifests/medagentbench_mvp30_manifest.json",
        ROOT / "data/processed/temporal/v2/manifest.json",
    ]
    for manifest_path in manifests:
        if not manifest_path.exists():
            continue
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        for item in manifest.get("cases", []):
            for key in ("path", "raw_case_path", "tree_path"):
                if item.get(key):
                    paths.append(ROOT / item[key])
    tree_manifests = [
        ROOT / "data/manifests/mvp50_tree_manifest.json",
        ROOT / "data/manifests/synthea_mvp50_tree_manifest.json",
        ROOT / "data/manifests/medagentbench_mvp30_tree_manifest.json",
    ]
    for manifest_path in tree_manifests:
        if not manifest_path.exists():
            continue
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        for item in manifest.get("cases", []):
            for key in ("raw_case_path", "tree_path"):
                if item.get(key):
                    paths.append(ROOT / item[key])
    return sorted(set(path for path in paths if path.exists()))


def is_translatable(key: str, value: str) -> bool:
    text = value.strip()
    if key in PROTECTED_KEYS or len(text) < 2:
        return False
    if ID_LIKE.fullmatch(text) or not HAS_WORD.search(text):
        return False
    return True


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


def collect_strings(
    value: Any, source_is_non_english: bool, key: str = ""
) -> Iterable[tuple[str, bool]]:
    if isinstance(value, dict):
        for child_key, child in value.items():
            yield from collect_strings(child, source_is_non_english, child_key)
    elif isinstance(value, list):
        for child in value:
            yield from collect_strings(child, source_is_non_english, key)
    elif isinstance(value, str):
        embedded = parse_embedded_collection(value)
        if embedded is not None:
            yield from collect_strings(embedded, source_is_non_english, key)
        elif is_translatable(key, value):
            yield value.strip(), source_is_non_english or bool(
                HAS_NON_ENGLISH_SCRIPT.search(value)
            )


def is_restricted_case(path: Path, document: dict[str, Any]) -> bool:
    if "temporal" not in path.parts:
        return False
    access_class = str(document.get("source", {}).get("access_class", ""))
    return not access_class.startswith("PUBLIC")


def collect_corpora() -> dict[str, tuple[list[str], list[str]]]:
    corpora = {
        "public": (set(), set()),
        "private": (set(), set()),
    }
    for path in manifest_case_paths():
        document = json.loads(path.read_text(encoding="utf-8"))
        scope = "private" if is_restricted_case(path, document) else "public"
        all_text, non_english_text = corpora[scope]
        source_name = str(document.get("source", {}).get("dataset_family", ""))
        source_is_non_english = "VIE" in source_name.upper()
        for text, needs_english in collect_strings(document, source_is_non_english):
            all_text.add(text)
            if needs_english:
                non_english_text.add(text)
    return {
        scope: (sorted(all_text), sorted(non_english_text))
        for scope, (all_text, non_english_text) in corpora.items()
    }


def collect_corpus() -> tuple[list[str], list[str]]:
    corpora = collect_corpora()
    all_text = set(corpora["public"][0]) | set(corpora["private"][0])
    non_english_text = set(corpora["public"][1]) | set(corpora["private"][1])
    return sorted(all_text), sorted(non_english_text)


def batches(values: list[str], max_items: int, max_chars: int) -> Iterable[list[str]]:
    batch: list[str] = []
    chars = 0
    for value in values:
        if batch and (len(batch) >= max_items or chars + len(value) > max_chars):
            yield batch
            batch, chars = [], 0
        batch.append(value)
        chars += len(value)
    if batch:
        yield batch


def translate_batch(
    values: list[str],
    target: str,
    api_key: str,
    base_url: str,
    model: str,
) -> dict[str, str]:
    indexed = {str(index): value for index, value in enumerate(values)}
    script_requirement = (
        " English output must not retain Chinese, Japanese, or Korean characters."
        if target == "English"
        else (
            " Translate all English and Vietnamese prose, including prose embedded "
            "inside otherwise Chinese text, into Simplified Chinese."
        )
    )
    prompt = (
        f"Translate every JSON value into {target}. The content is medical benchmark data. "
        "Preserve clinical meaning, negation, uncertainty, dosages, units, abbreviations, and line breaks. "
        f"{script_requirement} "
        "Do not translate identifiers or alter JSON keys. Return only one valid JSON object with exactly "
        "the same keys. Do not add markdown.\n\n"
        + json.dumps(indexed, ensure_ascii=False)
    )
    body = json.dumps(
        {
            "model": model,
            "temperature": 0,
            "messages": [
                {
                    "role": "system",
                    "content": "You are a precise medical translator. Output valid JSON only.",
                },
                {"role": "user", "content": prompt},
            ],
        }
    ).encode("utf-8")
    request = urllib.request.Request(
        f"{base_url.rstrip('/')}/chat/completions",
        data=body,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=180) as response:
        payload = json.loads(response.read().decode("utf-8"))
    content = payload["choices"][0]["message"]["content"].strip()
    if content.startswith("```"):
        content = re.sub(r"^```(?:json)?\s*|\s*```$", "", content)
    try:
        translated = json.loads(content, strict=False)
    except json.JSONDecodeError:
        translated = ast.literal_eval(content)
    if not isinstance(translated, dict):
        raise ValueError("Translation response is not a JSON object")
    if set(translated) != set(indexed):
        raise ValueError("Translation response keys do not match the request")
    return {
        indexed[key]: normalize_translation(indexed[key], str(translated[key]))
        for key in indexed
    }


def translate_single_value(
    value: str,
    target: str,
    api_key: str,
    base_url: str,
    model: str,
) -> str:
    prompt = (
        f"Translate the following medical benchmark text into {target}. "
        "Preserve clinical meaning, negation, uncertainty, dosages, units, "
        "abbreviations, and line breaks. Return only the translated text, "
        "without commentary or markdown.\n\n"
        f"{value}"
    )
    body = json.dumps(
        {
            "model": model,
            "temperature": 0,
            "messages": [
                {
                    "role": "system",
                    "content": "You are a precise medical translator.",
                },
                {"role": "user", "content": prompt},
            ],
        }
    ).encode("utf-8")
    request = urllib.request.Request(
        f"{base_url.rstrip('/')}/chat/completions",
        data=body,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=180) as response:
        payload = json.loads(response.read().decode("utf-8"))
    return normalize_translation(
        value, payload["choices"][0]["message"]["content"]
    )


def translate_google_batch(
    values: list[str], locale: str
) -> dict[str, str]:
    if any(GOOGLE_SEPARATOR in value for value in values):
        raise ValueError("Google translation separator appears in source text")
    body = urllib.parse.urlencode(
        {
            "client": "gtx",
            "sl": "auto",
            "tl": locale,
            "dt": "t",
            "q": GOOGLE_SEPARATOR.join(values),
        }
    ).encode("utf-8")
    request = urllib.request.Request(
        "https://translate.googleapis.com/translate_a/single",
        data=body,
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=60) as response:
        payload = json.loads(response.read().decode("utf-8"))
    translated_text = "".join(
        str(item[0]) for item in payload[0] if item and item[0]
    )
    translated = translated_text.split(GOOGLE_SEPARATOR)
    if len(translated) != len(values):
        raise ValueError("Google translation response lost batch separators")
    return {
        source: normalize_translation(source, target)
        for source, target in zip(values, translated)
    }


def normalize_translation(source: str, translated: str) -> str:
    value = translated.strip()
    if (
        len(value) >= 2
        and value[0] == value[-1]
        and value[0] in {"\"", "'"}
        and not (source.startswith(value[0]) and source.endswith(value[0]))
    ):
        value = value[1:-1].strip()
    return value


def translation_is_complete(
    locale: str, source: str, translated: str
) -> bool:
    if not translated:
        return False
    if locale == "en":
        return not HAS_EAST_ASIAN_SCRIPT.search(translated)
    if source != translated:
        return True
    words = ENGLISH_WORD.findall(source)
    has_english_prose = len(words) >= 4 and sum(
        len(word) for word in words if word.islower()
    ) >= 6
    has_vietnamese_prose = (
        bool(HAS_NON_ENGLISH_SCRIPT.search(source))
        and not HAS_EAST_ASIAN_SCRIPT.search(source)
        and len(source) >= 20
    )
    return not (has_english_prose or has_vietnamese_prose)


def generated_translation_is_valid(locale: str, translated: str) -> bool:
    return bool(translated) and (
        locale != "en" or not HAS_EAST_ASIAN_SCRIPT.search(translated)
    )


def load_existing(output_dir: Path, locale: str) -> dict[str, str]:
    path = output_dir / f"{locale}.json"
    if not path.exists():
        return {}
    translations = json.loads(path.read_text(encoding="utf-8")).get(
        "translations", {}
    )
    return {
        source: normalize_translation(source, translated)
        for source, translated in translations.items()
    }


def build_locale(
    output_dir: Path,
    locale: str,
    target: str,
    corpus: list[str],
    api_key: str,
    base_url: str,
    model: str,
    max_items: int,
    max_chars: int,
    workers: int,
    provider: str = "openrouter",
) -> None:
    corpus_set = set(corpus)
    translations = {
        source: translated
        for source, translated in load_existing(output_dir, locale).items()
        if source in corpus_set
        and translation_is_complete(locale, source, translated)
    }
    if locale == "en":
        translations.update(
            {
                source: translated
                for source, translated in ENGLISH_OVERRIDES.items()
                if source in corpus_set
            }
        )
    pending = [value for value in corpus if value not in translations]
    pending_batches = list(batches(pending, max_items, max_chars))

    def run_batch(batch: list[str]) -> dict[str, str]:
        format_attempts = 2 if len(batch) > 1 else 4
        rate_limit_attempts = 6
        last_error: Exception | None = None
        for attempt in range(rate_limit_attempts):
            try:
                translated = (
                    translate_google_batch(batch, locale)
                    if provider == "google"
                    else translate_batch(
                        batch, target, api_key, base_url, model
                    )
                )
                if locale == "en":
                    translated.update(
                        {
                            source: value
                            for source, value in ENGLISH_OVERRIDES.items()
                            if source in translated
                        }
                    )
                if any(
                    not generated_translation_is_valid(locale, value)
                    for value in translated.values()
                ):
                    raise ValueError(
                        f"{locale} translation retained source-language script"
                    )
                return translated
            except (
                urllib.error.URLError,
                TimeoutError,
                ValueError,
                KeyError,
                json.JSONDecodeError,
                SyntaxError,
            ) as exc:
                last_error = exc
                rate_limited = (
                    isinstance(exc, urllib.error.HTTPError)
                    and exc.code == 429
                )
                allowed_attempts = (
                    rate_limit_attempts if rate_limited else format_attempts
                )
                if attempt + 1 >= allowed_attempts:
                    break
                delay = (
                    min(60, 15 * (2 ** attempt))
                    if rate_limited
                    else 2 ** attempt
                )
                print(
                    f"{locale}: retrying batch after {type(exc).__name__} "
                    f"(attempt {attempt + 2}/{allowed_attempts}, "
                    f"wait {delay}s)",
                    file=sys.stderr,
                    flush=True,
                )
                time.sleep(delay)
        if (
            isinstance(last_error, urllib.error.HTTPError)
            and last_error.code == 429
        ):
            raise RuntimeError(
                f"{locale} translation model remained rate limited"
            ) from last_error
        if len(batch) > 1:
            midpoint = len(batch) // 2
            print(
                f"{locale}: splitting failed batch of {len(batch)} items",
                file=sys.stderr,
                flush=True,
            )
            translated = run_batch(batch[:midpoint])
            translated.update(run_batch(batch[midpoint:]))
            return translated
        if provider == "google":
            raise RuntimeError(
                f"{locale} Google translation batch failed"
            ) from last_error
        try:
            translated = translate_single_value(
                batch[0], target, api_key, base_url, model
            )
            if locale == "en" and batch[0] in ENGLISH_OVERRIDES:
                translated = ENGLISH_OVERRIDES[batch[0]]
            if generated_translation_is_valid(locale, translated):
                return {batch[0]: translated}
        except (
            urllib.error.URLError,
            TimeoutError,
            ValueError,
            KeyError,
            json.JSONDecodeError,
            SyntaxError,
        ) as exc:
            last_error = exc
        raise RuntimeError(f"{locale} translation batch failed") from last_error

    completed = 0
    executor = ThreadPoolExecutor(max_workers=max(1, workers))
    try:
        futures = {
            executor.submit(run_batch, batch): batch for batch in pending_batches
        }
        for future in as_completed(futures):
            translations.update(future.result())
            completed += 1
            print(
                f"{locale}: {completed}/{len(pending_batches)} batches",
                flush=True,
            )
            write_locale(output_dir, locale, translations, model)
    except Exception:
        for future in futures:
            future.cancel()
        executor.shutdown(wait=True, cancel_futures=True)
        raise
    else:
        executor.shutdown(wait=True)
    write_locale(output_dir, locale, translations, model)


def write_locale(
    output_dir: Path,
    locale: str,
    translations: dict[str, str],
    model: str,
) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / f"{locale}.json"
    models = {model}
    if output_path.exists():
        existing = json.loads(output_path.read_text(encoding="utf-8"))
        models.update(existing.get("models", []))
        if existing.get("model") not in {None, "mixed"}:
            models.add(existing["model"])
    payload = {
        "schema_version": "clincforestbench.case-translations.v1",
        "locale": locale,
        "model": model if len(models) == 1 else "mixed",
        "models": sorted(models),
        "translations": dict(sorted(translations.items())),
    }
    temporary_path = output_path.with_suffix(".json.tmp")
    temporary_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    temporary_path.replace(output_path)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--env-file", type=Path, default=ROOT / "tools/api_smoke/.env")
    parser.add_argument("--base-url", default=DEFAULT_BASE_URL)
    parser.add_argument("--model", default=DEFAULT_MODEL)
    parser.add_argument("--api-key-env", default="OPENROUTER_API_KEY")
    parser.add_argument(
        "--provider", choices=("openrouter", "google"), default="openrouter"
    )
    parser.add_argument(
        "--scope", choices=("all", "public", "private"), default="all"
    )
    parser.add_argument("--max-items", type=int, default=40)
    parser.add_argument("--max-chars", type=int, default=4000)
    parser.add_argument("--workers", type=int, default=5)
    args = parser.parse_args()
    load_env(args.env_file)
    api_key = os.environ.get(args.api_key_env, "")
    if args.provider == "openrouter" and not api_key:
        raise SystemExit(f"{args.api_key_env} is required")
    if args.provider == "google" and args.scope != "public":
        raise SystemExit("Google translation is restricted to public cases")
    model = GOOGLE_MODEL if args.provider == "google" else args.model
    max_items = min(args.max_items, 5) if args.provider == "google" else args.max_items

    for scope, (all_text, non_english_text) in collect_corpora().items():
        if args.scope != "all" and scope != args.scope:
            continue
        output_dir = (
            PUBLIC_OUTPUT_DIR if scope == "public" else PRIVATE_OUTPUT_DIR
        )
        print(
            f"{scope}: {len(all_text)} strings; "
            f"{len(non_english_text)} need translation to English.",
            flush=True,
        )
        english_complete = set(non_english_text) <= set(
            load_existing(output_dir, "en")
        )
        if args.provider != "google" or not english_complete:
            build_locale(
                output_dir,
                "en",
                "English",
                non_english_text,
                api_key,
                args.base_url,
                model,
                max_items,
                args.max_chars,
                args.workers,
                args.provider,
            )
        build_locale(
            output_dir,
            "zh-CN",
            "Simplified Chinese",
            all_text,
            api_key,
            args.base_url,
            model,
            max_items,
            args.max_chars,
            args.workers,
            args.provider,
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
