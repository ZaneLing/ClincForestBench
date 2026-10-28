#!/usr/bin/env python3
"""Create one labelled demo through the same HTTP API used by the Arena.

Source answers are never synthesized. The simulation is excluded from the
ordinary doctor forest. Credentials are ephemeral and are not written to disk.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import secrets
from urllib.parse import urlparse

import httpx

from backend.app.services.case_service import CaseService
from backend.app.services.encounter_catalog import EncounterCatalog

ROOT = Path(__file__).resolve().parents[2]
CASE_ID = "DDX_TEST_0021752"
DECISIONS = [
    ("inquiry:source_2e8a35a1fe106d91", "support", "模拟演示：核对慢阻肺既往史，不代表真实医生决策。"),
    ("inquiry:source_138633790af95b31", "differentiate", "模拟演示：核对哮喘相关病史，不因一次否定答案排除疾病。"),
    ("inquiry:source_2b3d8c21dee4db84", "support", "模拟演示：继续收集呼吸系统症状。"),
    ("inquiry:source_1ed4d89b04584bc7", "severity", "模拟演示：记录病例已有的呼吸困难答案；严重程度仍需临床评估。"),
]
DIAGNOSIS = "模拟演示：疑似慢阻肺急性加重（仅4条问询，证据不足，非临床诊断）"


def seed_demo(base_url, output):
    if output.exists():
        raise FileExistsError("Refusing to create another demo when the report already exists")
    if not output.parent.is_dir():
        raise FileNotFoundError("Output parent directory does not exist")
    parsed = urlparse(base_url)
    if parsed.hostname not in {"localhost", "127.0.0.1"} or parsed.scheme != "http":
        raise ValueError("演示脚本仅允许访问本机 HTTP API")
    cases = CaseService(ROOT)
    catalog = EncounterCatalog(cases)
    for item_id, reason_id, _ in DECISIONS:
        assert catalog.bindings[CASE_ID].get(item_id), "Missing source answer"
        assert reason_id in {r["id"] for r in catalog.reasons(item_id)}
    with httpx.Client(base_url=base_url, timeout=30, trust_env=False) as client:
        before = client.get("/research/encounter-forest")
        before.raise_for_status()
        before = before.json()
        registration = client.post("/auth/register", json={
            "username": "simulation_demo_" + secrets.token_hex(5),
            "password": secrets.token_urlsafe(24),
        })
        registration.raise_for_status()
        client.headers["Authorization"] = "Bearer " + registration.json()["token"]
        try:
            response = client.post("/encounters", params={"lang": "zh-CN"}, json={
                "case_id": CASE_ID, "client_event_id": "demo-start", "is_simulation": True})
            response.raise_for_status()
            visit = response.json()
            route = "/encounters/" + visit["id"]
            for index, (item_id, reason_id, text) in enumerate(DECISIONS, 1):
                response = client.post(route + "/actions", params={"lang": "zh-CN"}, json={
                    "item_id": item_id, "reason_id": reason_id, "reason_text": text,
                    "hypothesis": "模拟假设：呼吸系统疾病待鉴别", "client_event_id": "decision-%d" % index})
                response.raise_for_status()
                visit = response.json()
                assert visit["status"] == "ACTIVE"
                assert visit["events"][-1]["result_status"] == "RECORDED"
                raw = client.get(route + "/export")
                raw.raise_for_status()
                assert raw.json()["events"][-1]["records"] == catalog.bindings[CASE_ID][item_id]
            response = client.post(route + "/diagnoses", params={"lang": "zh-CN"}, json={
                "diagnoses": [DIAGNOSIS], "client_event_id": "decision-5"})
            response.raise_for_status()
            response = client.post(route + "/finish", params={"lang": "zh-CN"}, json={"client_event_id": "complete"})
            response.raise_for_status()
            visit = client.get(route, params={"lang": "zh-CN"})
            visit.raise_for_status()
            visit = visit.json()
            assert visit["status"] == "COMPLETED" and visit["is_simulation"]
            assert [event["type"] for event in visit["events"]] == ["ACTION"] * 4 + ["DIAGNOSIS", "COMPLETE"]
            assert [event["sequence"] for event in visit["events"]] == list(range(1, 7))
            forest = client.get("/research/encounter-forest", params={"case_id": CASE_ID, "simulation": "true", "lang": "zh-CN"})
            forest.raise_for_status()
            forest = forest.json()
            assert any(row["encounter_id"] == visit["id"] for row in forest["demo_visits"])
            after = client.get("/research/encounter-forest")
            after.raise_for_status()
            assert after.json()["session_count"] == before["session_count"], "Simulation polluted doctor counts"
            assert after.json()["nodes"] == before["nodes"] and after.json()["edges"] == before["edges"]
            report = {"case_id": CASE_ID, "encounter_id": visit["id"], "is_simulation": True,
                      "decision_count": 5, "visit": visit, "forest": forest,
                      "doctor_forest_unchanged": True,
                      "forest_url": "http://127.0.0.1:3000/forest?case=" + CASE_ID + "&simulation=true"}
            if output.exists():
                raise FileExistsError("Refusing to overwrite an existing demo report")
            output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
            print(json.dumps({key: report[key] for key in ("case_id", "decision_count", "doctor_forest_unchanged", "forest_url")}, ensure_ascii=False))
        finally:
            client.post("/auth/logout")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    seed_demo(args.base_url, args.output)
