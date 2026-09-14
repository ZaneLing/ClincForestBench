# MedAgentBench task dataset

Downloaded on 2026-09-08 from the official Stanford MedAgentBench repository.

- Project: https://github.com/stanfordmlgroup/MedAgentBench
- Paper: https://ai.nejm.org/doi/full/10.1056/AIdbp2500144
- Source directory: https://github.com/stanfordmlgroup/MedAgentBench/tree/main/data/medagentbench
- Pinned commit: `99260117137b09f04837a8c18d18a1107efa55ae`
- Upstream license: MIT; retained as `LICENSE.upstream`

Downloaded data files:

- `test_data_v1.json`: 100 benchmark tasks.
- `test_data_v2.json`: 300 benchmark tasks across the released task suite.
- `funcs_v1.json`: nine FHIR tool definitions.
- `web.html` and `final_web.html`: upstream task web resources.
- `README.upstream.md`: the repository documentation at the pinned commit.

The task JSON is only one part of the interactive benchmark. Reproducing the
official evaluation also requires the MedAgentBench FHIR server and the
official `refsol.py` referenced by the upstream documentation. Those runtime
components are not included in this dataset-only download.

Key SHA-256 checksums:

- `test_data_v1.json`: `b539a3dece8cf2fe0518bbfe76e47dec53e3676755c9bb6d87ff261b2aad856a`
- `test_data_v2.json`: `b6e89b2ef82f1bef27c5778a644a8a66c7b25738bbd6a48d03ab3e5182df6ca8`
- `funcs_v1.json`: `c977266db5eca75182c0d12cac1962b33ae6b5a54b9029ceb104e1a93b4c38c1`

