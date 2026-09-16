# Consultation, persona, memory, and expert-action MVP

This slice adds six source adapters to the existing Temporal Forest v2 state
machine. It is deliberately small: three locally generated Case trees per
dataset, 18 Cases total. They automatically appear in Case 查看, human Arena,
model Arena, history, forest analytics, and the dataset/rules center because
those modules consume the shared Temporal manifest.

| Dataset | MVP input | Tree meaning | Reference strength |
| --- | --- | --- | --- |
| MediScope | PulseMind `MedDiagnose.parquet` dialogue + JPEG | report review and source-authored doctor/patient turns | dialogue conclusion proxy |
| MedPI | patients, conversation metadata, message JSONL, dimensions | source doctor question → next source patient message | synthetic encounter-reason label |
| PatientSim | official repository's three demo profiles | fixed profile question → published field answer | demo profile diagnosis |
| Meddies Persona VIE | 12 Dataset Viewer rows | Vietnamese symptom/persona fields as inquiry branches | chronic-condition profile codes |
| MedMemoryBench | five English core Parquet tables | real source dates, strictly sequential event reveal | synthetic persona disease type |
| MedDialogRubrics | public v1 Excel workbook | expert inquiry criterion → matched case-record fact | expert-refined synthetic case label |

## Reproduce

```bash
make preprocess-temporal
./download_data.sh interaction
make preprocess-interaction-mvp
```

The download script uses resumable HTTP downloads, a shallow clone for the
PatientSim public code/demo, and records local SHA-256 hashes. The build merges
the 18 Case bundles into the existing manifest and rewrites canonical Case and
Event Parquet tables.

## Safety and fidelity rules

- Consultation and persona action catalogs are Case-scoped. A question from one
  source conversation can never reveal an answer from a different patient.
- No adapter calls an LLM to invent a patient response. `patient_answer` is
  rendered as a natural-language clinical block in the Arena.
- MedMemoryBench exposes only the next unreviewed dated event. Clicking it
  advances simulated time synchronously; no wall-clock wait occurs.
- MediScope stores the source JPEG beside its local Case bundle and displays it
  in Arena and Case 查看. The media endpoint rejects non-public Cases and path
  traversal.
- MedDialogRubrics uses deterministic character-overlap matching to bind an
  expert inquiry to one source-record fact. The score and method remain in the
  node; unmatched criteria return an explicit “not recorded” message and need
  clinician review before formal scoring.
- `is_absolute_ground_truth` is false for every new MVP. The UI must not imply
  that conversation conclusions, persona labels, or profile codes are
  independently adjudicated diagnoses.

## Access and license boundaries

PatientSim's complete patient data requires a credentialed PhysioNet account
and signed DUA, so this repository downloads only the official public demo.
MedPI and MedMemoryBench currently publish conflicting license statements in
their upstream metadata; MedDialogRubrics does not declare a dataset license.
The implementation therefore keeps all downloaded rows and generated
patient-level bundles local and Git-ignored. Source URLs and the conservative
interpretation are recorded under `dataset/interaction/*/README.source.md`.
