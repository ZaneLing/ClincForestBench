"""Global bilingual libraries and deterministic source-to-action mappings.

Catalog identity never depends on the selected case. Labels containing narrative
findings are never promoted into the shared menu. Native source IDs are retained
only in the private mapping, not exposed as availability hints.
"""
from __future__ import annotations

import csv
import hashlib
import json
import re
from collections import Counter
from pathlib import Path

from backend.app.domain.evidence import human_readable_response
from backend.app.services.localization_service import localize_payload


VERSION = "encounter-libraries.v1"


def localized_records(records, locale):
    """One result presentation contract for the arena and read-only inspector."""
    return [{**r, "result": localize_payload(r["result"], locale),
             "source_label": localize_payload(r.get("source_label", ""), locale)} for r in records]


def bilingual(text: str) -> dict:
    return {locale: localize_payload(text, locale) for locale in ("en", "zh-CN")}


def normalized(text: str) -> str:
    return re.sub(r"\s+", " ", text.strip()).casefold()


class EncounterCatalog:
    def __init__(self, cases, temporal):
        self.cases, self.temporal = cases, temporal
        self.items: dict[str, dict] = {}
        self.aliases: dict[tuple[str, str], str] = {}
        self.bindings: dict[str, dict[str, list[dict]]] = {}
        self.visits: dict[str, dict] = {}
        self.treatments: dict[str, list[dict]] = {}
        self.audit: dict[str, list[dict]] = {}
        self.reason_profiles = json.loads((Path(__file__).resolve().parents[3] / "configs/clinical_reasons.json").read_text())
        for kind, name in (("operation", "operations"), ("inquiry", "inquiries")):
            with (Path(__file__).resolve().parents[3] / f"configs/clinical_{name}.tsv").open() as stream:
                for row in csv.DictReader(stream, delimiter="\t"):
                    self.add(f"{kind}:{row['id']}", kind, row["category"],
                             {"en": row["en"], "zh-CN": row["zh"]},
                             [row["en"], row["zh"], *row["aliases"].split("|")])
        with (Path(__file__).resolve().parents[3] / "configs/clinical_aliases.tsv").open() as stream:
            for row in csv.DictReader(stream, delimiter="\t"):
                kind = row["target"].split(":")[0]
                self.aliases[(kind, normalized(row["alias"]))] = row["target"]
        for case in cases.cases.values():
            self.classic(case)
        for entry in temporal.manifest()["cases"]:
            self.temporal_case(temporal.get(entry["case_id"]))
        for case_id, visit in self.visits.items():
            if visit["presentation"]:
                self.bind(case_id, "inquiry:CHIEF", "visit.presentation", visit["presentation"], origin="VISIT_PRESENTATION")
        self.expand_components()

    def add(self, item_id, kind, category, label, aliases):
        self.items[item_id] = {"id": item_id, "kind": kind, "category": category,
                               "label": label, "catalog_version": VERSION}
        for alias in aliases:
            if alias:
                self.aliases.setdefault((kind, normalized(alias)), item_id)
        return item_id

    def resolve(self, kind, label, source_id="", category="Source catalog", native=True):
        for alias in (source_id, label):
            item_id = self.aliases.get((kind, normalized(alias)))
            if item_id:
                return item_id
        if not native:
            return None
        item_id = f"{kind}:source_{hashlib.sha256(label.encode()).hexdigest()[:16]}"
        if item_id not in self.items:
            self.add(item_id, kind, category, bilingual(label), [label])
        return item_id

    def bind(self, case_id, item_id, source_id, result, **metadata):
        metadata.setdefault("mapping_method", "GENERIC_RECORDED_CONTEXT" if item_id in {
            "inquiry:RECORDS", "operation:RECORDED_LAB", "operation:RECORDED_IMAGING", "operation:RECORDED_EXAM"
        } else "SOURCE_NATIVE" if ":source_" in item_id else "EXPLICIT_CATALOG_BINDING")
        self.bindings[case_id].setdefault(item_id, []).append(
            {"source_id": source_id, "result": result, **metadata})
        self.audit[case_id].append({"source_id": source_id, "item_id": item_id,
                                   "disposition": "MAPPED", **metadata})

    def prepare(self, case_id):
        self.bindings[case_id], self.treatments[case_id], self.audit[case_id] = {}, [], []

    def classic(self, case):
        cid = case.case_id
        self.prepare(cid)
        definitions = self.cases.catalog_for_case(cid)
        initial_definition = definitions[case.initial_evidence.evidence_id]
        if case.dataset.name == "Synthea":
            # encounter_reason and the old initial evidence contain the answer.
            presentation = case.initial_context.get("encounter_description", "")
        else:
            presentation = human_readable_response(case.initial_evidence, initial_definition)
            if case.dataset.name == "DDXPlus":
                presentation = {"question": initial_definition.question_en, "answer": presentation}
        self.visits[cid] = {"case_id": cid, "dataset": case.dataset.name,
                            "demographics": case.demographics.model_dump(),
                            "presentation": presentation,
                            "track_type": case.case_type, "source_hash": case.case_hash}
        if case.initial_context.get("presentation_vitals"):
            self.bind(cid, "operation:VITALS", "initial_context.presentation_vitals",
                      [{"name": v["DESCRIPTION"], "value": v["VALUE"], "unit": v.get("UNITS", "")}
                       for v in case.initial_context["presentation_vitals"]], origin="SOURCE_TRIAGE")
        for response in case.truth:
            definition = definitions[response.evidence_id]
            if response.evidence_id == case.initial_evidence.evidence_id:
                self.audit[cid].append({"source_id": response.evidence_id, "disposition": "VISIT"})
                continue
            treatment = bool(re.search(r"chemotherapy|radiation therapy|rehabilitation|extraction of|prostatectomy|immunization|augmentation of labor|childbirth", definition.question_en, re.I))
            if definition.clinical_domain == "MEDICATION" or definition.mutates_state or treatment:
                self.treatments[cid].append({"source_id": response.evidence_id,
                                           "label": definition.question_en,
                                           "result": human_readable_response(response, definition)})
                self.audit[cid].append({"source_id": response.evidence_id, "disposition": "TREATMENT"})
                continue
            if case.dataset.name == "MedAgentBench":
                # FHIR request templates are not clinical results.
                self.bind(cid, "inquiry:WORKFLOW", response.evidence_id,
                          human_readable_response(response, definition),
                          origin="OFFLINE_WORKFLOW_INSTRUCTION")
                continue
            kind = "inquiry" if definition.action_kind == "ASK_QUESTION" else "operation"
            label = re.sub(r"^Review (?:recorded )?(?:observation|procedure):\s*", "", definition.question_en)
            if ("inquiry", normalized(label)) in self.aliases:
                kind = "inquiry"
            category = ("History" if definition.is_antecedent else "Symptoms") if kind == "inquiry" else "Records"
            item_id = self.resolve(kind, label, definition.evidence_id, category=category)
            self.bind(cid, item_id, response.evidence_id,
                      {"answer": human_readable_response(response, definition),
                       "status": response.status.value},
                      origin="SOURCE_EVIDENCE", source_label=label)
        # A panel returns only its actually recorded components, never inferred values.
        panels = {
            "CBC": ["Hemoglobin [Mass/volume] in Blood", "Hematocrit [Volume Fraction] of Blood by Automated count", "Hematocrit [Volume Fraction] of Blood", "Leukocytes [#/volume] in Blood by Automated count", "Platelets [#/volume] in Blood by Automated count", "Erythrocytes [#/volume] in Blood by Automated count", "WBC Auto (Bld) [#/Vol]", "RBC Auto (Bld) [#/Vol]"],
            "LIPIDS": ["LIPIDS", "Total Cholesterol", "Low Density Lipoprotein Cholesterol", "High Density Lipoprotein Cholesterol", "Triglycerides"],
            "ELECTROLYTES": ["SODIUM", "POTASSIUM", "CHLORIDE", "BICARBONATE"],
            "RENAL": ["CREATININE", "BUN"],
            "LIVER": ["ALT", "AST", "ALP", "BILIRUBIN", "ALBUMIN"],
            "BMP": ["SODIUM", "POTASSIUM", "CHLORIDE", "BICARBONATE", "CREATININE", "BUN", "GLUCOSE", "CALCIUM"],
        }
        for panel, members in panels.items():
            results = []
            for member in members:
                key = f"operation:{member}"
                key = key if key in self.items else self.aliases.get(("operation", normalized(member)))
                results.extend(self.bindings[cid].get(key, []))
            if results and f"operation:{panel}" not in self.bindings[cid]:
                self.bindings[cid][f"operation:{panel}"] = [dict(r, partial_panel=True) for r in results]

    def expand_components(self):
        for case_id, bindings in self.bindings.items():
            additions = {}
            for rows in list(bindings.values()):
                for row in rows:
                    if not isinstance(row["result"], dict):
                        continue
                    for index, component in enumerate(row["result"].get("components", [])):
                        label = component.get("label", component.get("name", ""))
                        item_id = self.resolve("operation", label, native=False)
                        if item_id and item_id not in bindings and item_id not in additions:
                            additions[item_id] = [{**row, "result": component, "source_label": label,
                                                   "component_index": index, "origin": "SOURCE_PANEL_COMPONENT"}]
            bindings.update(additions)

    def temporal_case(self, case):
        cid = case.case_id
        self.prepare(cid)
        initial = case.initial_state
        self.visits[cid] = {
            "case_id": cid, "dataset": case.source.get("dataset_family", case.source.get("dataset", "Temporal")),
            "demographics": {k: initial[k] for k in ("age", "age_range", "sex", "gender", "occupation") if k in initial},
            "presentation": initial.get("chief_complaint", initial.get("presentation", "")),
            "track_type": case.task_type,
            "source_hash": hashlib.sha256(case.model_dump_json().encode()).hexdigest(),
        }
        if initial.get("presentation_hpi"):
            self.bind(cid, "inquiry:RECORDS", "initial_state.presentation_hpi", initial["presentation_hpi"], origin="SOURCE_PRESENTATION_HISTORY")
        vitals = initial.get("triage_vitals") or initial.get("first_15_min_vitals")
        if vitals:
            self.bind(cid, "operation:VITALS", "initial_state.vitals", vitals, origin="SOURCE_TRIAGE")
        for context in case.queryable_context:
            source_id = context.get("action_id", "")
            if source_id and context.get("items"):
                kind = "operation" if source_id == "REVIEW_PHYSICAL_EXAM" else "inquiry"
                item_id = self.resolve(kind, "", source_id, native=False)
                if item_id:
                    self.bind(cid, item_id, source_id, context["items"], origin="SOURCE_CONTEXT")
        for event in case.timeline_events:
            source_id = event.event_id
            modality = event.clinical_concept.modality
            if modality == "INTERVENTION":
                self.treatments[cid].append({"source_id": source_id, "label": event.clinical_concept.display,
                                           "result": event.result})
                self.audit[cid].append({"source_id": source_id, "disposition": "TREATMENT"})
                continue
            if not event.arena.arena_eligible or modality == "DIAGNOSIS":
                self.audit[cid].append({"source_id": source_id, "disposition": "REFERENCE_ONLY"})
                continue
            kind = "inquiry" if modality in {"HISTORY", "RECORD"} else "operation"
            label = event.clinical_concept.display
            # Never turn a report excerpt or an outcome into a menu label.
            narrative = event.event_type in {"NARRATIVE_CLINICAL_EVENT", "LONGITUDINAL_HEALTH_EVENT"} or label.startswith("Review imaging finding")
            item_id = self.resolve(kind, label, event.action_id or "", native=False)
            if not item_id:
                if narrative or (modality == "IMAGING" and not re.search(r"(?:CT|MRI|X-ray|ultrasound|radiograph|超声|影像)", label, re.I)):
                    fallback = {"IMAGING": "operation:RECORDED_IMAGING", "LAB": "operation:RECORDED_LAB",
                                "EXAM": "operation:RECORDED_EXAM"}.get(modality, "inquiry:RECORDS")
                    item_id = fallback
                else:
                    item_id = self.resolve(kind, label, category={"LAB": "Laboratory", "ECG": "Cardiology",
                                          "IMAGING": "Imaging", "EXAM": "Physical examination"}.get(modality, "Source catalog"))
            # First source result for a repeat order; subsequent results remain
            # traceable in the audit, not silently pooled across treatment times.
            if item_id in self.bindings[cid] and kind == "operation" and not item_id.startswith("operation:RECORDED"):
                self.audit[cid].append({"source_id": source_id, "item_id": item_id, "disposition": "LATER_RESULT"})
                continue
            result = event.result.get("patient_answer", event.result)
            self.bind(cid, item_id, source_id, result, origin="SOURCE_EVENT",
                      source_label=label, source_time=event.time.model_dump(mode="json"))

    def reasons(self, item_id):
        item = self.items[item_id]
        en, zh = item["label"]["en"], item["label"]["zh-CN"]
        profile = self.reason_profiles.get(item_id, self.reason_profiles.get(item["category"]))
        if profile:
            return [{"id": reason_id, "label": {"en": row[0], "zh-CN": row[1]}}
                    for reason_id, row in zip(("support", "differentiate", "urgent", "severity"), profile)] + [
                        {"id": "other", "label": {"en": "Another reason (please describe)", "zh-CN": "其他原因（请填写）"}}]
        return [
            {"id": "support", "label": {"en": f"Use “{en}” to look for evidence supporting my current suspected diagnosis.", "zh-CN": f"通过“{zh}”寻找支持当前怀疑诊断的证据。"}},
            {"id": "differentiate", "label": {"en": f"Use “{en}” to distinguish between competing diagnoses.", "zh-CN": f"通过“{zh}”区分几个可能的诊断。"}},
            {"id": "urgent", "label": {"en": f"Use “{en}” to assess a serious or urgent possibility.", "zh-CN": f"通过“{zh}”评估严重或紧急情况的可能性。"}},
            {"id": "severity", "label": {"en": f"Use “{en}” to assess severity, complications or treatment suitability.", "zh-CN": f"通过“{zh}”评估严重程度、并发症或治疗适用性。"}},
            {"id": "other", "label": {"en": "Another reason (please describe)", "zh-CN": "其他原因（请填写）"}},
        ]

    def report(self):
        return {"catalog_version": VERSION, "case_count": len(self.visits),
                "library_counts": dict(Counter(i["kind"] for i in self.items.values())),
                "cases": [{"case_id": cid, "mapped_actions": len(self.bindings[cid]),
                           "dispositions": dict(Counter(a["disposition"] for a in self.audit[cid])),
                           "sources": self.audit[cid]} for cid in self.visits]}

    def inspection(self, case_id, locale):
        visit = self.visits[case_id]
        bindings = self.bindings[case_id]
        return {
            "catalog_version": VERSION,
            "visit": localize_payload(visit, locale),
            "bindings": {item_id: localized_records(records, locale)
                         for item_id, records in bindings.items()},
            "counts": {kind: {"total": sum(i["kind"] == kind for i in self.items.values()),
                              "recorded": sum(self.items[key]["kind"] == kind and bool(rows)
                                              for key, rows in bindings.items())}
                       for kind in ("inquiry", "operation")},
            "treatments": [{**r, "label": localize_payload(r["label"], locale),
                            "result": localize_payload(r["result"], locale)}
                           for r in self.treatments[case_id]],
            "audit": self.audit[case_id],
        }
