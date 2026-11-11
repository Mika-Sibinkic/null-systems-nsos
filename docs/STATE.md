<a id="top"></a>
# STATE: what is built

> Single source of "where we are." Updated on every milestone merge (see [UPDATE-PROTOCOL](./UPDATE-PROTOCOL.md)).
> Status words: **built** (code and tests exist) · **partial** (exists, not wired end to end) · **planned** (empty) · **external** (outside service).
> Last updated: 2026-11-11 (launch pass).

<a id="summary"></a>
## One-line summary

The whole path runs end to end on one fabricated QuickBooks fixture (`examples/synthetic-client-a`):
QuickBooks adapter → `baseline.json` → scoped-token onboarding and teaser → financial team findings,
each `impact_usd` source-traced and confidence-banded → council ranking → two or three scored SOW
candidates → owner-facing report, side-by-side and FDE handoff packet → outcome ledger.
`tests/test_e2e_synthetic.py` runs it, and `python scripts/run_synthetic.py` writes every artifact under `runs/synthetic-client-a/`. Vendor concentration, customer concentration and overdue AR
count as exposure and stay out of annual impact ([decision](./decisions/2026-11-11-exposure-is-not-impact.md)).
Five of six domain teams, non-QuickBooks connectors and the review page's engine routes are not built.

<a id="engine"></a>
## Engine

| Component | State | Path | Notes |
|---|---|---|---|
| Council (pairwise judge + Borda) | built | `engine/council/council.py` | deterministic judge fallback for tests |
| Recursive-weight scoring | built | `engine/council/recursive_weights.py` | 0.30 prio + 0.25 novelty + 0.20 corrob + 0.25 impact, z-normed $/hrs |
| Reasoning engine (lifted) | built | `engine/reasoning/reasoning_engine.py` | `predict()` backs WWOD SOW scoring |
| NIM client (lifted, only model client) | built | `engine/router/nim_client.py` | `judge_pair` for council; live path untested without a key |
| Engine HTTP API (FastAPI) | built | `engine/api/app.py` | `GET /health`, `GET /teaser` (scoped token, per-tenant authz), dev-only `POST /dev/scoped-token` (404 once `VINNY_TOKEN_SECRET` is set); `require_live_model` fails closed 503 without `NIM_API_KEY`; `python -m engine.api` |
| Meta-teams: financial | built | `engine/meta-levels/financial/` | question battery (`questions.jsonl` + `team.py`), data→findings engine (`findings.py`); in-engine grounding gate (fail-closed); FDE-review gate (`review_gate.py`) |
| Meta-teams: other 5 | planned | `engine/meta-levels/{operational,organizational,customer,technology,strategic}/` | empty |

<a id="harness"></a>
## CI and governance

| Component | State | Path | Notes |
|---|---|---|---|
| Promotion gate (5-gate) | partial | `learning/promotion-gate/promotion_gate.py` | reads `runs/latest-gauntlet-score.json` and `runs/perf-delta.json`, which are produced outside the repo |
| Quality judge (3-layer) | built | `engine/gauntlets/quality_judge.py` | |
| GitHub Actions CI | built | `.github/workflows/ci.yml` | pytest (3.11, 3.14), secret scan, demo run diffed against `examples/`, engine API smoke; web audit, typecheck, `npm test`, build; MCP server audit and stdio smoke. Not yet run on GitHub |
| docs_sync gate | built | `scripts/check_docs_sync.py` | fails on source-vs-docs drift; `[skip-docs-sync]` override; CI runs it on pull requests |
| Unit tests | built | `tests/` | `python -m pytest -q`, offline, no keys |
| Quality judge offline-deterministic fallback | built | `engine/gauntlets/quality_judge.py` | opt-in `NSOS_JUDGE_OFFLINE_DETERMINISTIC=1`; prod stays fail-closed ([decision](./decisions/2026-06-02-offline-deterministic-quality-judge.md)) |

<a id="client"></a>
## Client ingestion

| Component | State | Path |
|---|---|---|
| Onboarding flow | built | `client/onboarding/onboarding.py`: connect → server-side secret → snapshot → scoped web token |
| Scoped-token auth | built | `client/onboarding/auth.py`: HMAC scoped token, per-tenant authz, secrets stay server-side |
| QuickBooks adapter | built | `client/adapters/quickbooks.py`: read-only QB export → `baseline.json` (schema-valid) |
| Connectors (HubSpot, Slack, Pocket) | planned | `client/adapters/`: QuickBooks only so far |
| Tenant snapshots | built | `client/snapshots/{tenant}/baseline.json` + `schemas/baseline.json` |
| <1h teaser signal | built | `engine/teaser/teaser.py`: one grounded finding from the snapshot |

<a id="sow"></a>
## SOW output, scoring and presentation

| Component | State | Path |
|---|---|---|
| Exec report generator | built | `presentation/exec-report/report_generator.py`: `render_sow_report` renders the scored SOWs side by side; passes the quality_judge gate |
| SOW assembly (bundle findings → 2–3 candidates) | built | `engine/sow/assembly.py`: thrust taxonomy, impact-weighted confidence, source-traced union |
| WWOD SOW scoring | built | `engine/sow/wwod_score.py`: `predict()` policy + deterministic deal-quality prior; cold start falls back to the prior; confidence + gaps[] |
| 5-pillar deployability grade | partial | `engine/sow/pillar_grade.py`: security/compliance/build/throughput/audit-replayable; the security pillar is a constant, so the grade is a placeholder |
| Quantified success metrics | built | `engine/sow/metrics.py`: EBITDA %/yr + hrs/yr + payback months per SOW, source-traced; grounded-numbers probe validates the artifact |
| Side-by-side comparison | built | `presentation/side-by-side/sbs.py`: WWOD + pillar grade + metrics → comparison matrix + one recommendation; markdown + JSON |
| FDE handoff packet | built | `presentation/handoff/packet.py`: selected SOW → JSON + markdown brief; gaps/blockers become the FDE validation checklist |
| Narrative | planned | `presentation/narrative/` (empty) |
| Grounded-numbers gate | built | `engine/meta-levels/financial/findings.py` (`assert_grounded`, fail-closed) + `scripts/probes/grounded_numbers.py`; both check `impact_usd`, `impact_hours` and `exposure_usd` |

<a id="flywheel"></a>
## Outcome ledger

| Component | State | Path |
|---|---|---|
| Feedback (predicted vs realized) | built | `learning/feedback/outcome_loop.py` + `schema.json`: append-only ledger; paired deltas + accuracy ratio → eval-set export |
| Durable execution (idempotency + retry/backoff) | built | `engine/run/durable.py`: at-most-once on `run_id`; capped exponential retry (1/4/16s, max 3); every attempt journaled |
| Monitoring / recurring-diagnostic tier | partial | `learning/feedback/monitoring.py`: re-run cadence (`next_run_due`/`due_tenants`) + realized-impact stub |
| RL / external-signals / self-triggers | planned | `learning/{rl,external-signals,self-triggers}/` (empty) |

<a id="surface"></a>
## Web surface

| Component | State | Path |
|---|---|---|
| Next.js app | built | `web/`: App Router, `tsc --noEmit` clean, Next 16.4.1, Node 20.9+ |
| Onboarding page + first-finding UX | built | `web/app/onboarding/page.tsx` |
| Engine HTTP boundary (scoped token only) | built | `web/lib/engine.ts` + `web/app/api/teaser/route.ts`: calls `engine/api` over `ENGINE_URL` with a timeout; `engine_unreachable` fallback only when the engine cannot be reached, engine errors surface as 502 |
| SOW review/choose UI | partial | `web/app/diagnostic/[runId]/page.tsx`: the page exists; the `/api/runs/[runId]/*` routes it calls and the engine routes behind them are not built |

<a id="docs"></a>
## Docs and visualization

| Component | State | Path |
|---|---|---|
| Decision record (Tier-2 architecture) | built | `docs/decisions/2026-05-28-saas-conglomeration-architecture.md` |
| PRODUCT / STATE / ROADMAP / GTM / UPDATE-PROTOCOL | built | `docs/` |
| Clickable product map | built | `docs/site/index.html` |
