# Guidance.md implementation traceability

This checklist maps every numbered guidance item to the initial implementation. “Foundation” means the schema/data needed for later studies is present, while the advanced statistical study itself remains future research work.

| § | Status | Implementation |
|---:|---|---|
| 1 | Implemented | Separate truth, observation, action and belief domain models/storage. |
| 2 | Implemented | `prepare_raw` creates read-only source links and a versioned manifest. |
| 3 | Implemented | 223-row evidence catalog with raw definition fields. |
| 4 | Implemented | Binary, categorical, multi-choice and numeric token parser. |
| 5 | Implemented with declared source exceptions | Hierarchy edges plus exact upstream-reference drift checks. |
| 6 | Implemented | Dense truth for only the 50 selected cases. |
| 7 | Implemented | Versioned `CaseBundle` JSON plus per-case raw projection and canonical ground-truth exposure-tree JSON. |
| 8 | Implemented | Initial evidence deterministically formatted through `question_en`; no LLM paraphrase. |
| 9 | Implemented | `evidence_semantics.csv` includes role, root, parent, tier and provenance/version. |
| 10 | Implemented / QA-ready | Reliable automatic symptom/antecedent + root/attribute labels; all 49 conditions classified into 11 versioned clinical-system categories; manual QA remains explicit. |
| 11 | Implemented | Versioned research exposure protocol with non-temporal disclaimer. |
| 12 | Implemented | Free exploration, layered exposure and one-choice anchor-state modes. |
| 13 | Implemented | All generated priors named and tagged DDXPlus empirical, train-only priors. |
| 14 | Implemented | Global, age/sex and age/sex/initial-evidence prior tables. |
| 15 | Implemented | Train-only likelihood tables and analysis-only `ReferenceNaiveBayes`. |
| 16 | Implemented | Dataset differential exists only as oracle reference. |
| 17 | Implemented | Full test-split case-quality profile before selection. |
| 18 | Implemented | Configurable branchability score with retained components. |
| 19 | Implemented | Reproducible 50-case selection across 48 pathologies. |
| 20 | Implemented | Train for statistics, test for MVP benchmark; split provenance retained. |
| 21 | Implemented | READY/ACTIVE/COMPLETED/ABORTED environment states. |
| 22 | Implemented | Initial belief gate → evidence loop → final diagnosis and lock. |
| 23 | Implemented | Four belief-capture enum modes; every-step enforcement and configurable checkpoints. |
| 24 | Implemented | Ranked, unique, bounded structured diagnosis probabilities over 49 conditions. |
| 25 | Implemented | Graph nodes contain only case + observed evidence state. |
| 26 | Implemented | SHA-256 over case ID and sorted revealed evidence responses. |
| 27 | Implemented | Ordered event trajectories coexist with canonical state snapshots. |
| 28 | Implemented | Evidence-only monotonic transitions form a DAG. |
| 29 | Implemented | Per-case graphs aggregate into an exportable forest collection. |
| 30 | Implemented | PostgreSQL operational schema. |
| 31 | Implemented | DuckDB/Parquet warehouse separated from Arena database. |
| 32 | Implemented | All 17 listed tables are defined and migrated. |
| 33 | Implemented | Researcher/physician/model player metadata. |
| 34 | Implemented | Session modes, timestamps, versions, seed and status. |
| 35 | Implemented | Append-only ordered events with before/after hashes and timestamps. |
| 36 | Implemented | Complete action/observation/state timing retained for retrospective work. |
| 37 | Implemented | Every changed state receives a queryable snapshot cache. |
| 38 | Implemented | Beliefs normalized separately by diagnosis/rank/probability. |
| 39 | Implemented | React 19 + TypeScript app-router-compatible Sites/Vinext frontend, with a shared collapsible navigation sidebar, shadcn/ui primitives, Motion and React Flow. |
| 40 | Implemented | Fixed-viewport three-column workspace whose patient journey is a live, zoomable state tree that grows after every evidence action. |
| 41 | Implemented | Hypothesis-scoped search exposes safe question metadata and generic provenance, never answers, probabilities or disease associations. |
| 42 | Implemented | Differential, confidence, question count, every-step belief checkpoints and complete personal path; finalization replaces the Arena with a full-screen comparison workspace. |
| 43 | Implemented | No aggregate graph in player route. |
| 44 | Implemented | Separate protected Research route with synchronized raw/normalized JSON, two-column hierarchical tables, stacked diagnosis/probability rows, inline `E_*` question meanings, and a zoomable case tree whose final row contains every ranked differential node with hover/click probability; `/evidence` provides the complete searchable field dictionary. |
| 45 | Implemented | Side-by-side, uniform-node React Flow comparison of the completed personal trajectory and accumulated case forest; canonical state hashes identify shared versus group-only branches, with separate physician/participant/completed-path counts. |
| 46 | Foundation | Player subgroup counts are stored; dashboard filter controls are scaffolded. |
| 47 | Implemented | FastAPI, Pydantic, SQLAlchemy, Alembic and PostgreSQL. |
| 48 | Implemented | Requested domain/service/repository module boundaries. |
| 49 | Implemented | Pure deterministic truth resolution; no LLM call. |
| 50 | Implemented | Unknown, repeated, dependency and not-applicable validation paths. |
| 51 | Implemented | All minimum endpoints plus safe catalogs and health/action inventory. |
| 52 | Implemented and tested | Active schemas omit pathology, oracle differential, truth and quality; comparison unlocks only after finalization. |
| 53 | Implemented | Recommended monorepo directory structure. |
| 54 | Implemented | `make preprocess-ddxplus` runs one ordered rebuild command. |
| 55 | Implemented | Dataset, pipeline, mapping, manifest, Arena, UI and analysis versions. |
| 56 | Implemented | Canonical SHA-256 case hashes stored with sessions. |
| 57 | Implemented and tested | Seven Parquet exports plus complete per-session replay bundle. |
| 58 | Implemented | Versioned analysis run directory and metadata contract. |
| 59 | Foundation | Saved data supports prior, belief, information, efficiency and graph analyses. |
| 60 | Implemented initial metric | Top-1, confidence and entropy shifts between belief snapshots. |
| 61 | Implemented | Reference Naive Bayes posterior and information-gain function. |
| 62 | Implemented initial metric | Questions and redundant queries; timestamps allow time metrics. |
| 63 | Implemented | Final/top-3/top-5 accuracy, pathology rank and oracle coverage. |
| 64 | Implemented | Branch entropy from state-level outgoing action support. |
| 65 | Implemented | Edge action probabilities and player-type subgroup counts. |
| 66 | Foundation | Exact ordered paths and canonical overlap points are exportable. |
| 67 | Foundation | Temporal beliefs plus train-only condition/evidence statistics are retained. |
| 68 | Implemented initial protocol | Tier metadata, layered mode and tier-compatible belief capture. |
| 69 | Implemented and tested | OpenRouter model selection, MODEL player metadata, strict per-turn JSON decisions, canonical Arena validation, 30-question hard limit, complete transcript storage, and model-only case forests. |
| 70 | Implemented and tested | Replay from bundle + events validates every stored hash. |
| 71 | Implemented | Parser, hierarchy, hash, leakage, replay and idempotency tests. |
| 72 | Implemented | All requested counters; exact versioned upstream exceptions fail on drift. |
| 73 | Implemented | Seeded 10-case `clinical_qa.csv`; fixes flow through versioned mappings. |
| 74 | Implemented and tested | Full CLI/API event loop through replay and graph. |
| 75 | Implemented | Demo runner builds divergent strategies and graph support. |
| 76 | Implemented initial protocol | Layered mode is selectable and tier transitions are logged. |
| 77 | Implemented and tested | Opposite query order produces one final canonical state hash. |
| 78 | Enforced | No LLM patient, free-text parser, treatment, labs/imaging or player forest. |
| 79 | Implemented | Generic action/environment boundaries permit future observation types. |
| 80 | Implemented | Abstract `ClinicalEnvironment` with the five requested methods. |
| 81 | Implemented | Raw-to-analysis data flow is represented in code and architecture docs. |
| 82 | Implemented | All eight phase boundaries have executable initial components. |
| 83 | Initial MVP acceptance met | Automated validation covers the listed first-release invariants. |
| 84 | Foundation | Exported case, behavior, cognition, group, forest and model fields support the listed questions. |
| 85 | Implemented | Product is framed as a partially observed evidence environment, not a symptom checker. |
| 86 | Enforced | The twelve priority constraints are encoded in boundaries, versions and tests. |

The only manual gate is clinical review of `data/manifests/clinical_qa.csv`. Automated code cannot truthfully mark medical-semantic QA complete on a reviewer’s behalf.
