# MedPI MVP source

- Upstream dataset: `TheLumos/MedPI-Dataset` on Hugging Face.
- Dataset role: multi-turn patient-facing consultation and evaluation dimensions.
- Public release: 7,097 synthetic conversations across 366 patient profiles.
- MVP payload: patients, conversation metadata, full transcripts, and dimension
  catalog; the 161 MB score table is not required to build Case trees.
- Provenance URLs:
  - https://huggingface.co/datasets/TheLumos/MedPI-Dataset
  - https://arxiv.org/abs/2601.04195

The dataset card YAML says CC BY-SA 4.0 while its License section says CC BY-NC
4.0. Until the publisher resolves that conflict, ClincForestBench applies the
more restrictive non-commercial interpretation and does not redistribute rows.
