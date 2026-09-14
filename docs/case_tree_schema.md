# MVP ground-truth case-tree schema

Each selected DDXPlus case now has two immutable audit artifacts:

- `raw_cases/mvp50_v1/<case_id>.raw.json`: an exact JSON projection of the source Parquet row. Source strings are deliberately left unparsed.
- `case_trees/mvp50_v1/<case_id>.tree.json`: the classified, human-readable tree derived from that row.

The aggregate index is `data/manifests/mvp50_tree_manifest.json`. It records the raw/tree hashes, disease category, node/evidence counts and the result of all conversion checks for every MVP-50 case.

## Honest interpretation

DDXPlus does not contain an observed clinician chronology. It also contains no physical examination, laboratory, imaging, procedure or treatment events. The generated structure is therefore named a **canonical ground-truth exposure tree**, not a recorded diagnostic workflow.

Only source-asserted evidence tokens become tree nodes. The 223-field dense truth is still used by the Arena response engine, but implicit negative fields are not rendered as if they were observed clinical events.

The deterministic stages are:

1. patient context (`AGE`, `SEX`);
2. initial presentation (`INITIAL_EVIDENCE`);
3. symptom questions and patient observations;
4. antecedent/risk questions and patient observations;
5. every ranked diagnosis in the source reference differential, with the pathology-matching node marked as ground truth.

Symptom attributes are nested under their source-defined parent evidence. Raw token order is retained where possible, but must not be interpreted as timestamped chronology.

## Node types

| Node type | Meaning | Primary source |
|---|---|---|
| `CASE` | Case root | generated case ID |
| `STAGE` | Deterministic exposure grouping | tree schema |
| `CONTEXT` | Demographic value | `AGE`, `SEX` |
| `ACTION` | `ASK_QUESTION` using canonical question text | `EVIDENCES` + evidence catalog |
| `OBSERVATION` | Human-readable source-asserted result | `EVIDENCES` |
| `DIAGNOSIS` | One ranked reference-differential candidate with its original probability and `is_ground_truth` marker | `PATHOLOGY`, `DIFFERENTIAL_DIAGNOSIS` |

Schema `ground_truth_exposure_tree_v2` expands the source differential into one node per candidate (`diagnosis.differential.001`, `002`, …). The nodes share the final visual row and preserve source order. `PATHOLOGY` maps to the single candidate whose `is_ground_truth` value is true; no additional synthetic primary-diagnosis node is created.

## Disease categories

All 49 DDXPlus conditions are covered exactly once by `configs/disease_categories.yaml`. The current taxonomy has 11 broad clinical-system categories and is marked for clinical QA because the upstream dataset does not provide a system taxonomy.

## Rebuild

The complete pipeline includes tree generation:

```bash
make preprocess-ddxplus
```

For a tree-only rebuild after the case bundles already exist:

```bash
.venv/bin/python -m etl.build_case_trees
```
