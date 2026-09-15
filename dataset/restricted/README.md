# Restricted clinical datasets

This directory is the single local home for credentialed or conservatively
restricted patient-level source data used by ClincForestBench. Raw records are
available to local ETL code but are intentionally excluded from Git.

| Local directory | Dataset | Local payload | Distribution rule |
| --- | --- | ---: | --- |
| `mc-med-v1.0.1/` | MC-MED v1.0.1 | ~1.2 GB | Treat as credentialed; do not redistribute patient-level tables. |
| `eicu-crd-v2.0/` | eICU Collaborative Research Database v2.0 | ~5.1 GB | PhysioNet credentialed data; sharing is prohibited by the supplied license. |
| `mimic-iv-ed-v2.2/` | MIMIC-IV-ED v2.2 | ~116 MB | PhysioNet credentialed data; sharing is prohibited by the supplied license. |
| `mimic-iv-ecg/` | MIMIC-IV-ECG table snapshot | ~298 MB | Treat as credentialed because its identifiers link to MIMIC-IV. |
| `mimiciv/` | MIMIC-IV v3.1 | ~37 GB | PhysioNet credentialed; local hospital/ICU backbone for Temporal v2. |
| `mimic-iv-note/` | MIMIC-IV-Note v2.2 | ~5.1 GB | PhysioNet credentialed; retrospective text remains local-only. |

Each child directory contains a tracked `README.source.md`. Supplied license,
checksum, and non-patient data-dictionary files are retained where available.
The actual CSV/GZIP data remains present only in the local workspace.

Do not place credentials, access cookies, PhysioNet passwords, or personal
access tokens in this directory. Any future public examples must be synthetic
or independently reviewed aggregate outputs.
