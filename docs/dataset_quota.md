# Dataset case quota

The shared target is **30 runnable cases per track**, or **420 cases across
14 tracks**, configured in `configs/dataset_quota.yaml`. The aggregate inventory
in `data/manifests/dataset_inventory.json` records actual counts and explicit
shortfalls. A build fails on a shortfall by default. `--allow-shortfall` keeps
available source-backed cases and records the unmet quota; it does not pad cases.

Cases are examples, not necessarily independent patients:

- MedPI selects distinct completed diagnosis conversations, prioritizing one
  conversation per patient profile before selecting additional conversations.
- MedMemoryBench selects disjoint windows of up to 31 source events: one initial
  event plus up to 30 freely queryable records. Windows can share a persona, but
  their source events do not overlap. This is static history acquisition, with
  no time-dependent unlocking.
- NEJM CPC uses open clinical presentation sections from authentic NEJM articles
  hosted by PMC, followed by eligible PubMed abstracts. Final diagnosis sections
  remain protected reference data. Abstract-only cases retain proxy reference
  quality labels. `make download-nejm-open` downloads the open source texts.
  Public reading access does not imply a redistribution license; NEJM narratives
  and their display translations remain local.
- PatientSim uses the official public demo when no authorized full export exists.
  Put the authorized PhysioNet `patient_profile.json` at
  `dataset/interaction/patientsim/patient_profile.json` to build the full quota.
  These profiles and their derivatives remain local and restricted.

MedDialogRubrics has no declared data redistribution license. Its case text and
translation overlays remain local as well.

To build all currently accessible evidence and report any missing sources:

```bash
make preprocess-ddxplus preprocess-workflows
make download-nejm-open
.venv/bin/python -m etl.build_ehr_sources --allow-shortfall
.venv/bin/python -m etl.build_interaction_mvp --allow-shortfall
make preprocess-evidence
.venv/bin/python tools/update_dataset_inventory.py
```

Full source validation is enabled by default. Clinical review of provisional
diagnoses and deterministic action mappings remains necessary. Duplicate source
identities and overlapping memory evidence are checked by `tests/test_dataset_quota.py`.

Manifest filenames are independent of sample counts. Historical dataset revision
identifiers remain stable so unchanged cases retain their hashes and recorded
play histories. No duplicate version directories are created.

For new display translations, install `.[offline-translation]` and the Argos
English-to-Chinese, Chinese-to-English and Vietnamese-to-English packages.
Then run `.venv/bin/python -m tools.build_offline_case_translations`.
The model packages are downloadable resources; inference runs locally and
patient text is never sent to a translation provider. Generated translations
are display overlays and still require clinical review.
