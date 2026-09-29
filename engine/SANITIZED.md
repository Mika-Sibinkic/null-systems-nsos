# Engine provenance

The modules under `engine/reasoning/`, `engine/gaps/`, `engine/prediction-residual/`,
`engine/vector-index/`, `engine/cascade-handler/`, `engine/router/` and
`engine/gauntlets/` were lifted from an earlier single-operator prototype and
generalized for multi-tenant use.

Operator and company identity are parameterized rather than hardcoded:

| Variable | Default |
|---|---|
| `OPERATOR_NAME` | `Operator` |
| `COMPANY_NAME` | `the firm` |

Prompt templates use `{OPERATOR_NAME}` / `{COMPANY_NAME}` (or the `<OPERATOR>` /
`<COMPANY>` tokens) for substitution. Provider endpoints and data directories
come from environment variables (`NSOS_DIR`, `NSOS_DATA_DIR`, `NIM_API_KEY`, ...).

Optional knowledge files, read with safe fallbacks if absent:

- `engine/router/knowledge/project_map.json` — `{ "lowercase_keyword": "Folder Name" }`
- `engine/router/knowledge/project_contexts.json` — list of `{project, context, tech}`
- `engine/reasoning/tier_config.json` — `{ "model_tiers": {...}, "tier_definitions": {...} }`
