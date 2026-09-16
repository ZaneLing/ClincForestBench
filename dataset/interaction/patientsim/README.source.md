# PatientSim MVP source

- Upstream project: `dek924/PatientSim`.
- Dataset role: persona-controlled, multi-turn doctor-patient simulation.
- Official patient-level dataset: PhysioNet `persona-patientsim/1.0.0`.
- Access boundary: credentialed PhysioNet account and signed DUA required.
- MVP payload: public source code plus the repository's published demo profile,
  when present. The adapter never substitutes MIMIC rows for the official
  PatientSim release or fabricates a private dataset download.
- Provenance URLs:
  - https://github.com/dek924/PatientSim
  - https://physionet.org/content/persona-patientsim/1.0.0/
  - https://arxiv.org/abs/2505.17818

Place an authorized PatientSim export under this directory to expand beyond the
public demo. Credentials and DUA-protected data must never be committed.
