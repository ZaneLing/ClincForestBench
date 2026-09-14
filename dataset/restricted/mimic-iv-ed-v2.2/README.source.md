# MIMIC-IV-ED v2.2 local source

- Access class: PhysioNet credentialed health data.
- Local payload: approximately 116 MB.
- Tables present: `edstays`, `diagnosis`, `medrecon`, `pyxis`, `triage`, and
  `vitalsign` under `ed/`.
- Integrity metadata: upstream `SHA256SUMS.txt` retained.
- Documentation/license: upstream `README.txt` and PhysioNet Credentialed
  Health Data License 1.5.0 retained.
- Intended benchmark role: emergency-department presentation, evidence,
  treatment, and disposition trajectories.

All patient-level `*.csv.gz` files remain local and are excluded from Git.
Repository users must obtain their own credentialed PhysioNet access.
