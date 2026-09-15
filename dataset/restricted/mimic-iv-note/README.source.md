# MIMIC-IV-Note v2.2 local source

- Access class: PhysioNet credentialed health data.
- Local payload: approximately 5.1 GB.
- Tables present: discharge and radiology notes under `2.2/note/`.
- Intended Temporal Forest role: reviewed pre-admission presentation sections
  and radiology report availability proxies.

Discharge summaries are retrospective documents. Only explicitly parsed
pre-admission/presentation sections may inform S0, and every MVP case remains
marked for human review. Raw and generated record-level content is not tracked.
