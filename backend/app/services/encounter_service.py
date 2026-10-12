"""Persistent visit/action/reason/diagnosis trajectories with atomic transitions."""
from __future__ import annotations

import hashlib
import json
import sqlite3
import threading
from datetime import datetime, timezone
from uuid import uuid4

from backend.app.services.encounter_catalog import VERSION, bilingual, localized_records
from backend.app.services.localization_service import localize_payload


def now():
    return datetime.now(timezone.utc).isoformat()


class EncounterService:
    def __init__(self, catalog, database):
        self.catalog = catalog
        self.lock = threading.RLock()
        self.connection = sqlite3.connect(str(database), check_same_thread=False)
        self.connection.execute("CREATE TABLE IF NOT EXISTS encounters (id TEXT PRIMARY KEY, owner TEXT NOT NULL, document TEXT NOT NULL)")
        self.connection.commit()

    def save(self, document):
        self.connection.execute("INSERT OR REPLACE INTO encounters VALUES (?, ?, ?)",
                                (document["id"], document["owner"], json.dumps(document, ensure_ascii=False)))

    def get(self, encounter_id, owner):
        with self.lock:
            row = self.connection.execute("SELECT document FROM encounters WHERE id=? AND owner=?", (encounter_id, owner)).fetchone()
        if not row:
            raise KeyError("Encounter not found")
        return json.loads(row[0])

    def create(self, case_id, owner, client_event_id):
        if case_id not in self.catalog.visits:
            raise KeyError("Unknown case")
        encounter_id = hashlib.sha256(f"{owner}\0{client_event_id}".encode()).hexdigest()[:32]
        with self.lock, self.connection:
            try:
                existing = self.get(encounter_id, owner)
                if existing["case_id"] != case_id:
                    raise ValueError("Event ID was already used for another case")
                return existing
            except KeyError:
                pass
            document = {"id": encounter_id, "owner": owner, "case_id": case_id,
                        "catalog_version": VERSION, "status": "ACTIVE", "created_at": now(),
                        "visit": self.catalog.visits[case_id], "events": [], "diagnoses": [],
                        "prescription": None, "completed_at": None}
            self.save(document)
        return document

    def mutate(self, encounter_id, owner, event_id, command, apply):
        # BEGIN IMMEDIATE also serializes writers from independent API workers.
        with self.lock:
            try:
                self.connection.execute("BEGIN IMMEDIATE")
                doc = self.get(encounter_id, owner)
                for event in doc["events"]:
                    if event["client_event_id"] == event_id:
                        if event["command"] != command:
                            raise ValueError("Event ID was already used with a different request")
                        self.connection.commit()
                        return doc
                if doc["status"] != "ACTIVE":
                    raise ValueError("Encounter is already closed")
                event = apply(doc)
                event.update({"id": str(uuid4()), "sequence": len(doc["events"]) + 1,
                              "timestamp": now(), "client_event_id": event_id, "command": command})
                doc["events"].append(event)
                self.save(doc)
                self.connection.commit()
                return doc
            except Exception:
                self.connection.rollback()
                raise

    def act(self, encounter_id, owner, request):
        item = self.catalog.items.get(request.item_id)
        if not item:
            raise KeyError("Unknown catalog item")
        reasons = self.catalog.reasons(request.item_id)
        if request.reason_id not in {r["id"] for r in reasons}:
            raise ValueError("Choose one of the offered reasons")
        if request.reason_id == "other" and not request.reason_text.strip():
            raise ValueError("Describe the other reason")

        def apply(doc):
            if any(e.get("item", {}).get("id") == request.item_id for e in doc["events"]):
                raise ValueError("This item has already been selected")
            records = self.catalog.bindings[doc["case_id"]].get(request.item_id, [])
            if not records:
                doc.update(status="TERMINATED_MISSING_RESULT", completed_at=now())
            return {"type": "ACTION", "item": item, "reason_options": reasons,
                    "reason_generator_version": "clinical-reason-profiles.v1",
                    "reason_id": request.reason_id, "reason_text": request.reason_text.strip(),
                    "hypothesis": request.hypothesis.strip(),
                    "diagnoses_before": list(doc["diagnoses"]),
                    "result_status": "RECORDED" if records else "NOT_RECORDED",
                    "records": records}
        return self.mutate(encounter_id, owner, request.client_event_id,
                           request.model_dump(mode="json"), apply)

    def diagnose(self, encounter_id, owner, request):
        diagnoses = [v.strip() for v in request.diagnoses if v.strip()]
        if not diagnoses:
            raise ValueError("Enter or select at least one diagnosis")
        def apply(doc):
            doc["diagnoses"] = diagnoses
            codes = {}
            for condition_id, value in self.catalog.cases.all_condition_catalog.items():
                if value.get("kind", "DIAGNOSIS") == "DIAGNOSIS":
                    for label in bilingual(value.get("condition_name", condition_id)).values():
                        codes[label.casefold()] = condition_id
            doc["coded_diagnoses"] = [{"text": text, "condition_id": codes.get(text.casefold()),
                                       "entry_type": "CATALOG_MATCH" if text.casefold() in codes else "FREE_TEXT"}
                                      for text in diagnoses]
            return {"type": "DIAGNOSIS", "diagnoses": diagnoses, "coded_diagnoses": doc["coded_diagnoses"]}
        return self.mutate(encounter_id, owner, request.client_event_id,
                           request.model_dump(mode="json"), apply)

    def prescribe(self, encounter_id, owner, request):
        def apply(doc):
            if not doc["diagnoses"]:
                raise ValueError("Record a diagnosis before prescribing")
            if not self.catalog.treatments[doc["case_id"]]:
                raise ValueError("This source case has no treatment stage")
            if not request.text.strip():
                raise ValueError("Enter a prescription or treatment plan")
            doc["prescription"] = request.text.strip()
            return {"type": "PRESCRIPTION", "text": doc["prescription"], "diagnoses": doc["diagnoses"]}
        return self.mutate(encounter_id, owner, request.client_event_id,
                           request.model_dump(mode="json"), apply)

    def finish(self, encounter_id, owner, request):
        def apply(doc):
            if not doc["diagnoses"]:
                raise ValueError("Record a diagnosis before completing the visit")
            doc.update(status="COMPLETED", completed_at=now())
            return {"type": "COMPLETE"}
        return self.mutate(encounter_id, owner, request.client_event_id,
                           request.model_dump(mode="json"), apply)

    def view(self, doc, locale):
        # Localize presentation/results only, never doctor-authored observations
        # or bilingual contracts. Export keeps the original alongside this view.
        result = dict(doc)
        result["visit"] = localize_payload(doc["visit"], locale)
        result["events"] = []
        for event in doc["events"]:
            visible = {k: v for k, v in event.items() if k != "command"}
            if "records" in event:
                visible["records"] = localized_records(event["records"], locale)
            result["events"].append(visible)
        result["prescription_available"] = bool(doc["diagnoses"] and self.catalog.treatments[doc["case_id"]])
        return result

    def history(self, owner):
        with self.lock:
            rows = self.connection.execute("SELECT document FROM encounters WHERE owner=? ORDER BY rowid DESC", (owner,)).fetchall()
        return [{k: doc[k] for k in ("id", "case_id", "status", "created_at", "completed_at", "diagnoses")}
                for doc in (json.loads(r[0]) for r in rows)]

    def forest(self):
        with self.lock:
            documents = [json.loads(row[0]) for row in self.connection.execute("SELECT document FROM encounters")]
        nodes, edges = {}, {}
        reasons, terminations, missing_inquiries = {}, {}, {}
        for doc in documents:
            parent = doc["case_id"]
            nodes.setdefault(parent, {"id": parent, "label": parent, "count": 0})["count"] += 1
            for event in doc["events"]:
                label = (f"{event['item']['id']} / {event['reason_id']} / {event['result_status']}"
                         if event["type"] == "ACTION" else event["type"] +
                         (": " + " | ".join(event["diagnoses"]) if event["type"] == "DIAGNOSIS" else ""))
                if event["type"] == "ACTION":
                    reasons[event["reason_id"]] = reasons.get(event["reason_id"], 0) + 1
                    if event["result_status"] == "NOT_RECORDED" and event["item"]["kind"] == "operation":
                        terminations[event["item"]["id"]] = terminations.get(event["item"]["id"], 0) + 1
                    if event["result_status"] == "NOT_RECORDED" and event["item"]["kind"] == "inquiry":
                        missing_inquiries[event["item"]["id"]] = missing_inquiries.get(event["item"]["id"], 0) + 1
                child = hashlib.sha256(f"{parent}/{label}".encode()).hexdigest()[:24]
                nodes.setdefault(child, {"id": child, "label": label, "count": 0,
                                         "item": event.get("item"), "event_type": event["type"],
                                         "reason_id": event.get("reason_id"), "result_status": event.get("result_status")})["count"] += 1
                edges.setdefault((parent, child), {"source": parent, "target": child, "count": 0})["count"] += 1
                parent = child
        return {"nodes": list(nodes.values()), "edges": list(edges.values()), "session_count": len(documents),
                "reason_counts": reasons, "missing_examination_counts": terminations,
                "missing_inquiry_counts": missing_inquiries}
