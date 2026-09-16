# Repository layout

ClincForestBench separates executable source from downloaded clinical data and
generated patient-level artifacts. The separation is intentional: a clone is
small and auditable, while `download_data.sh` recreates permitted sources.

| Path | Responsibility | Git policy |
| --- | --- | --- |
| `backend/` | FastAPI, domain model, persistence, Arena services | tracked |
| `frontend/` | Next.js interface and visualization components | source and lockfile tracked; build/dependency caches ignored |
| `etl/` | deterministic source-to-Case/Event/tree conversion | tracked |
| `analysis/` | metrics, snapshots, and reference analyses | tracked |
| `configs/` | benchmark and exposure contracts | tracked |
| `migrations/` | database schema history | tracked |
| `tests/` | automated test suite | tracked |
| `docs/` | architecture, schemas, guides, and data contracts | tracked |
| `examples/` | small, reviewable example records | tracked |
| `scripts/data/` | dataset download helpers | tracked |
| `scripts/dev/` | local development bootstrap | tracked |
| `scripts/demo/` | command-line demonstrations | tracked |
| `tools/api_smoke/` | optional external-provider connectivity probes | scripts tracked; `.env` ignored |
| `dataset/` | upstream source datasets and provenance notes | notes/small permitted metadata tracked; large and restricted payloads ignored |
| `data/processed/` | generated Case bundles, Parquet tables, and trees | ignored |
| `data/exports/` | session exports | ignored |
| `data/analysis_runs/` | local evaluation runs | ignored |
| `model/` | optional local model weights | weights ignored; small model metadata tracked |

Do not move raw patient-level files into source directories to bypass ignore
rules. A new dataset should add a `dataset/<name>/README.source.md`, a
reproducible downloader under `scripts/data/` or `download_data.sh`, an ETL
adapter, and tests for its fidelity boundary.
