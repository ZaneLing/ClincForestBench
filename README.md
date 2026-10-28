# ClincForestBench

[English](README.md) | [简体中文](README.zh-CN.md)

A reproducible clinical decision benchmark that records how physicians and models acquire evidence, revise diagnoses, and build a shared forest of decision paths. Source-backed patient responses are deterministic; models choose actions but do not generate patient results.

**Status: runnable research MVP; clinical adjudication and large-scale evaluation are still pending.** The current local manifests contain **393 Cases across 14 dataset tracks**. Generated patient-level artifacts are excluded from Git and must be rebuilt locally.

[Quick start](#quick-start) · [Dataset coverage](#dataset-coverage) · [Project progress](#project-progress) · [Documentation](docs/README.md)

## Project progress

Repository status reviewed on **2026-10-28**.

Local verification: all 94 Python tests, frontend lint, and the production
build passed. The running API reports 393 unordered cases; bilingual mapping
coverage has no gaps. Browser end-to-end behavior and the Docker/PostgreSQL
profile were not revalidated in this update.

| Area | Implemented | Remaining work |
| --- | --- | --- |
| Data pipeline | Raw-source validation, deterministic conversion, versioned manifests, case hashes, and raw-to-tree audit | Clinical review of mappings, reference labels, and presentation extraction |
| Human Arena | Accounts, evidence actions, staged diagnosis rankings, replay, personal history, and population forests | Broader physician participation and subgroup studies |
| Model Arena | OpenRouter model selection, validated decisions, pause/resume, full exchange archive, and model-only forests | Fixed-protocol, multi-case, repeated model evaluation |
| Source evidence | 303 additional cases converted into independent action/result branches in the unified runtime | Clinical adjudication of mappings and reference labels |
| Analysis | Accuracy/rank metrics, belief shifts, branch entropy, reference Naive Bayes, and export/snapshot helpers | Advanced trajectory and physician-comparison studies |
| Localization | English/Chinese interface and case-content dictionaries | Regenerate dictionaries when case artifacts change |

All runnable cases now use unordered evidence access: players and models choose
their own inquiry and examination order. There is no simulation clock, waiting
action, source sequence unlocking, or time score. Source dates remain clinical
history or provenance, and actual participant decision paths remain recorded.

The checked-in clinical QA worksheet still has **10 pending reviews**. Generated review pages and passing engineering checks do not constitute medical adjudication. A local exploratory report contains three model runs on one Case; it is not a leaderboard or a population-level performance estimate.

## Dataset coverage

Counts describe the current local manifests, not patient records distributed with this repository. Only manifest-listed Cases are loaded; leftover generated directories do not increase the inventory.

| Track | Cases | Interpretation |
| --- | ---: | --- |
| DDXPlus | 30 | Ground-truth evidence exposure trees; 223 evidence fields and 49 catalog conditions |
| Synthea | 30 | Encounter-linked observations, procedures, and medications |
| MedAgentBench | 30 | Offline task/workflow replay; no live FHIR execution |
| MC-MED | 30 | Source-backed emergency presentation Cases |
| MIMIC-IV multimodal | 30 | Admission Cases with linked Note, ECG, and ED modalities |
| eICU-CRD | 30 | Early ICU clinical assessment |
| PMC Case Reports | 30 | Provisional narrative evidence Cases |
| NEJM CPC | 30 | 27 open full-text presentations and 3 PubMed abstracts |
| MediScope | 30 | Multimodal consultation with source diagnostic statement proxies |
| MedPI | 30 | Distinct diagnosis conversations from 24 patient profiles |
| PatientSim | 3 | Official public demo profiles |
| Meddies Persona VIE | 30 | Vietnamese persona profiles |
| MedMemoryBench | 30 | Disjoint source event windows from 20 personas |
| MedDialogRubrics | 30 | Expert inquiry references matched to source facts |
| **Total** | **393** | **One unordered evidence catalog across 14 datasets** |

Aggregate counts are recorded in [dataset_inventory.json](data/manifests/dataset_inventory.json).
The requested quota is **30 per dataset (420 total)**. The current **27-case
shortfall** is PatientSim, whose full release requires an authorized PhysioNet
export. See [quota and sampling details](docs/dataset_quota.md).
MIMIC Note, ECG, and ED are linked modalities, not separately counted dataset tracks. Interaction reference labels are explicitly non-adjudicated. See the [source evidence status](docs/source_evidence.md) and [interaction contract](docs/interaction_mvp.md).

## Quick start

The physician Arena now uses a unified Visit protocol: shared examination and
inquiry libraries, required reasons at each step, persisted termination on a
missing inquiry answer or examination result, diagnosis at any time during an
active visit, and optional post-diagnosis plans.
The 393-case local inventory currently yields 354 operation and 1127 inquiry
items. See the [protocol and mapping guide](docs/encounter_protocol.md).

### 1. Install and build the public classic tracks

The bundled bootstrap targets **macOS (Apple Silicon or Intel)** and installs a project-local Node runtime. Python **3.9+** is required. On other platforms, use a compatible Node installation (**22.13+**) and install the Python/frontend dependencies directly; the current Node bootstrap downloads macOS binaries.

```bash
git clone https://github.com/ZaneLing/ClincForestBench.git
cd ClincForestBench
make setup
./download_data.sh core
make preprocess-ddxplus
make preprocess-workflows
```

This builds the 90 classic Cases. Downloaded inputs and generated outputs stay local. The downloader's default `all` profile includes public core and interaction inputs; it **does not** download credentialed PhysioNet sources.

### 2. Run the application

Start both services with one command:

```bash
./start.command
```

On macOS, you can also double-click `start.command` in Finder. The launcher
installs missing local dependencies, waits for both services, opens the browser,
and shuts everything down together when you press `Ctrl-C`. Use `make start` as
the equivalent terminal command. Separate `make api` and `make web` commands
remain available for split-terminal development.

Open [the application](http://localhost:3000) or [API documentation](http://localhost:8000/docs). Register a local physician account to enter the Arena.

Local development uses **SQLite** at `data/clincforestbench.db` for accounts, canonical sessions, and model runs across all available cases. Physician Visits persist in `data/encounters.db`. Tests use isolated in-memory repositories or temporary databases.

Model testing additionally requires `OPENROUTER_API_KEY` in a local `.env`. Start from `.env.example`, replace the placeholders, and set a private `RESEARCH_API_KEY` for shared use. Standalone provider probes use `tools/api_smoke/.env`. Credentials are loaded by the backend and are not included in exported model transcripts.

### 3. Add source evidence and interaction cases

Rebuilding all 393 Cases requires approved access to the relevant restricted datasets, as well as the public sources. After obtaining access and configuring PhysioNet credentials:

```bash
./download_data.sh restricted
./download_data.sh interaction
make download-nejm-open
.venv/bin/python -m etl.build_ehr_sources --allow-shortfall
.venv/bin/python -m etl.build_interaction_mvp --allow-shortfall
make preprocess-evidence
.venv/bin/python tools/update_dataset_inventory.py
```

Build the EHR source staging inputs before merging the interaction slice.
The shortfall option explicitly records the missing PatientSim authorization.
With all sources authorized, `make preprocess-all` enforces the full 420-case quota.
The interaction step also converts all source episodes into unordered bundles
under `data/processed/evidence/`. If staging inputs already exist, use
`make preprocess-evidence` to regenerate them. See [data setup](docs/data_setup.md).

### 4. Verify

```bash
make test       # Python tests
make validate   # Python tests, frontend lint, and frontend production build
make demo       # command-line Arena demonstration
```

The full test suite expects all 393 generated unordered cases. Run it after the full data setup; a public-classic-only installation is not a complete test fixture.
New case text can be translated locally using the optional
`offline-translation` dependencies and the workflow in [quota details](docs/dataset_quota.md).

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
| `/temporal` | Compatibility redirect to `/arena` |

Model testing, history, forest, and research use the unified catalog. The global `EN / 中文` switch changes both interface copy and case text. Full interaction rules, exports, result comparison, and localization instructions are in the [application guide](docs/application_guide.md).

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
- Source display order never controls evidence access. Narrative and interaction reference labels require clinician review before formal scoring.
- Local account administration currently exposes plaintext passwords by MVP design. Use throwaway passwords and replace this storage before shared or production deployment.

This is research software, not a diagnostic medical device.

## PostgreSQL development profile

After generating the required artifacts on the host:

```bash
cp .env.example .env  # only if a local .env does not already exist; edit its values
docker compose up --build
```

The Compose profile uses PostgreSQL, applies migrations, and mounts local `data/` and read-only `dataset/`. The current SQLAlchemy schema has **21 tables**; database seeding loads the available unified case manifests (393 cases after the complete build), rather than the full source population. This profile is a development setup, not a production deployment recipe.

## Documentation

- [Documentation index](docs/README.md)
- [Local development and one-command launcher](docs/development.md)
- [Application guide](docs/application_guide.md)
- [Dataset setup and download profiles](docs/data_setup.md)
- [Architecture and API/data boundaries](docs/architecture.md)
- [Case-tree schema](docs/case_tree_schema.md)
- [Source evidence MVP status](docs/source_evidence.md) and [interaction MVP](docs/interaction_mvp.md)
