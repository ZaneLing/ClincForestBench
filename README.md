# ClincForestBench

[English](README.md) | [简体中文](README.zh-CN.md)

A reproducible clinical decision benchmark that records how physicians and models acquire evidence, revise diagnoses, and build a shared forest of decision paths. Source-backed patient responses are deterministic; models choose actions but do not generate patient results.

**Status: runnable research MVP; clinical adjudication and large-scale evaluation are still pending.** The current local manifests contain **188 Cases across 14 dataset tracks**. Generated patient-level artifacts are excluded from Git and must be rebuilt locally.

[Quick start](#quick-start) · [Dataset coverage](#dataset-coverage) · [Project progress](#project-progress) · [Documentation](docs/README.md)

## Project progress

Repository status reviewed on **2026-10-08**.

Local verification on that date: `make validate` passed (Python tests,
frontend lint, and production build). Browser end-to-end behavior and the
Docker/PostgreSQL profile were not revalidated in this documentation update.

| Area | Implemented | Remaining work |
| --- | --- | --- |
| Data pipeline | Raw-source validation, deterministic conversion, versioned manifests, case hashes, and raw-to-tree audit | Clinical review of mappings, reference labels, and presentation extraction |
| Human Arena | Accounts, evidence actions, staged diagnosis rankings, replay, personal history, and population forests | Broader physician participation and subgroup studies |
| Model Arena | OpenRouter model selection, validated decisions, pause/resume, full exchange archive, and model-only forests | Fixed-protocol, multi-case, repeated model evaluation |
| Temporal Forest v2 | Source-backed action/result events, simulation time, belief checkpoints, and 58 local Cases | Clinical adjudication of temporal and narrative reference semantics |
| Analysis | Accuracy/rank metrics, belief shifts, branch entropy, reference Naive Bayes, and export/snapshot helpers | Advanced trajectory and physician-comparison studies |
| Localization | English/Chinese interface and case-content dictionaries | Regenerate dictionaries when case artifacts change |

The latest feature milestones were the Temporal Arena (September 15), interaction datasets, reproducible downloads, repository organization, and bilingual case localization (September 16, 2026).

The checked-in clinical QA worksheet still has **10 pending reviews**. Generated review pages and passing engineering checks do not constitute medical adjudication. A local exploratory report contains three model runs on one Case; it is not a leaderboard or a population-level performance estimate.

## Dataset coverage

Counts describe the current local manifests, not patient records distributed with this repository. Only manifest-listed Cases are loaded; leftover generated directories do not increase the inventory.

| Track | Cases | Interpretation |
| --- | ---: | --- |
| DDXPlus | 50 | Ground-truth evidence exposure trees; 223 evidence fields and 49 catalog conditions |
| Synthea | 50 | Encounter-linked observations, procedures, and medications |
| MedAgentBench | 30 | Offline task/workflow replay; no live FHIR execution |
| MC-MED | 10 | Source-backed emergency presentation Cases |
| MIMIC-IV multimodal | 10 | Admission Cases with linked Note, ECG, and ED modalities |
| eICU-CRD | 10 | Early ICU clinical assessment |
| PMC Case Reports | 5 | Provisional narrative-sequence Cases |
| NEJM CPC | 5 | Provisional PubMed-record narrative Cases |
| MediScope | 3 | Multimodal consultation |
| MedPI | 3 | Multi-turn consultation |
| PatientSim | 3 | Official public demo profiles |
| Meddies Persona VIE | 3 | Vietnamese persona profiles |
| MedMemoryBench | 3 | Longitudinal memory |
| MedDialogRubrics | 3 | Expert inquiry references matched to source facts |
| **Total** | **188** | **130 classic + 58 Temporal/interaction Cases** |

MIMIC Note, ECG, and ED are linked modalities, not separately counted dataset tracks. Interaction reference labels are explicitly non-adjudicated. See the [Temporal status](docs/temporal_v2_mvp.md) and [interaction contract](docs/interaction_mvp.md).

## Quick start

### 1. Install and build the public classic tracks

The bundled bootstrap targets **macOS (Apple Silicon or Intel)** and installs a project-local Node runtime. Python **3.9+** is required. On other platforms, use a compatible Node installation (**22.13+**) and install the Python/frontend dependencies directly; the current Node bootstrap downloads macOS binaries.

```bash
git clone https://github.com/ZaneLing/ClincForestBench.git
cd ClincForestBench
make setup
./download_data.sh core
make preprocess-ddxplus
make preprocess-guidance2
```

This builds the 130 classic Cases. Downloaded inputs and generated outputs stay local. The downloader's default `all` profile includes public core and interaction inputs; it **does not** download credentialed PhysioNet sources.

### 2. Run the application

Start these in separate terminals:

```bash
make api
```

```bash
make web
```

Open [the application](http://localhost:3000) or [API documentation](http://localhost:8000/docs). Register a local physician account to enter the Arena.

Local development uses **SQLite** at `data/clincforestbench.db`, so accounts, classic sessions, and model runs survive API restarts. Temporal sessions and model runs are stored under `data/processed/temporal/v2/`. Tests use an isolated in-memory repository or temporary databases.

Model testing additionally requires `OPENROUTER_API_KEY` in a local `.env`. Start from `.env.example`, replace the placeholders, and set a private `RESEARCH_API_KEY` for shared use. Standalone provider probes use `tools/api_smoke/.env`. Credentials are loaded by the backend and are not included in exported model transcripts.

### 3. Add Temporal and interaction tracks

Rebuilding all 188 Cases requires approved access to the relevant restricted datasets, as well as the public sources. After obtaining access and configuring PhysioNet credentials:

```bash
./download_data.sh restricted
./download_data.sh interaction
make preprocess-temporal
make preprocess-interaction-mvp
```

Build the base Temporal manifest before the interaction slice. Rebuilding the base replaces that manifest, so rerun the interaction step afterward. See [data setup](docs/data_setup.md) for source requirements and download profiles.

### 4. Verify

```bash
make test       # Python tests
make validate   # Python tests, frontend lint, and frontend production build
make demo       # command-line Arena demonstration
```

The full test suite expects the generated classic, Temporal, and interaction artifacts. Run it after the full data setup; a public-classic-only installation is not a complete test fixture.

## Application routes

| Route | Purpose |
| --- | --- |
| `/` | Animated benchmark overview |
| `/arena` | Physician Arena and track selection |
| `/model-arena` | OpenRouter model testing and round inspection |
| `/history` | Signed-in physician's completed sessions |
| `/forest` | Aggregated participant paths and diagnosis distributions |
| `/research` | Raw source, converted Case, and tree audit |
| `/evidence` | Dataset contracts, mappings, and evidence dictionary |
| `/admin` | Research-key-protected local account administration |
| `/temporal?mode=arena` | Temporal physician Arena |
| `/temporal?mode=timeline` | Recorded source-trajectory replay |

Model testing, history, forest, and research routes support Temporal mode via `?mode=temporal`. The global `EN / 中文` switch changes both interface copy and case text. Full interaction rules, exports, result comparison, and localization instructions are in the [application guide](docs/application_guide.md).

## Repository organization

| Path | Contents |
| --- | --- |
| `backend/`, `frontend/` | FastAPI services and React/TypeScript interface with Vinext/Vite |
| `etl/`, `analysis/` | Source conversion, validation, metrics, and snapshots |
| `configs/`, `migrations/`, `tests/` | Contracts, schema history, and verification |
| `docs/`, `examples/` | Documentation and small auditable examples |
| `scripts/`, `tools/` | Download/bootstrap/demo helpers and standalone utilities |
| `locales/cases/` | Committed public English/Chinese case dictionaries |
| `dataset/` | Local source payloads and tracked provenance notes |
| `data/` | Tracked small manifests; ignored generated artifacts and databases |
| `model/` | Optional local weights and small tracked model metadata |

See [repository layout](docs/repository_layout.md) for Git policies. Local editor settings, credentials, dependencies, build caches, model weights, and patient-level derivatives are excluded from synchronization. Restricted translations remain under `data/processed/locales/cases/`.

## Fidelity and release boundaries

- Active classic sessions expose observed evidence, not hidden truth or oracle diagnoses. Final comparison unlocks only after completion; research and model routes use a research key.
- DDXPlus trees represent evidence exposure, not recorded clinician chronology. Its five known unresolved evidence-parent references and duplicate counts are versioned upstream exceptions checked for drift.
- MedAgentBench currently uses `OFFLINE_TASK_REPLAY`; it does not claim that a FHIR request returned a result or created a resource.
- Recorded results are replayed without invented values. Missing actions resolve to `UNOBSERVED_IN_RECORDED_EPISODE`.
- PMC/NEJM display-order proxies are not elapsed clinical time. Narrative and interaction reference labels require clinician review before formal scoring.
- Local account administration currently exposes plaintext passwords by MVP design. Use throwaway passwords and replace this storage before shared or production deployment.

This is research software, not a diagnostic medical device.

## PostgreSQL development profile

After generating the required artifacts on the host:

```bash
cp .env.example .env  # only if a local .env does not already exist; edit its values
docker compose up --build
```

The Compose profile uses PostgreSQL, applies migrations, and mounts local `data/` and read-only `dataset/`. The current SQLAlchemy schema has **21 tables**; database seeding loads the available classic MVP manifests (130 Cases after both classic build steps), rather than the full source population. Temporal artifacts continue to use their local file store. This profile is a development setup, not a production deployment recipe.

## Documentation

- [Documentation index](docs/README.md)
- [Application guide](docs/application_guide.md)
- [Dataset setup and download profiles](docs/data_setup.md)
- [Architecture and API/data boundaries](docs/architecture.md)
- [Case-tree schema](docs/case_tree_schema.md)
- [Temporal MVP status](docs/temporal_v2_mvp.md) and [interaction MVP](docs/interaction_mvp.md)
- [Design-to-code traceability](docs/guidance_traceability.md)
- [Original design guides](docs/guides/README.md)
