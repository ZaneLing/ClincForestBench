# MC-MED v1.0.1 local source

- Access class: credentialed/restricted clinical data.
- Local payload: approximately 1.2 GB.
- Tables present: `visits`, `pmh`, `meds`, `orders`, `labs`, `rads`, and
  `waveform_summary`.
- Intended benchmark role: emergency-department diagnostic trajectory and
  evidence-acquisition cases described in
  `docs/guides/Guidance3_MC-MED_eICU.md`.

The local snapshot includes patient/stay identifiers and patient-level
clinical events. No redistributable license file was present in the supplied
directory, so this repository applies the conservative rule: none of the raw
CSV tables are committed. Collaborators must obtain authorized access and
recreate this directory independently.
