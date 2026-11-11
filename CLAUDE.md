# NSOS: agent instructions for this repo

Instructions for any coding agent (or human) working in this codebase.

## What this is

NSOS is a diagnostic engine for small and mid-sized firms: it reads a firm's
data snapshot, turns it into grounded findings (one team today, financial),
ranks them, bundles them into 2 to 3 scored statements of work, and renders a
report in the owner's language. The report prints the name "Vinny". Read
`README.md` first; its Status and Limits sections are the one record of what
is built.

## Layer ownership

| Layer | Purpose |
|---|---|
| `client/` | Tenant-specific code: onboarding, connector adapters, snapshots (gitignored except the synthetic example) |
| `engine/` | Reusable diagnostic logic: the financial team (`meta_levels/`), council, SOW scoring, quality judge, NIM client, HTTP API |
| `learning/` | Cross-run improvement: outcome ledger |
| `presentation/` | Engine output → executive report, side-by-side, FDE handoff packet |
| `schemas/` | `baseline.json`, the tenant snapshot contract |
| `web/` | Next.js onboarding demo; holds only a scoped token, never a connector secret |
| `mcp-servers/` | Correction MCP server, a separate tool the diagnostic does not use |
| `examples/` | Synthetic client used by tests and smoke runs |

## Rules

1. **Tests first for new code.** `python -m pytest -q` must stay green; the
   suite runs offline against `examples/synthetic-client-a` and
   `client/snapshots/synth-acme-services` with no API keys.
2. **Every number is grounded.** A finding or metric that carries `impact_usd`,
   `impact_hours` or `exposure_usd` must carry a source trace and a confidence.
   `scripts/probes/grounded_numbers.py` enforces this and the tests run it.
3. **Every LLM call goes through `engine/router/nim_client.py`.** Do not import
   a second provider client elsewhere. Offline-deterministic modes
   (`NSOS_JUDGE_OFFLINE_DETERMINISTIC`) exist for tests and the demo; production stays fail-closed.
4. **No tenant-specific code in `engine/`.** That belongs in `client/`.
5. `presentation/` reads from `engine/` outputs; `engine/` never writes to
   `presentation/`.
6. **No secrets in source, in `web/` client bundles, or in example files.**
   Everything comes from environment variables. `scripts/probes/pillar5_security.py`
   scans for hardcoded secrets.
7. **Operator identity is parameterized** (`OPERATOR_NAME`, `COMPANY_NAME`);
   never hardcode a person's name.
8. **Keep the README honest.** When a change makes its Status, Limits or
   numbers wrong, fix them in the same change.
9. **Architecture-level changes** (new provider, schema change, council weight
   change) get a decision record under `docs/decisions/` before the code.
