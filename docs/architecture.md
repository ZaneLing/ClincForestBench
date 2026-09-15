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

## Temporal Forest v2 local boundary

Credentialed sources under `dataset/restricted/` pass through three independent
adapters: `MCMEDTemporalAdapter`, `MIMICTemporalAdapter`, and
`EICUTemporalAdapter`. MIMIC-IV-Note, ECG, and ED are linked modalities of the
MIMIC adapter. The adapters first emit a canonical temporal event layer and
only then build Case bundles and graphs.

```text
restricted source tables
        │ source validation (schema / rows / null rate / join coverage)
        ▼
canonical temporal events
  order ┆ acquisition ┆ availability ┆ documentation
        │
        ├──► immutable realized trajectory
        ├──► review page + per-Case timeline Parquet
        └──► Temporal Tree / DAG
                state = visible observations + pending set + time bucket
```

An observed lab or imaging result may be replayed with its source-derived TAT,
but its value never changes. An action absent from the recorded episode keeps
its edge and resolves to `UNOBSERVED_IN_RECORDED_EPISODE`; it never invokes a
model to synthesize a result. MIMIC ECG clock uncertainty, eICU
interface-dependent missingness, and post-intervention exclusions are
first-class metadata. All record-level inputs and outputs remain Git-ignored
and are reachable only through research-key endpoints in the local API.
