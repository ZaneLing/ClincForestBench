"""Write a local source mapping + bilingual coverage report without network calls."""
from __future__ import annotations

import json
from pathlib import Path

from backend.app.services.case_service import CaseService
from backend.app.services.encounter_catalog import EncounterCatalog
from backend.app.services.localization_service import translations_for
from backend.app.services.temporal_case_service import TemporalCaseService
from tools.build_case_translations import collect_strings, translation_is_complete


def audit(catalog):
    report = catalog.report()
    gaps = []
    for cid, visit in catalog.visits.items():
        content = [visit, [r["result"] for rows in catalog.bindings[cid].values() for r in rows]]
        for text, needs_english in collect_strings(content, False):
            for locale in ("en", "zh-CN"):
                if locale == "en" and not needs_english:
                    continue
                translated = translations_for(locale).get(text, text)
                if not translation_is_complete(locale, text, translated):
                    gaps.append({"case_id": cid, "locale": locale, "source": text})
    for item in catalog.items.values():
        for locale in ("en", "zh-CN"):
            text = item["label"][locale]
            if not text or (locale == "zh-CN" and not any("\u4e00" <= c <= "\u9fff" for c in text)):
                gaps.append({"item_id": item["id"], "locale": locale})
    report["localization"] = {"gaps": gaps, "gap_count": len(gaps),
                              "method": "dictionary coverage and script checks; not clinical translation adjudication"}
    return report


def main():
    catalog = EncounterCatalog(CaseService(), TemporalCaseService())
    report = audit(catalog)
    path = Path("data/analysis_runs/encounter_mapping_audit.json")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"case_count": report["case_count"], "libraries": report["library_counts"],
                      "translation_gaps": report["localization"]["gap_count"], "report": str(path)}, ensure_ascii=False))
    return 1 if report["localization"]["gap_count"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
