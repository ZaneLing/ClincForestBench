# MIMIC-IV-ECG local table snapshot

- Access class: treated as PhysioNet credentialed health data.
- Local payload: approximately 298 MB.
- Tables present: record list, machine measurements, waveform-note links, and
  the machine-measurements data dictionary.
- Version: not encoded in the supplied local directory; pin it before building
  a released benchmark adapter.
- Intended benchmark role: ECG interpretation and linkage to longitudinal
  MIMIC-IV context.

No license file accompanied this local snapshot. Because its subject and study
identifiers link to MIMIC-IV, all record-level CSV tables are excluded from
Git. Only this source note and the non-patient data dictionary may be tracked.
