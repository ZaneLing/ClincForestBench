# Visit / examination / inquiry protocol

[English](encounter_protocol.md) | [简体中文](encounter_protocol.zh-CN.md)

The physician Arena at `/arena` now uses a shared clinical catalog across all
locally generated tracks. A visit begins with demographics and presentation.
The physician can investigate immediately or record a diagnosis at any time.

## Libraries and source mapping

The versioned base libraries live in `configs/clinical_operations.tsv` and
`configs/clinical_inquiries.tsv`. Operations cover laboratory testing, imaging,
pathology, microbiology, physical examination, endoscopy, sampling, and specialty
investigations. Inquiries cover symptom characterization, systems review,
medical/family/social history, medication/allergy, exposures, reproductive and
pediatric history, and patient preferences. Source-native items extend these
libraries at load time. The current 188-case local inventory produces **309
operations and 397 inquiries**; counts change with source manifests.

These are broad, extensible research catalogs, not an assertion that a finite
list includes every hospital's orderables. New items require stable IDs and
English/Chinese names. Exact source synonyms are maintained in
`configs/clinical_aliases.tsv`. The separation of requests, results and answers
follows the concepts in [FHIR ServiceRequest](https://hl7.org/fhir/R4B/servicerequest.html),
[DiagnosticReport](https://fhir.hl7.org/fhir/diagnosticreport.html), and
[QuestionnaireResponse](https://hl7.org/fhir/questionnaireresponse.html).
Clinical domains follow the breadth described by the [LOINC scope](https://loinc.org/kb/users-guide/introduction/scope-of-loinc).
Internal IDs are not claimed to be licensed LOINC or SNOMED CT codes.

Catalog content is independent of the selected case. It does not show whether
that case has an answer. Private bindings connect items to original evidence or
event IDs and preserve provenance. Matching uses exact source IDs, exact labels,
and explicit aliases; unmatched safe native labels remain distinct. Narrative
report excerpts use generic recorded-report/history items, so result text does
not become a menu label. These coarse narrative mappings still need clinical
review before fine-grained scoring. Reference diagnoses and upstream-ineligible
events are retained in the audit as reference-only rather than actionable evidence.

DDXPlus negatives and default values keep their source semantics. A missing
record is never synthesized as a negative result. Panel expansion returns only
recorded components and marks partial panels. Repeat temporal investigations
use the first mapped source result; later results remain identified in the audit.
This visit protocol does not simulate treatment effects or elapsed clinical time.
The original temporal timeline remains available at `/temporal?mode=timeline`.
Synthea's diagnosis-bearing encounter reason is omitted from the new opening
visit; its recorded vitals are retrievable as an operation. MedAgentBench FHIR
request templates are explicitly identified as offline workflow instructions.

## Decision capture

Selecting an examination or inquiry opens five possible reasons before the
result is retrieved: support a suspected diagnosis, distinguish alternatives,
assess urgency, assess severity/treatment suitability, or another reason. The
last option requires free text. Item/domain-specific reason profiles (for example,
CBC, ECG, imaging, symptoms and medication history) live in
`configs/clinical_reasons.json`. Additional explanation and a suspected diagnosis
can be recorded for any choice. Options are deterministic and use the chosen
item, never hidden outcomes. They are prompts for physician self-report, not
inferred physician reasoning. Exports retain the exact offered options, selected
reason, free text, current diagnoses, timestamps, source result and catalog version.

An unrecorded operation **or inquiry** immediately sets `TERMINATED_MISSING_RESULT`
and persists the attempted action, reason, and preceding trajectory. The event
returns `NOT_RECORDED`; the session then rejects further mutations. Recorded
results are shown immediately, with a control to choose the next inquiry or exam.
Recorded negatives and non-applicable answers do not terminate a visit.

During an active visit, diagnosis can be selected from the shared disease list or typed freely. It can
be revised and does not immediately close the visit. Cases with source treatment
records offer an optional prescription/treatment-plan field after diagnosis.
Completing a visit requires a diagnosis but never requires a prescription.
Prescriptions record the physician's plan; the application does not execute it.

## Persistence, history and analysis

The Case Inspector (`/research`) uses the same inquiry/operation catalog and
source bindings as the Arena. After selecting a case, recorded questions and
answers appear directly in two color-coded columns: teal inquiries and violet
examinations/procedures. Mobile screens switch between the two groups. Long
content is paginated without page scrolling. Missing items, source IDs, coverage
statistics, treatment panels and audit controls are not displayed. Partial panels
retain their qualifier and component names. Both languages share the Arena result
renderer and localization. The inspector is read-only and never changes visits.
`GET /research/encounter-cases` and `GET /research/encounter-cases/{case_id}`
require research access; the physician catalog still does not reveal availability.

New encounters are stored in local `data/encounters.db` (ignored by Git), separate
from the original account/session database. Transactions serialize mutations;
client event IDs make retries idempotent. Access is bound to the authenticated
owner. `/history` supports reopening active visits and viewing ended visits;
the browser retains the latest encounter across refreshes and language switches.
The JSON export preserves original source text and physician-authored text.
`/forest` groups visits by case, action, selected reason and result state, behind
the research key. Legacy history/forest views remain under `?mode=classic` and
`?mode=temporal`. Model Arena still uses its existing protocol; new physician
trajectories must not be pooled with those runs as if the protocols were identical.

`/research/encounter-mapping` provides the private mapping audit.
`/research/encounter-forest` provides the aggregate forest. The following command
writes a local mapping and bilingual coverage report without external calls:

```bash
make audit-encounters
```

The report is saved at `data/analysis_runs/encounter_mapping_audit.json`. It
distinguishes visit, mapped evidence, treatment, later result, and reference-only
records. Dictionary/script coverage is checked for both English and Chinese;
this does not replace clinical translation review. Existing restricted-data
translation overlays stay local. Run `make validate` for regression tests,
frontend lint, and production build.
