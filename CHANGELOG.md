# Changelog

All notable changes to NSOS. Format loosely follows
Keep-a-Changelog; the diagnostic engine's internal pattern/eval promotions are tracked separately by
`learning/promotion-gate/ledger.jsonl`.

## [Unreleased] — dev branch

### 2026-11-11 — Launch pass: docs match the code
- **Changed** `README.md`: venv quickstart that works on a stock Mac, one demo command, env-var
  table, correction MCP server lines, an output excerpt, a limits list, and which test or CI step
  enforces each design rule.
- **Changed** `docs/STATE.md`, `docs/ROADMAP.md`: status words replace the emoji legend; the SOW
  review page is marked partial (page exists, routes not built); the staged web-CI row and the rows
  for lifted modules off the pipeline path are gone; the promotion gate says its gauntlet and perf
  inputs come from outside the repo.
- **Added** `SECURITY.md`.
- **Changed** `docs/site/index.html`: pinned Mermaid version, `securityLevel: "strict"`, labeled zoom
  buttons, and a status word on every node.
- **Changed** `README.md`, `docs/GTM.md`: the revenue band is stated as undecided in both.

### 2026-09-29 — Engine HTTP API
- **Added** `engine/api/` (FastAPI, `python -m engine.api`): `GET /health`, `GET /teaser` behind the
  scoped token with per-tenant authz, and a dev-only `POST /dev/scoped-token` that returns 404 once
  `VINNY_TOKEN_SECRET` is set. Routes that need a live model fail closed with a 503.
- **Changed** `web/lib/engine.ts` + `web/app/api/teaser/route.ts`: the web app calls the engine over
  `ENGINE_URL` with a timeout. An unreachable engine yields a finding labeled `engine_unreachable`;
  an engine error comes back as a 502.
- **Added** `tests/test_engine_api.py` (FastAPI TestClient) and a CI step that boots the API and
  curls `/health` and `/teaser`; CI also typechecks the web app.

### 2026-06-07 — P4 + P5 build pass: MVP slice complete (presentation → choice → flywheel → E2E)
- **Added** P4 — SOW presentation + operator choice:
  - `presentation/exec-report/report_generator.py::render_sow_report` — CEO-language decision report
    rendering the 2–3 scored SOWs side-by-side; passes the `quality_judge` gate.
  - `presentation/side-by-side/sbs.py` — enriches each SOW with WWOD push + 5-pillar grade + metrics
    into a comparison matrix + an honest single recommendation; markdown + machine-readable artifact.
  - `web/app/diagnostic/[runId]/page.tsx` — operator review + select page (`tsc --noEmit` clean,
    `pillar5_security` pass). The `/api/runs/[runId]/*` routes it calls were not built.
  - `presentation/handoff/packet.py` — selected SOW → FDE engagement packet (JSON + markdown brief);
    every number source-traced; gaps/blockers become the FDE validation checklist.
- **Added** P5 — outcome flywheel + durable execution + E2E + promotion:
  - `learning/feedback/outcome_loop.py` + `schema.json` — append-only predicted-vs-realized ledger;
    paired-outcome deltas + accuracy ratio export to the eval set.
  - `engine/run/durable.py` — idempotency on `run_id` (at-most-once) + capped exponential retry/backoff
    (1/4/16s, max 3) matching the manifest cascade; every attempt journaled (no silent failure).
  - `learning/feedback/monitoring.py` — recurring-diagnostic cadence + realized-impact tracking stub
    (land-and-expand tier).
  - `tests/test_e2e_synthetic.py` — full real pipe on synthetic-client-a: onboarding → QB snapshot →
    grounded findings → council → 2–3 scored SOWs → side-by-side → report → FDE packet → flywheel
    prediction. Runs on a fabricated QuickBooks fixture.
- **Decided** Tier-2: offline-deterministic no-regression mode for `eval_harness`
  (`NSOS_EVAL_OFFLINE_DETERMINISTIC`), mirroring the 2026-06-02 quality_judge precedent; production
  stays fail-closed, offline mode never fabricates an "adopt". Record:
  `docs/decisions/2026-06-07-offline-deterministic-eval-harness.md`.
- **Verified** P5.T4 promotion gate green (5/5) on `runs/synthetic-client-a/proposal.md`; eval
  no-regression passes; **132 unit tests pass**; grounded_numbers + quality_judge + pillar5_security
  all green.

### 2026-05-28 — Conglomeration foundation (Phase 0 + 0.5)
- **Decided** Tier-2 architecture: monorepo (Python `engine/` + Next.js `web/`), NIM-primary brain,
  WWOD × 5-pillar SOW scoring. Record: `docs/decisions/2026-05-28-saas-conglomeration-architecture.md`.
  Rollback baseline: `c6b1f83`.
- **Added** living docs, all in `dev`:
  - `docs/PRODUCT.md` — product description + product-description changelog (the thesis and 5-stage flow).
  - `docs/STATE.md` — build state per component.
  - `docs/ROADMAP.md` — phased plan, recursive to STATE (checkbox tracker).
  - `docs/GTM.md` — ICP, design partners, pricing, unit economics, eval-set-as-IP, trust collateral.
  - `docs/UPDATE-PROTOCOL.md` — the rule + CI gate keeping docs/viz in sync with code.
  - `docs/BUILD-PLAN.md` — the approved implementation plan (verbatim).
- **Added** `docs/site/index.html` — clickable product mind map (Mermaid, nodes colored by real build
  state, click → in-page description panels deep-linking to the docs).
- **Added** `.github/workflows/ci.yml` — CI scaffold (python tests gate; web + docs-sync jobs land Phase 1).
- **Preserved** prior bootstrap WIP as baseline commit `c6b1f83` (council protocol, NIM-only
  sanitization replacing `llm_adapter.py` → `nim_client.py`, lifted engine).

### Hardening folded into the roadmap
- Outcome flywheel (`learning/feedback/`) as first-class + recurring tier (Phase 5).
- Grounded-numbers gate: every $/hrs source-traced + confidence-banded (Phase 2).
- Eval-set versioned as IP, cold-started from prior Null Systems engagements (cross-cutting).
- `quality_judge` human-in-loop gate on client-facing output (Phase 2).
- <1h time-to-value teaser at onboarding (Phase 1).
