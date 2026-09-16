# Interaction and memory benchmark sources

This directory holds the next ClincForestBench MVP source family. Raw payloads
stay local; the tracked files only document provenance, licensing boundaries,
and reproducible download locations.

| Local directory | Benchmark role | Public payload used by the MVP |
| --- | --- | --- |
| `mediscope/` | Multimodal, multi-turn consultation | PulseMind/MediScope public subset |
| `medpi/` | Multi-turn patient-facing consultation | MedPI patients, transcripts, and dimensions |
| `patientsim/` | Persona-driven patient simulation | Public code and published demo profile only; official patient data is PhysioNet-gated |
| `meddies-persona-vie/` | Patient persona variation | Public Vietnamese synthetic persona samples |
| `medmemorybench/` | Longitudinal clinical memory | Public personas, events, queries, and reports |
| `meddialogrubrics/` | Expert action reference | Public workbook with case-level inquiry rubrics |

Run `make download-interaction-mvp` to fetch the source slice and
`make preprocess-interaction-mvp` to append its Case trees to the Temporal v2
manifest. Do not commit downloaded patient-level or large model-generated data.
