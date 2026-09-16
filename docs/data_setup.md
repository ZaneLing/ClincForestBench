# Dataset setup

The repository deliberately excludes large source payloads, generated case
bundles, local databases, model weights, credentials, and dependency caches.
Use the root downloader after cloning:

```bash
git clone https://github.com/ZaneLing/ClincForestBench.git
cd ClincForestBench
./download_data.sh
```

The default `all` profile downloads public core sources plus the smaller
interaction MVP input. Downloads are resumable, existing non-empty files are
skipped, Synthea is checksum-verified, and its CSV archive is extracted.

## Profiles

```bash
./download_data.sh core
./download_data.sh interaction
./download_data.sh all
./download_data.sh all --force
```

`core` restores DDXPlus, Synthea, PMC-Patients, Clinical Guidelines,
NEJM/PubMed CPC metadata, and any missing MedAgentBench release files.
`interaction` restores the source slice used by MediScope, MedPI, the public
PatientSim demo, Meddies Persona VIE, MedMemoryBench, and MedDialogRubrics.

The public download is roughly 2 GB. Upstream hosts may change files or impose
rate limits; source URLs and license notes live under each dataset directory.
Patient-level and license-ambiguous interaction rows remain local even when
their download is technically public.

## Credentialed datasets

MC-MED, eICU-CRD, MIMIC-IV, MIMIC-IV-ED, MIMIC-IV-Note, MIMIC-IV-ECG, and the
full PatientSim release require independent PhysioNet approval. Once the
account has accepted each resource agreement, configure a private
`~/.netrc` for `physionet.org` (recommended) or export
`PHYSIONET_USERNAME`, then run:

```bash
./download_data.sh restricted
```

This mode is intentionally separate because it is large and governed by data
use agreements. The script never stores credentials in the repository and the
downloaded records are covered by `dataset/restricted/**` or the interaction
ignore policy. Access approval—not possession of this code—determines whether
PhysioNet serves those files.

## Build generated benchmark artifacts

After data download and environment setup:

```bash
make setup
make preprocess-all
make validate
```

Generated artifacts are written beneath `data/processed/` and can always be
rebuilt from the source directories. They are not synchronized through Git.
