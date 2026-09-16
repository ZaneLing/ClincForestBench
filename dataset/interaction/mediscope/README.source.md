# MediScope MVP source

- Upstream dataset: `AQ-MedAI/PulseMind` on Hugging Face.
- Dataset role: multimodal, multi-turn diagnostic consultation.
- Published license metadata: MIT.
- Public release boundary: the card describes a curated subset rather than the
  98,000-consultation collection reported in the paper.
- MVP payload: dataset card, text-only consultation JSON, and one official
  MedDiagnose Parquet shard so a small number of image-backed cases can be
  extracted locally.
- Provenance URLs:
  - https://huggingface.co/datasets/AQ-MedAI/PulseMind
  - https://arxiv.org/abs/2601.07344

The Parquet file is large and remains untracked. Extracted images and case-level
JSON are also local-only artifacts.
