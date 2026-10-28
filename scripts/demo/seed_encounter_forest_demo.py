#!/usr/bin/env python3
"""Retain the first demo and add three separate paths through the real Arena API."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import secrets

import httpx

from backend.app.services.case_service import CaseService
from backend.app.services.encounter_catalog import EncounterCatalog
from scripts.demo.seed_encounter_demo import CASE_ID, ROOT

COPD = "inquiry:source_2e8a35a1fe106d91"
ASTHMA = "inquiry:source_138633790af95b31"
COUGH = "inquiry:source_2b3d8c21dee4db84"
DYSPNEA = "inquiry:source_1ed4d89b04584bc7"
FEVER = "inquiry:source_e04736c34b2649ab"
PROFILES = [
    ("B：病史后评估症状", [(COPD, "support"), (DYSPNEA, "severity"), (COUGH, "support"), (ASTHMA, "differentiate")]),
    ("C：先问呼吸困难", [(DYSPNEA, "urgent"), (COPD, "support"), (ASTHMA, "differentiate"), (COUGH, "support")]),
    ("D：先问伴随症状", [(COUGH, "support"), (FEVER, "differentiate"), (DYSPNEA, "severity"), (COPD, "support")]),
]


def add_demo_paths(output):
    if output.exists():
        raise FileExistsError("Report already exists; refusing to duplicate the three demo paths")
    if not output.parent.is_dir():
        raise FileNotFoundError("Output parent does not exist")
    catalog = EncounterCatalog(CaseService(ROOT))
    for _, steps in PROFILES:
        for item_id, reason_id in steps:
            assert catalog.bindings[CASE_ID].get(item_id)
            assert reason_id in {row["id"] for row in catalog.reasons(item_id)}
    query = {"case_id": CASE_ID, "simulation": "true", "lang": "zh-CN"}
    report = {"case_id": CASE_ID, "is_simulation": True, "added_paths": [],
              "forest_url": "http://127.0.0.1:3000/forest?case=" + CASE_ID + "&simulation=true"}
    with httpx.Client(base_url="http://127.0.0.1:8000", trust_env=False, timeout=30) as client:
        response = client.get("/research/encounter-forest", params=query)
        response.raise_for_status()
        initial = response.json()
        if initial["session_count"] != 1 or any(row["status"] != "COMPLETED" for row in initial["demo_visits"]):
            raise RuntimeError("Expected exactly the one previously completed demo; no new paths created")
        before_response = client.get("/research/encounter-forest")
        before_response.raise_for_status()
        before = before_response.json()
        report["retained_paths"] = initial["demo_visits"]
        for profile, steps in PROFILES:
            register = client.post("/auth/register", json={
                "username": "simulation_path_" + secrets.token_hex(6),
                "password": secrets.token_urlsafe(24)})
            register.raise_for_status()
            client.headers["Authorization"] = "Bearer " + register.json()["token"]
            try:
                response = client.post("/encounters", params={"lang": "zh-CN"}, json={
                    "case_id": CASE_ID, "is_simulation": True, "client_event_id": "demo-" + profile[0]})
                response.raise_for_status()
                encounter_id = response.json()["id"]
                route = "/encounters/" + encounter_id
                for step, (item_id, reason_id) in enumerate(steps, 1):
                    response = client.post(route + "/actions", params={"lang": "zh-CN"}, json={
                        "item_id": item_id, "reason_id": reason_id,
                        "reason_text": "模拟轨迹" + profile + "：收集此项既有证据，仅演示不同问询顺序，非临床方案。",
                        "hypothesis": "模拟假设：呼吸系统疾病待鉴别", "client_event_id": "step-%d" % step})
                    response.raise_for_status()
                    assert response.json()["status"] == "ACTIVE"
                    exported = client.get(route + "/export")
                    exported.raise_for_status()
                    assert exported.json()["events"][-1]["records"] == catalog.bindings[CASE_ID][item_id]
                diagnosis = "模拟轨迹" + profile + "：疑似慢阻肺急性加重（4条问询不足以确诊，非临床诊断）"
                response = client.post(route + "/diagnoses", json={
                    "diagnoses": [diagnosis], "client_event_id": "diagnosis"})
                response.raise_for_status()
                response = client.post(route + "/finish", json={"client_event_id": "complete"})
                response.raise_for_status()
                fetched = client.get(route, params={"lang": "zh-CN"})
                fetched.raise_for_status()
                visit = fetched.json()
                assert visit["status"] == "COMPLETED" and visit["is_simulation"]
                assert [event["type"] for event in visit["events"]] == ["ACTION"] * 4 + ["DIAGNOSIS", "COMPLETE"]
                assert [event["item"]["id"] for event in visit["events"][:4]] == [item_id for item_id, _ in steps]
                report["added_paths"].append({"profile": profile, "decision_count": 5, "visit": visit})
                # Preserve evidence immediately; no credentials are written.
                output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
            finally:
                logout = client.post("/auth/logout")
                logout.raise_for_status()
                del client.headers["Authorization"]
        response = client.get("/research/encounter-forest", params=query)
        response.raise_for_status()
        forest = response.json()
        assert forest["session_count"] == 4
        assert all(row["status"] == "COMPLETED" for row in forest["demo_visits"])
        assert {row["encounter_id"] for row in initial["demo_visits"]} <= {row["encounter_id"] for row in forest["demo_visits"]}
        outgoing = {}
        for edge in forest["edges"]:
            outgoing.setdefault(edge["source"], []).append(edge)
        assert len(outgoing[CASE_ID]) == 3
        assert sum(edge["count"] for edge in outgoing[CASE_ID]) == 4
        assert len([node for node in forest["nodes"] if node["id"] not in outgoing]) == 4
        assert any(len(edges) > 1 for parent, edges in outgoing.items() if parent != CASE_ID)
        after_response = client.get("/research/encounter-forest")
        after_response.raise_for_status()
        after = after_response.json()
        assert all(not row.get("is_simulation") for row in after["nodes"])
        after_nodes = {row["id"]: row for row in after["nodes"]}
        assert all(after_nodes[row["id"]]["count"] >= row["count"] for row in before["nodes"])
        assert after["session_count"] >= before["session_count"]
        report.update(forest=forest, total_trajectories=4, distinct_terminal_paths=4,
                      original_doctor_nodes_preserved=True, simulation_excluded_from_doctors=True)
        output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(json.dumps({"trajectories": 4, "added": 3, "retained": 1,
                          "nodes": len(forest["nodes"]), "edges": len(forest["edges"]),
                          "terminal_paths": 4, "initial_branch_support": [edge["count"] for edge in outgoing[CASE_ID]],
                          "forest_url": report["forest_url"]}, ensure_ascii=False))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    add_demo_paths(parser.parse_args().output)
