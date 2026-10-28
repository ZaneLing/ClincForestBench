# Source evidence MVP status

The runnable benchmark uses **unordered evidence**. The model chooses which
recorded question or examination result to acquire next.

The shared target is 30 cases per dataset, or 420 cases across 14 tracks.
The current catalog contains 393 cases: DDXPlus 30, Synthea 30,
MedAgentBench 30, plus 303 source cases from MC-MED, MIMIC-IV, eICU-CRD, PMC Case
Reports, NEJM CPC, MediScope, MedPI, PatientSim, Meddies Persona VIE,
MedMemoryBench, and MedDialogRubrics.

Thirteen tracks have 30 cases each. PatientSim has only three available public
demo profiles; its 27-case gap requires an authorized PhysioNet export.
See [dataset quotas and sampling units](dataset_quota.md) for the precise counting
units and rebuild instructions.

Each converted source case contains initial patient information, independent
action/result branches, protected references, reference-quality metadata, and
private source provenance. The player or model chooses evidence order; each
action returns its fixed recorded result immediately. There are no clocks,
waits, time scores, sequential unlocks, or source chronology replay.

All cases are available through `/arena`, `/model-arena`, `/research`,
`/forest`, and `/history`.

Rebuild source readers with `make preprocess-ehr-sources`, then run
`make preprocess-interaction-mvp` to merge public interaction inputs and
convert the complete source slice. If staging inputs already exist,
`make preprocess-evidence` regenerates unordered cases directly.

Original patient records, dates, source uncertainty, and unpublished derivatives
remain local. Conversion changes evidence-access semantics, not patient facts.
Proxy and unadjudicated reference labels remain marked as such; clinical
adjudication and large-scale model evaluation are still pending.
