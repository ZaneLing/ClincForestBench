# MIMIC-IV v3.1 local source

- Access class: PhysioNet credentialed health data.
- Local payload: approximately 37 GB.
- Tables present: hospital and ICU modules under `3.1/`.
- Intended Temporal Forest role: admission anchor, diagnoses, provider orders,
  laboratory acquisition/availability times, and intervention context.

All patient-level files remain local and are excluded from Git. The Temporal
v2 ETL writes record-level derivatives only under the ignored
`data/processed/temporal/v2/` directory.
