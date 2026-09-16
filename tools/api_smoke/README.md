# API smoke tests

These optional scripts check external OpenRouter and OrcaRouter connectivity;
they are not part of the automated `tests/` suite.

```bash
python -m venv .venv
.venv/bin/python -m pip install -r tools/api_smoke/requirements.txt
cp tools/api_smoke/.env.example tools/api_smoke/.env
.venv/bin/python tools/api_smoke/test_openrouter_api.py
```

Put only the required provider keys in `tools/api_smoke/.env`. The file is
Git-ignored and must never be committed.
