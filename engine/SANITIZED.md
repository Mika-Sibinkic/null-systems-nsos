# Engine provenance

`engine/reasoning/`, `engine/router/` and `engine/gauntlets/` were lifted from an
earlier single-operator prototype and generalized for multi-tenant use. The
pipeline and its tests use `reasoning/reasoning_engine.py` (WWOD scoring),
`router/nim_client.py` (the only model client) and `gauntlets/quality_judge.py`
(the report quality gate).

Operator and company identity are parameterized rather than hardcoded:

| Variable | Default |
|---|---|
| `OPERATOR_NAME` | `Operator` |
| `COMPANY_NAME` | `the firm` |

Prompt templates use `{OPERATOR_NAME}` / `{COMPANY_NAME}` (or the `<OPERATOR>` /
`<COMPANY>` tokens) for substitution. Provider endpoints and data directories
come from environment variables (`NSOS_DIR`, `NSOS_DATA_DIR`, `NIM_API_KEY`).
