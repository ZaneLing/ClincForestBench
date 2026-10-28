import json
from collections import Counter
from pathlib import Path

from etl.quota import CASES_PER_DATASET


def test_inventory_counts_match_runtime_and_every_shortfall_is_explicit(cases):
    inventory = json.loads(Path("data/manifests/dataset_inventory.json").read_text())
    actual = Counter(c.dataset.name for c in cases.cases.values())
    assert len(actual) == inventory["dataset_count"] == 14
    assert dict(actual) == inventory["dataset_case_counts"]
    assert sum(actual.values()) == inventory["case_count"]
    assert inventory["requested_total"] == 14 * CASES_PER_DATASET == 420
    for dataset, count in actual.items():
        assert 0 < count <= CASES_PER_DATASET
        if count < CASES_PER_DATASET:
            gap = inventory["shortfalls"][dataset]
            assert gap["actual"] == count
            assert gap["requested"] == CASES_PER_DATASET
        else:
            assert dataset not in inventory["shortfalls"]
    assert inventory["quota_complete"] == (sum(actual.values()) == 420)


def test_selected_source_ids_and_memory_evidence_are_unique(cases):
    source_ids, memory_events = set(), set()
    for case in cases.cases.values():
        if case.generation_mode != "SOURCE_BACKED_EVIDENCE":
            continue
        source = case.source_provenance["source"]
        identity = (case.dataset.name, source["source_case_id"])
        assert identity not in source_ids
        source_ids.add(identity)
        if case.dataset.name == "MedMemoryBench":
            raw = case.source_provenance["raw_source"]
            for event in raw["events"]:
                identity = (raw["source_persona_id"], event["event_id"])
                assert identity not in memory_events
                memory_events.add(identity)
