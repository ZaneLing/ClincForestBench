# ClincForestBench

This repository is the runnable structure described in [Guidance.md](docs/guides/Guidance.md), [Guidance2.md](docs/guides/Guidance2.md), and the [Temporal Forest v2 guide](docs/guides/Temporal_Forest_v2_Guide.md): one deterministic Arena spanning classic diagnosis/workflow tracks, time-aware EHR and narrative cases, plus consultation, persona, longitudinal-memory, and expert-action-reference MVPs.

## What is already wired

- Immutable raw layer over `dataset/ddxplus`, strict QA report, canonical Parquet patients and catalogs.
- Train-only global, demographic, initial-evidence priors, plus condition/evidence likelihoods for an analysis-only Naive Bayes reference.
- Reproducible MVP-50 selection from `test`, dense 223-field truth, SHA-256 case bundles and a clinical QA worksheet.
- Exact raw-row JSON projections plus 50 auditable ground-truth exposure trees classified into 11 disease-system categories.
- 50 Synthea encounter trees built from exact linked CSV observations, procedures, and medications, with no invented narrative reports.
- 30 MedAgentBench workflow trees across lab retrieval, conditional management, and referral actions, retaining the original task and official FHIR function schema.
- Generic `ClinicalEnvironment` and deterministic `DDXPlusEnvironment` with hierarchy validation.
- Initial-belief gate, configurable Arena/belief modes, append-only events, snapshots, idempotency, replay and canonical graph aggregation.
- FastAPI active and research routes with physical response separation; 21-table PostgreSQL/SQLite schema, persistent local accounts/model runs and an isolated in-memory test repository.
- Pure animated benchmark home, account-gated three-track `/arena`, OpenRouter `/model-arena`, personal `/history`, population `/forest`, account `/admin`, full-screen result comparison, `/research` data-QA UI, and the unified `/evidence` dataset contract center in React/TypeScript.
- Unified clinical visual system built with shadcn/ui primitives, Motion animation and React Flow diagnosis-tree canvases.
- Seven-file Parquet export, replay bundle, and versioned analysis snapshot helpers.
- Temporal Forest v2 canonical events with separate order/acquisition/availability/documentation times, pending actions, per-result belief checkpoints, observed-only result replay, source validation, and 58 local MVP case bundles across 11 Temporal datasets.

See [architecture.md](docs/architecture.md), [guidance_traceability.md](docs/guidance_traceability.md), and the [Temporal v2 MVP status](docs/temporal_v2_mvp.md) for the design-to-code map and declared first-slice limits.

## Raw case → processed tree audit

Open `http://localhost:3000/research`. The first MVP case loads automatically into three synchronized columns:

1. the exact unparsed source row JSON;
2. the processed and classified case-tree JSON with conversion checks;
3. the complete color-coded tree from patient context through question actions and observations to the full ranked reference differential.

DDXPlus has no recorded lab, imaging, examination, procedure or treatment events, so the MVP does not fabricate them. The output is explicitly a canonical ground-truth **exposure tree**, not an observed clinician chronology. See [case_tree_schema.md](docs/case_tree_schema.md) for the schema and interpretation boundary.

The classic inspector contains 130 cases across three tracks. Its Temporal mode adds 58 local Cases from 11 sources, for 188 inspectable Cases across 14 dataset tracks. The added interaction slice contains three MVP trees each from MediScope, MedPI, PatientSim, Meddies Persona VIE, MedMemoryBench, and MedDialogRubrics. Synthea is labeled `NATURAL_CSV_EXPORT`. MedAgentBench is labeled `OFFLINE_TASK_REPLAY`: this machine has no Docker/Java FHIR runtime, so the current MVP evaluates the task-derived workflow and never claims that a FHIR request returned a lab value or that a POST created a resource.

## Concrete converted patient example

Open [`examples/DDX_TEST_0021752.readable.json`](examples/DDX_TEST_0021752.readable.json). It is generated from a real selected test-split row and includes readable questions rather than only `E_*` codes. Its initial state is:

```json
{
  "case_id": "DDX_TEST_0021752",
  "demographics": { "age": 33, "sex": "M" },
  "initial_presentation": {
    "question": "Have you noticed a wheezing sound when you exhale?",
    "answer": "Yes"
  },
  "ground_truth": {
    "pathology": "Acute COPD exacerbation / infection"
  }
}
```

The full 223-field dense truth remains in the linked versioned case bundle and is never returned during an active session.

## How Arena questions are selected

After each belief submission, the Arena exposes the complete unanswered DDXPlus Evidence catalog. The initial evidence is already revealed, asserted case tokens resolve to `Yes` or their coded value, unasserted binary evidence resolves to `No`, and child attributes remain unavailable until their parent question has been asked. The picker supports keyword and `E_*` searches and uses separate colors for symptoms, symptom details, and medical history. It does **not** inspect hidden answers while constructing the picker.

The default protocol is `EVERY_STEP`: after each patient answer, questions lock until a new belief is submitted for that observation state. Every question extends the live patient-path tree by one canonical state. Finalization replaces the Arena with three synchronized, zoomable views: the player's trajectory on the left, the protected reference tree in the middle, and the case's accumulated participant forest on the right. The result is not shown in a modal.

The Arena collects an ordered diagnosis list rather than asking clinicians to invent probabilities. Searchable disease chips are clicked into the candidate list, where they can be drag-ranked or removed. The current ordering persists after new evidence, so an unchanged judgment can be submitted directly. Every stage submission remains available in the collapsible history panel. For compatibility with the benchmark belief schema, deterministic rank weights are generated by the client and explicitly labeled as system-derived—not clinician-entered—in the completed artifact.

Playing now requires a registered physician account. Session creation ignores client-supplied player identities and binds each run to the authenticated account. `/history` returns only that account's completed sessions: the reference tree, raw/formatted personal decision JSON, and every S0/S1/… diagnosis ranking. The normal `make api` path uses `data/clincforestbench.db`, so accounts and play history survive local API restarts; Docker continues to use PostgreSQL.

## Frontend experience

The opening screen is a chrome-free animated clinical-forest overview of the benchmark: a case grows into branches, doctors add independent paths, and patient trees assemble into a forest. It does not ask the visitor to choose a dataset. `Enter the Arena` opens the authenticated Arena route, where classic and Temporal sources can be selected before a case begins.

A collapsible system sidebar is shown on the working routes, but intentionally omitted from the home page. It links directly to the human Arena, Model Test, personal decision history, the three-column Case inspector, population forest analytics, the unified dataset/rules center, and the local account backend. The data center explains each source dataset, raw fields, raw-to-tree mapping, track-specific Arena rules, and fidelity boundary; the DDXPlus tab also resolves all 223 `E_*` identifiers to their clinical question, domain, data type, parent field, and coded value meanings.

The global `EN / 中文` control switches both interface copy and case content. English mode translates non-English source cases, including Meddies Persona VIE, into English. Chinese mode translates every displayable MVP case string into Simplified Chinese. IDs, codes, timestamps, units, enum contracts, hashes, and source files remain unchanged; localization is applied to API response copies. Public translations are committed in `locales/cases/`; restricted patient-level translations remain under the ignored `data/processed/locales/cases/` directory and must be built inside the authorized deployment. Regenerate both layers after rebuilding case artifacts with `make translate-cases`. If the configured OpenRouter quota is unavailable, the public layer alone can resume through `python tools/build_case_translations.py --provider google --scope public`; the generator rejects Google mode for restricted cases.

全局 `EN / 中文` 控件会同时切换界面文案和病例内容。英文模式会将 Meddies Persona VIE 等非英文来源统一翻译为英文；中文模式会将所有可展示的 MVP 病例文本翻译为简体中文。ID、编码、时间戳、单位、枚举契约、哈希和源文件保持不变，本地化仅作用于 API 响应副本。公开翻译提交在 `locales/cases/`；受限的患者级翻译保存在已忽略的 `data/processed/locales/cases/`，只能在获授权的部署环境内生成。重建病例产物后运行 `make translate-cases` 即可重新生成两层词典。如果配置的 OpenRouter 额度不可用，可以运行 `python tools/build_case_translations.py --provider google --scope public` 仅续传公开层；生成器会拒绝用 Google 模式处理受限病例。

`/model-arena` reads the current OpenRouter catalog and groups selectable models by provider/company before dataset and case selection. A run advances one server-validated turn at a time: the model receives the current public patient state, recent decision evolution, explicit early-stopping signals, and the complete condition and action libraries; it returns one strict JSON decision, submits its ordered stage diagnosis, and either asks one currently available non-repeated high-yield action or finalizes one unique outcome. The normal target is 3–10 questions, stable Top-1 decisions are prompted to finalize, and 30 remains only a hard emergency ceiling. Invalid IDs, repeated diagnoses/questions, locked child actions, and attempts to exceed the cap are rejected by the canonical Arena state machine. The browser can auto-advance, pause, single-step, retry a failed round, and recover persisted active runs after a page reload.

`/model-arena?mode=temporal` applies that same OpenRouter loop to all 58 Temporal Cases. Its contract uses clinical `ACTION` and `FINAL`: selecting a source-backed action advances simulation time and returns the recorded result synchronously, every newly visible state triggers a new ranked differential, and repeated or unavailable actions are rejected. The completed artifact retains every prompt, raw response, parsed JSON, state application, latency, and the same model/reference/community comparison used elsewhere.

Every model request payload, raw OpenRouter response, extracted decision JSON, validation/application result, error, and latency is persisted without the API key. During play they are visible in a four-tab round inspector. Completion reuses the same three-tree comparison as human play—model path, Ground Truth, and a model-only case forest accumulated across completed model runs—and exports a versioned `clincforestbench.model-arena-run.v1` artifact containing the full exchange archive.

The application shell is locked to the browser viewport and does not use page-level vertical scrolling. Long content scrolls only inside its own panel; diagnosis trees pan by dragging and zoom with the mouse wheel inside their canvas. This keeps the patient path, clinical interaction and current differential visible together throughout a case.

Completing a case automatically downloads `ClincForestBench_<case>_<session>.json`. The same canonical artifact can be downloaded again from the result page or fetched from `GET /sessions/{session_id}/artifact` after finalization. It contains the session metadata, full revealed patient path, every staged and final diagnosis ordering, append-only event log, observation-state snapshots, final comparison, and post-completion reference findings.

`/forest` aggregates physician sessions without mixing the oracle into clinician counts. Each state node reports visit rate and path support. Its diagnosis table reports selection rate, Top-1 rate, mean rank when selected, and mean rank weight at that exact node; the same distributions are available for every S-step and for final submissions. Ground truth is shown as a separate green reference marker.

`/admin` is protected by the research key and exposes registered account names, plaintext passwords, registration time, and play counts. **This intentionally follows the current MVP request and is unsafe by design: use throwaway passwords only, keep it local, and replace plaintext storage before any shared or production deployment.**

The result comparison matches nodes by canonical state hash. Shared states and edges are cyan, group-only branches are gray, the submitted diagnosis is violet and the ground-truth diagnosis is green. The case forest reports distinct registered physicians, all distinct participants and completed paths separately; it does not present a session count as a doctor count.

The Research case tree keeps a strict top-to-bottom diagnostic chronology: case → blue stage spine → stage-specific questions/context and returned observations → the complete final differential row. Every source diagnosis is an equal-size circular node carrying its original rank and probability; the pathology-matching ground-truth node is bright red while the remaining differential nodes are amber. Hovering or selecting a diagnosis reveals its probability. The canvas initially fits the complete patient tree; the mouse wheel zooms and dragging pans.

`/temporal?mode=arena` is the doctor-playable Temporal Arena. A player reads a natural-language S0, submits a ranked differential, and chooses a concrete history question, examination, laboratory test, image, ECG, or record review. The same request advances the simulation clock to the source-backed availability time and renders the result as a clinical report—there is no wall-clock wait and no raw JSON in the doctor view. `/research?mode=temporal` is the Temporal section of Case 查看 and shows the exact local raw source slice, normalized Case JSON, ordered transformation rules, and complete tree. `/temporal?mode=timeline` retains the source-trajectory player. Imaging impressions and narrative imaging findings are stored and shown inside their result nodes.

MIMIC-IV-Note and MIMIC-IV-ECG are modalities of a MIMIC admission case, not standalone pseudo-cases. ECG machine time is always labeled with its known clock uncertainty. eICU remains an `ICU_EARLY_CLINICAL_ASSESSMENT` task and uses ICU-admission offsets; `Performed`, `scored`, and obtain-option workflow markers are removed before Case construction, while clinically meaningful history, examination and laboratory rows become distinct actions. Interface-dependent missingness is never interpreted as “test not performed.” Every unrecorded action resolves to `UNOBSERVED_IN_RECORDED_EPISODE`, and no adapter calls an LLM to invent a patient result.

PMC and NEJM CPC are narrative-sequence extensions, not timestamp-complete EHR cases. The converter preserves source sentences, extracts explicit intervals when present, and otherwise uses LOW-confidence monotonic order proxies solely for visualization. Their reference labels and chronology require clinician review before formal benchmark release.

Both the source case and normalized Case Tree can be switched between wrapped JSON source and an indented, hierarchical two-column field table. Every object or array group has an independent disclosure arrow. Arrays, objects, and Python-literal arrays embedded in raw string fields are expanded item by item. Each differential entry uses its sequence number on the left and stacks the full diagnosis name above its probability on the right; every `E_*` value in the source table is annotated with its human-readable Evidence question. In the normalized table, clicking any `tree.nodes[*]` row or descendant field highlights the same node in the visual tree. Long keys and values wrap within their panel, so neither view introduces horizontal JSON scrolling.

## Quick start

The Python virtual environment and project-local Node runtime are isolated from the system:

```bash
make setup
make download-data
make preprocess-ddxplus
make preprocess-guidance2
make preprocess-temporal
make preprocess-interaction-mvp
make test
```

`make download-data` is the reproducible public-data entry point. It restores
the large Git-ignored core datasets and the interaction MVP slice. Use
`./download_data.sh --help` for smaller profiles and the explicit,
credential-gated PhysioNet mode. See [data setup](docs/data_setup.md).

Start the two development processes in separate terminals:

```bash
make api
make web
```

Open `http://localhost:3000`. API docs are at `http://localhost:8000/docs`. The local research key defaults to `local-research-only`; replace it with `RESEARCH_API_KEY` before shared use.

Model Test also requires `OPENROUTER_API_KEY` in the project `.env`. The
standalone API probes use `tools/api_smoke/.env`. Neither file is tracked. The
secret is loaded only by FastAPI; the status endpoint exposes only whether it
is configured.

Choose `Enter the Arena`, then register a throwaway doctor account before selecting a dataset and case. The SQLite database created by `make api` is `data/clincforestbench.db`.

To verify the core loop without a browser:

```bash
make demo
```

## PostgreSQL mode

Local development defaults to the in-memory repository. The container profile selects PostgreSQL, migrates the 17 operational tables and idempotently loads only the MVP-50 cases—not all 1.29M source patients:

```bash
cp .env.example .env
docker compose up --build
```

## Rebuild and outputs

`make preprocess-ddxplus` performs the complete ordered pipeline. Generated artifacts live under:

- `data/manifests`: raw QA, selection and case version manifests.
- `data/processed/ddxplus/v1`: canonical patients, catalogs, train-only priors and case bundles.
- `data/processed/ddxplus/v1/raw_cases` and `case_trees`: exact raw projections and deterministic per-case trees.
- `data/processed/synthea/v1/mvp50_v1`: encounter-scoped case bundles, raw projections, and evidence trees.
- `data/processed/medagentbench/v2/mvp30_v1`: offline workflow bundles, raw task projections, and reference workflow trees.
- `data/exports`: session-level Parquet exports and replay JSON.
- `data/analysis_runs`: immutable analysis snapshots.
- `data/processed/temporal/v2`: local-only source-validation reports, 58 case bundles, canonical Case/Event Parquet tables, three engineering replay paths per Case, doctor-session JSON, review HTML, and Temporal DAG JSON. These patient-level derivatives are intentionally ignored by Git.

## Repository and local-data layout

Source code, configurations, migrations, tests, documentation, and small
redistributable metadata are version controlled. Downloaded datasets live
under `dataset/`, generated artifacts under `data/`, local model payloads under
`model/`, operational scripts under `scripts/`, and standalone API probes
under `tools/api_smoke/`. See the complete [repository layout](docs/repository_layout.md).

Credentialed clinical datasets are organized locally under `dataset/restricted/`: MC-MED v1.0.1, eICU-CRD v2.0, MIMIC-IV v3.1, MIMIC-IV-Note v2.2, MIMIC-IV-ED v2.2, and the local MIMIC-IV-ECG table snapshot. Their patient-level CSV/GZIP payloads and all record-level Temporal derivatives are deliberately excluded from Git. Only source notes, supplied license/checksum files, and non-patient schema metadata may be committed. See [the restricted-data catalog](dataset/restricted/README.md).

The interaction and memory sources live under `dataset/interaction/`. Run `make download-interaction-mvp` to reproduce the public/permitted local source slice and `make preprocess-interaction-mvp` after the base Temporal build. PatientSim uses only the official public demo because its full patient-level release is PhysioNet credentialed; ambiguous or undeclared source licenses are handled conservatively and their rows are never committed. See [the interaction MVP contract](docs/interaction_mvp.md).

The public release has 5 unresolved evidence-parent references and known exact duplicate counts. They are explicitly versioned in `configs/ddxplus.yaml`; any change to those counts fails QA as source drift. The raw source is never edited.

## API boundaries

Player-safe session routes require a bearer token and verify that the session belongs to the authenticated physician. They include session creation/state, searchable questions, evidence actions, belief capture, finalization, personal history, and the non-case-specific `/catalog/evidences` dictionary. During an active session they never serialize pathology, oracle differential, hidden truth or case quality. After finalization locks the session, review/history routes reveal only the completed case comparison. `/research/*`, `/admin/*`, `/exports`, and `/model-arena/*` require `X-Research-Key`; OpenRouter credentials never cross that API boundary.

This is research software and not a diagnostic medical device.
