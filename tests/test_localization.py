import json

from fastapi.testclient import TestClient

from backend.app.main import create_app
from backend.app.services.localization_service import (
    PROTECTED_KEYS,
    localization_status,
    localize_payload,
    normalize_locale,
    source_by_translation,
    source_text,
    translations_for,
)
from backend.app.services.temporal_case_service import TemporalCaseService
from tools.build_case_translations import (
    PUBLIC_OUTPUT_DIR,
    collect_corpora,
    collect_corpus,
)


def test_locale_aliases_are_normalized():
    assert normalize_locale(None) == "en"
    assert normalize_locale("en-US") == "en"
    assert normalize_locale("zh") == "zh-CN"
    assert normalize_locale("zh_CN") == "zh-CN"


def test_localization_preserves_contract_fields(monkeypatch):
    monkeypatch.setattr(
        "backend.app.services.localization_service.translations_for",
        lambda locale: {
            "Chest pain": "胸痛",
            "LAB": "化验",
            "ORDER_TEST": "检查",
            "Pulmonary embolism": "肺栓塞",
        },
    )
    payload = {
        "label": "Chest pain",
        "modality": "LAB",
        "action_id": "ORDER_TEST",
        "condition_id": "Pulmonary embolism",
        "embedded": '[{"label": "Chest pain", "condition_id": "Pulmonary embolism"}]',
        "nested": [{"display": "Chest pain"}],
    }

    localized = localize_payload(payload, "zh-CN")

    assert localized["label"] == "胸痛"
    assert localized["nested"][0]["display"] == "胸痛"
    assert localized["modality"] == "LAB"
    assert localized["action_id"] == "ORDER_TEST"
    assert localized["condition_id"] == "Pulmonary embolism"
    assert json.loads(localized["embedded"]) == [
        {"label": "胸痛", "condition_id": "Pulmonary embolism"}
    ]
    assert payload["label"] == "Chest pain"
    assert {"modality", "action_id", "condition_id"} <= PROTECTED_KEYS


def test_localized_diagnosis_can_be_restored_before_scoring(monkeypatch):
    monkeypatch.setattr(
        "backend.app.services.localization_service.translations_for",
        lambda locale: {"Pulmonary embolism": "肺栓塞"},
    )
    source_by_translation.cache_clear()
    assert source_text("肺栓塞", "zh-CN") == "Pulmonary embolism"
    assert source_text("Custom diagnosis", "zh-CN") == "Custom diagnosis"


def test_committed_case_locales_are_available():
    translations_for.cache_clear()
    status = localization_status()
    assert status["default_locale"] == "en"
    assert status["locales"]["en"]["translation_count"] > 0
    assert status["locales"]["zh-CN"]["translation_count"] > 0


def test_translation_overlays_cover_every_mvp_case_string():
    all_text, non_english_text = collect_corpus()
    assert set(non_english_text) <= set(translations_for("en"))
    assert set(all_text) <= set(translations_for("zh-CN"))


def test_non_vietnamese_chinese_source_is_translated_to_english():
    source = "2025-06-26血常规+CRP检查显示C反应蛋白32 mg/L"
    translated = translations_for("en")[source]
    assert translated != source
    assert not any("\u3400" <= character <= "\u9fff" for character in translated)
    assert translations_for("en")["Nạo VA"] == "Adenoidectomy"
    assert not any(
        "\u3400" <= character <= "\ud7af"
        for value in translations_for("en").values()
        for character in value
    )


def test_public_translation_files_exclude_private_only_case_text():
    corpora = collect_corpora()
    public_text, public_non_english = map(set, corpora["public"])
    private_text, private_non_english = map(set, corpora["private"])
    allowed_sources = {
        "en": public_non_english,
        "zh-CN": public_text,
    }
    private_only_sources = {
        "en": private_non_english - public_non_english,
        "zh-CN": private_text - public_text,
    }

    for locale in ("en", "zh-CN"):
        document = json.loads(
            (PUBLIC_OUTPUT_DIR / f"{locale}.json").read_text(encoding="utf-8")
        )
        sources = set(document["translations"])
        assert sources <= allowed_sources[locale]
        assert sources.isdisjoint(private_only_sources[locale])


def test_classic_case_catalog_switches_with_locale(cases):
    client = TestClient(create_app(cases))
    case_id = cases.case_ids()[0]
    english = client.get(f"/cases/{case_id}/catalog?lang=en").json()
    chinese = client.get(f"/cases/{case_id}/catalog?lang=zh-CN").json()

    assert [item["condition_id"] for item in english["conditions"]] == [
        item["condition_id"] for item in chinese["conditions"]
    ]
    assert english["conditions"] != chinese["conditions"]
    assert any(
        "\u3400" <= character <= "\u9fff"
        for character in json.dumps(chinese["conditions"], ensure_ascii=False)
    )


def test_vietnamese_temporal_case_switches_with_locale():
    service = TemporalCaseService()
    case_id = "CFB_MEDDIES_48A3B083_374B_4076_ADA4_5A0D9EBC6F76"
    english = service.detail(case_id, "en")["case"]["initial_state"][
        "chief_complaint"
    ]
    chinese = service.detail(case_id, "zh-CN")["case"]["initial_state"][
        "chief_complaint"
    ]
    assert english.startswith("Lately I often have stomach pain")
    assert any("\u4e00" <= character <= "\u9fff" for character in chinese)
