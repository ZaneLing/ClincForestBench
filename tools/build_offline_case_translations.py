"""Generate missing case translations entirely on the local machine.

Install the optional offline-translation dependencies and Argos en/zh, zh/en,
and vi/en packages first. No patient text is sent to a network service.
Machine translations are display overlays, not clinically adjudicated facts.
"""
from __future__ import annotations

import re
from concurrent.futures import ThreadPoolExecutor
from threading import Lock

import ctranslate2
from argostranslate import package

from backend.app.services.case_service import CaseService
from backend.app.services.encounter_catalog import EncounterCatalog
from backend.app.services.localization_service import translations_for
from tools.build_case_translations import (
    ENGLISH_OVERRIDES, EVIDENCE_COPY, HAS_EAST_ASIAN_SCRIPT, HAS_NON_ENGLISH_SCRIPT,
    PRIVATE_OUTPUT_DIR, PUBLIC_OUTPUT_DIR, collect_corpora,
    translation_is_complete, write_locale,
)


class OfflineTranslator:
    def __init__(self):
        self.packages = {(p.from_code, p.to_code): p for p in package.get_installed_packages()}
        self.models = {}
        self.lock = Lock()

    def translate(self, text, source, target):
        pair = (source, target)
        p = self.packages[pair]
        with self.lock:
            if pair not in self.models:
                self.models[pair] = ctranslate2.Translator(
                    str(p.package_path / "model"), device="cpu",
                    inter_threads=4, intra_threads=2,
                )
        # Split on sentence boundaries, then token windows, to prevent truncation.
        sentences = re.split(r"(?<=[.!?。！？])\s*|\n+", text)
        inputs = []
        for sentence in sentences:
            tokens = p.tokenizer.encode(sentence)
            inputs.extend(tokens[offset:offset + 180] for offset in range(0, len(tokens), 180))
        if not inputs:
            return text
        results = self.models[pair].translate_batch(
            inputs, beam_size=4, max_batch_size=16, max_decoding_length=400,
            length_penalty=0.2,
        )
        output = " ".join(p.tokenizer.decode(result.hypotheses[0]).strip()
                          for result in results)
        if p.target_prefix and output.startswith(p.target_prefix):
            output = output[len(p.target_prefix):].strip()
        return output


def main():
    translator = OfflineTranslator()
    needed = {("en", "zh"), ("zh", "en"), ("vi", "en")}
    if not needed <= translator.packages.keys():
        raise RuntimeError("Install the Argos en/zh, zh/en and vi/en model packages first")
    en, zh = dict(translations_for("en")), dict(translations_for("zh-CN"))
    en.update(ENGLISH_OVERRIDES)
    zh.update({translated: zh[source] for source, translated in en.items() if source in zh})
    catalog = EncounterCatalog(CaseService())
    clinical_labels = {item["label"]["en"] for item in catalog.items.values()}
    for item in catalog.items.values():
        if HAS_EAST_ASIAN_SCRIPT.search(item["label"]["zh-CN"]):
            zh[item["label"]["en"]] = item["label"]["zh-CN"]
        en.setdefault(item["label"]["zh-CN"], item["label"]["en"])
    zh.update(EVIDENCE_COPY)
    def complete(locale, text, translated):
        return translation_is_complete(locale, text, translated) and (
            locale != "zh-CN" or text not in clinical_labels
            or bool(HAS_EAST_ASIAN_SCRIPT.search(translated))
        )

    for scope, (all_text, non_english) in collect_corpora().items():
        directory = PUBLIC_OUTPUT_DIR if scope == "public" else PRIVATE_OUTPUT_DIR
        for locale, corpus, available in (("en", non_english, en), ("zh-CN", all_text, zh)):
            output = {text: available[text] for text in corpus
                      if complete(locale, text, available.get(text, ""))}

            def generate(text):
                translated = available.get(text, "")
                if not complete(locale, text, translated):
                    if locale == "en":
                        source = "zh" if HAS_EAST_ASIAN_SCRIPT.search(text) else "vi"
                        translated = translator.translate(text, source, "en")
                    elif complete(locale, text, text):
                        translated = text
                    else:
                        english = en.get(text, text)
                        if HAS_NON_ENGLISH_SCRIPT.search(english):
                            source = "zh" if HAS_EAST_ASIAN_SCRIPT.search(english) else "vi"
                            english = translator.translate(english, source, "en")
                        translated = translator.translate(english, "en", "zh")
                    if not complete(locale, text, translated):
                        raise ValueError(f"Offline translation incomplete: {scope}/{locale}")
                return text, translated

            pending = [text for text in corpus if text not in output]
            print(f"{scope}/{locale}: {len(pending)} missing translations", flush=True)
            with ThreadPoolExecutor(max_workers=4) as executor:
                for index, (text, translated) in enumerate(executor.map(generate, pending), 1):
                    available[text] = translated
                    output[text] = translated
                    if index % 100 == 0:
                        write_locale(directory, locale, output, "argos-local-display-translation")
                        print(f"{scope}/{locale}: {index}/{len(pending)} generated", flush=True)
            write_locale(directory, locale, output, "argos-local-display-translation")
            print(f"{scope}/{locale}: completed {len(corpus)} strings", flush=True)


if __name__ == "__main__":
    main()
