# NSOS — agent instructions for this repo

Instructions for any coding agent (or human) working in this codebase.

## What this is

NSOS is a diagnostic engine for small and mid-sized firms: it ingests a firm's
data snapshot, runs question batteries per domain team, ranks findings in a
council, bundles them into 2–3 scored statements of work, and renders a
CEO-language report. Client-facing name: "Vinny". See `README.md` and
`docs/ARCHITECTURE.md` first, then `docs/STATE.md` (what is built) and
`docs/ROADMAP.md` (what is next).

## Layer ownership

| Layer | Purpose |
|---|---|
| `client/` | Tenant-specific code: onboarding, connector adapters, snapshots (gitignored except the synthetic example) |
| `engine/` | Reusable diagnostic intelligence: meta-level teams, council, SOW scoring, reasoning, gauntlets, router |
| `learning/` | Cross-run improvement: outcome flywheel, promotion gate |
| `presentation/` | Engine output → executive report, side-by-side, FDE handoff packet |
| `schemas/` | JSON contracts shared across layers |
| `web/` | Next.js surface (onboarding + diagnostic review); holds only a scoped token, never a connector secret |
| `mcp-servers/` | MCP servers (correction store, engine exposure) |
| `examples/` | Synthetic client used by tests and smoke runs |

## Rules

1. **Tests first for new code.** `python -m pytest -q` must stay green; the
   suite runs offline against `examples/synthetic-client-a` and
   `client/snapshots/synth-acme-services` with no API keys.
2. **Every number is grounded.** A finding or metric that carries `impact_usd`
   or `impact_hours` must carry a source trace and a confidence.
   `scripts/probes/grounded_numbers.py` enforces this and the tests run it.
3. **Every LLM call goes through `engine/router/nim_client.py`.** Do not import
   a second provider client elsewhere. Offline-deterministic modes
   (`NSOS_JUDGE_OFFLINE_DETERMINISTIC`, `NSOS_EVAL_OFFLINE_DETERMINISTIC`)
   exist for tests; production stays fail-closed.
4. **No tenant-specific code in `engine/`.** That belongs in `client/`.
5. **`presentation/` reads from `engine/` outputs; `engine/` never writes to
   `presentation/`.**
6. **No secrets in source, in `web/` client bundles, or in example files.**
   Everything comes from environment variables. `scripts/probes/pillar5_security.py`
   scans for hardcoded secrets.
7. **Operator identity is parameterized** (`OPERATOR_NAME`, `COMPANY_NAME`);
   never hardcode a person's name.
8. **Keep docs recursive to code.** Source changes under `engine/ client/ web/
   learning/ presentation/` should be reflected in `docs/STATE.md` or
   `docs/ROADMAP.md` in the same change (`scripts/check_docs_sync.py`).
9. **Architecture-level changes** (new provider, schema change, council weight
   change) get a decision record under `docs/decisions/` before the code.
