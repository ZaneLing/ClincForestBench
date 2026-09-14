# Architecture and data boundaries

```text
dataset/{ddxplus,synthea,medagentbench} (read-only sources)
        │ versioned converters + manifests
        ▼
data/raw ── ETL/QA ──► data/processed (Parquet + train-only priors)
                              │
                              ▼
                    versioned multi-track case bundles
                              │
               ┌──────────────┴──────────────┐
               ▼                             ▼
      Clinical environments        PostgreSQL / SQLite arena DB
       (deterministic)             (events/states/beliefs/graph)
               └──────────────┬──────────────┘
                              ▼
                          FastAPI
          ┌──────────────┬───────────────┐
          ▼              ▼               ▼
 player-safe       protected         protected
 `/sessions`       `/research`       `/model-arena`
                                          │
                                server-side OpenRouter
                                one validated JSON turn
          └──────────────┬───────────────┘
                              ▼
               Parquet exports + analysis snapshots
```

The four domains never collapse into one object:

- **Truth** lives in versioned case bundles and research storage.
- **Observation** is the revealed subset returned by active-session APIs.
- **Action** is an immutable, ordered event with a client idempotency key.
- **Belief** is a separately normalized snapshot attached to a state hash.

Two graph forms are retained. Events preserve the exact personal trajectory. State hashes merge order-independent evidence sets (and future created FHIR resources) into a canonical information-state DAG. `ClinicalEnvironment` is the generic boundary: DDXPlus handles dense yes/no questioning, Synthea reveals encounter-linked structured records, and the FHIR environment carries workflow semantics. Current MedAgentBench cases are explicitly offline task replays until the official Docker FHIR runtime is available.

Model play is an orchestration layer over the same `ArenaService`, never a second simulator. Each OpenRouter response is parsed as a typed decision, checked against the current outcome catalog and dependency-aware available-action set, then applied through the same belief/action/finalization methods as physician play. Runs and complete provider transcripts are stored separately in `model_arena_runs` and `model_interactions`; model-only forest aggregation filters canonical sessions by `PlayerType.MODEL` so it cannot mix physician choices or the oracle into model statistics.
