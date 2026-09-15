# Temporal Forest v2 MVP status

This implementation follows
[`ClincForestBench_Temporal_Forest_v2_Guide.md`](../ClincForestBench_Temporal_Forest_v2_Guide.md)
for the first local restricted-data slice.

| Guide phase | MVP implementation |
| --- | --- |
| 1. Source validation | Three independent validators report file presence, schema, row count, temporal-field null rate, and key join coverage. |
| 2. Dataset adapters | `MCMEDTemporalAdapter`, `MIMICTemporalAdapter`, `EICUTemporalAdapter`, `PMCTemporalAdapter`, and `NEJMTemporalAdapter` implement candidate listing and canonical Case construction. MIMIC Note, ECG, and ED are linked modalities. PMC/NEJM are explicitly labeled narrative-sequence extensions. |
| 3. Canonical event layer | Every event keeps distinct order, acquisition, availability, documentation, start, and end fields plus relative minutes and confidence. |
| 4. Candidate scoring | Local candidate reports retain evidence/modality counts and the adapter-specific eligibility screen. |
| 5. Human review | Every selected Case has a standalone `review.html`. Medical adjudication is still a manual gate and is not marked complete by code. |
| 6. Temporal engine | `TemporalReplayEnvironment` preserves pending/TAT semantics for offline replay. The doctor/model Arena executes each clinical action synchronously, advances simulation time to the source-backed availability point, captures a new belief checkpoint, and never imposes wall-clock waiting. |
| 7. Graph builder | Every Case has a realized Temporal DAG with separate action/result nodes and latency edges; temporal state hashing includes visible evidence, pending actions, and a five-minute time bucket. |
| 8. MVP test | Each of the 40 Cases includes `FAST_TARGETED`, `BROAD_WORKUP`, and `CONTEXT_FIRST` engineering paths; all report zero synthetic results. |
| 9. Export | Local outputs include canonical Case/Event Parquet, per-Case JSON/Parquet/HTML, a manifest, summary, and graph index. |

## Local MVP inventory

- 10 MC-MED chest-pain presentation Cases.
- 10 MIMIC acute respiratory/infection admission Cases using the main,
  Note, ECG, and ED sources when linked.
- 10 eICU early-assessment Cases using ICU-admission offsets.
- 5 PMC patient-narrative Case MVPs.
- 5 NEJM CPC PubMed-record Case MVPs.

The browser route `/temporal?mode=arena` is a doctor-playable Arena: submit S0,
choose a concrete question/exam/test, receive its source-backed result in the same
request while simulation time advances, update the ranked differential, and finalize. `/research?mode=temporal` exposes raw source,
the canonical conversion trace, and the full graph. `/temporal?mode=timeline`
keeps the deterministic source-trajectory player. Imaging reports live inside
their result nodes. MIMIC ECG clock uncertainty, eICU interface-dependent
missingness, and post-intervention exclusions remain visible rather than being
silently normalized away.

The same 40-Case manifest is now the single source for every working module:
`/research?mode=temporal` (raw-to-tree audit), `/forest?mode=temporal`
(checkpoint/action distributions), `/history?mode=temporal` (the signed-in
doctor's completed runs), `/evidence` (dataset contracts and field mapping), and
`/model-arena?mode=temporal` (OpenRouter ACTION/FINAL simulation).

## Deliberate first-slice limits

- The 40 generated Cases and doctor-session artifacts are local derivatives and are not tracked
  in Git.
- Review pages are generated, but a clinician must still adjudicate each
  reference and presentation-section extraction before a formal benchmark
  release.
- Temporal doctor sessions persist locally and completed Case review includes
  the player's path, source reference graph, and aggregate top-1 distribution.
- PMC and NEJM lack complete EHR timestamp semantics. Their LOW-confidence
  minute values are source-order display proxies, not elapsed clinical time;
  they remain provisional until clinician adjudication.
- Tree screenshots are not generated in ETL; the interactive React Flow canvas
  is the current visual review artifact.
