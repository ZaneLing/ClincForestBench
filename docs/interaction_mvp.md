# Interaction evidence MVP

Six public source adapters contribute three cases each: MediScope, MedPI,
PatientSim, Meddies Persona VIE, MedMemoryBench, and MedDialogRubrics. They
join the other source episodes in the unified unordered evidence catalog.

```bash
make download-interaction-mvp
make preprocess-ehr-sources
make preprocess-interaction-mvp
```

The last command merges source inputs and runs `etl.build_evidence_cases`.
Generated runnable bundles and trees live under `data/processed/evidence/`.
The `evidence_mvp58` manifests include all 58 additional source cases. The
legacy source staging format is an ingestion implementation detail.

Consultation questions return source-authored answers. Persona and memory
questions return case-scoped profile facts or records. Rubric questions return
matched source facts. Each result is fixed and immediately available regardless
of prior evidence choices. MedMemoryBench has no sequential event unlocking.
Missing clinical answers are never generated.

Source patient histories and dates remain clinical content or provenance.
MediScope media is accessible only for an explicitly public source and a
filename confined to the selected case. References remain protected during
play, with unadjudicated and proxy quality labels retained in completed review.

Use `/arena`, `/model-arena`, `/research`, `/history`, and `/forest` for all
datasets. There is no separate source timeline or temporal mode.
