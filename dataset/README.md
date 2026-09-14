# Medical datasets

Downloaded or refreshed through 2026-09-08. These files are research data,
not a source of clinical advice.

## `synthea/`

Official Synthea CSV sample data with 1,171 synthetic patients. The original
ZIP is retained and extracted into 16 linked CSV tables under `csv/`.

- Project: https://github.com/synthetichealth/synthea
- Sample data: https://synthetichealth.github.io/synthea/
- Synthea describes the generated records as synthetic, with no real patient
  privacy restrictions.

## `medagentbench/`

The official Stanford MedAgentBench task data, pinned to upstream commit
`99260117137b09f04837a8c18d18a1107efa55ae`. It includes the 100-task v1 and
300-task v2 JSON releases, FHIR tool definitions, and task web resources.

- Repository: https://github.com/stanfordmlgroup/MedAgentBench
- Paper: https://ai.nejm.org/doi/full/10.1056/AIdbp2500144
- License in the upstream repository: MIT

## `ddxplus/`

English DDXPlus synthetic differential-diagnosis data in Parquet format,
plus the official condition/evidence metadata.

- Upstream project: https://github.com/mila-iqia/ddxplus
- Official release: https://figshare.com/articles/dataset/DDXPlus_Dataset_English_/22687585
- Download mirror used because Figshare returned HTTP 403 from this network:
  https://huggingface.co/datasets/aai530-group6/ddxplus
- License reported by the upstream project: CC BY 4.0
- Expected rows: 1,025,602 train; 132,448 validation; 134,529 test

## `pmc_case_reports/`

PMC-Patients contains 167,034 patient summaries extracted from PubMed
Central case reports.

- Dataset: https://huggingface.co/datasets/zhengyun21/PMC-Patients
- Project: https://github.com/pmc-patients/pmc-patients
- License reported by the dataset card: CC BY-NC-SA 4.0

## `nejm_cpc/`

PubMed bibliographic metadata for the query
`Case Records of the Massachusetts General Hospital[Title]`. The directory
contains the ESearch response and 3,279 PubMed records in XML.

- Source: https://pubmed.ncbi.nlm.nih.gov/
- API: https://www.ncbi.nlm.nih.gov/books/NBK25501/

NEJM article full text is not included. PubMed indexing does not grant rights
to redistribute the corresponding copyrighted NEJM articles.

## `clinical_guidelines/`

The EPFL/Meditron Clinical Guidelines corpus: 37,970 documents from nine
sources that the dataset authors identified as permitting redistribution.
The local copy uses two Parquet shards.

- Dataset: https://huggingface.co/datasets/epfl-llm/guidelines
- Repository: https://github.com/epfLLM/meditron
- Dataset card license field: Common Crawl Foundation Terms of Use

Review the source dataset cards and per-source terms before redistribution or
commercial use.

## `restricted/`

Credentialed or conservatively restricted patient-level datasets. The local
workspace contains MC-MED v1.0.1, eICU-CRD v2.0, MIMIC-IV-ED v2.2, and a
MIMIC-IV-ECG table snapshot. Their raw payloads are excluded from Git and must
not be shared with collaborators who have not independently obtained access.

See [`restricted/README.md`](restricted/README.md) for the local directory map,
access boundaries, and reproducibility metadata retained in the repository.
