# Converted case example

`DDX_TEST_0021752.readable.json` is a human-readable projection generated from the first MVP-50 case. It shows the exact input identity, deterministic initial presentation, positive clinical findings, oracle diagnosis/differential and the location of the full 223-field dense truth bundle.

It is research-side data. Never expose it to a player before session completion.

All runnable cases now use unordered evidence access. The 58 additional source
examples are generated locally under `data/processed/evidence/v1/case_bundles/`
by `make preprocess-evidence`; each contains `case.json`, `raw.json`, and
`tree.json`. Their action/result branches have no simulation clock, waits, or
source sequence unlocking. Source dates remain clinical history or provenance.
Inspect them through the unified `/research` and `/evidence` pages.
