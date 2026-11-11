# Changelog

All notable changes to NSOS. Format loosely follows Keep-a-Changelog.

## [1.0.0] - 2026-11-11

First public release. It runs end to end on one fabricated client. No real firm's books have been
through it yet.

- `python scripts/run_synthetic.py` turns a QuickBooks export into an owner-facing report with three
  scored options. CI reruns it and fails if the output differs from `examples/synthetic-client-a/report.md`.
- Every dollar in the output carries a source trace and a confidence. The engine raises on one that
  does not.
- Supplier concentration, customer concentration and overdue receivables show as dollars at risk.
  They stay out of annual impact, EBITDA lift and payback. Before this, an $8.4M supplier dependency
  was booked as $8.4M a year of savings and a +273% EBITDA lift.
- Findings under 0.65 confidence are listed as pending review and left out of every total.
- 174 tests run offline with no API key and make no network call.

The dated entries below are what went into 1.0.0.

### 2026-11-11 — Launch review fixes
- **Fixed** without `VINNY_TOKEN_SECRET` the API answers only loopback callers, however it is
  started. The dev secret is public, so `uvicorn engine.api.app:app --host 0.0.0.0` used to mint and
  accept forgeable tokens on the LAN.
- **Fixed** `NSOS_JUDGE_OFFLINE_DETERMINISTIC=1` now skips the model call in `quality_judge.score` and
  `nim_client.judge_pair`. Before, a `NIM_API_KEY` in the shell sent finding text to the model from
  the tests and the demo.
- **Fixed** overdue AR at risk is the open balance ($235,000 on the demo), not the 80% "recoverable"
  estimate ($188,000). The unused 80% assumption is gone.
- **Fixed** the teaser is the report's scope-cycle finding. The teaser-only cloud heuristic
  ($33,600/yr at 0.60 confidence, below the review floor) is deleted. Web copy says the demo reads a
  synthetic export.
- **Changed** the margin option is titled "Expand margin"; it no longer promises cost work it does
  not hold.
- **Removed** code no run path used: `engine/reasoning/`, `engine/run/durable.py`,
  `learning/feedback/monitoring.py`, `learning/promotion-gate/`, the financial question battery
  (`team.py`, `questions.jsonl`), the quality judge's SQLite and confirmation-gate layers, an
  unreferenced prompt file and `engine/SANITIZED.md`. The demo report is byte-identical.
- **Removed** `docs/PRODUCT.md`, `GTM.md`, `BUILD-PLAN.md`, `EXEC-REPORT-SPEC.md`,
  `UPDATE-PROTOCOL.md`, `site/index.html`, the eval-harness decision record, and the docs-sync script,
  test and CI job.
- **Changed** `SECURITY.md` points to GitHub private vulnerability reporting.
- **Changed** README: Node 22.6+, NIM env vars, the margin, scoping-sample and council limits, and
  test timings re-measured on a clean clone.

### 2026-11-11 — Launch pass
- **Fixed** vendor and customer concentration and overdue AR are exposure (`exposure_usd`), never annual
  impact ([decision](docs/decisions/2026-11-11-exposure-is-not-impact.md)). Overdue AR is the open
  balance as of the export date (made true by the review fixes above). Undefined EBITDA lift and payback are `None`, not `Infinity`.
- **Added** `scripts/run_synthetic.py`, the one demo pipeline; the review gate holds low-confidence
  findings out of every total. `examples/synthetic-client-a/report.md` is its real output.
- **Fixed** security: `tenant_id` is validated at the token boundary and in the baseline schema; the
  engine refuses to serve dev tokens off loopback; a torn corrections file is moved aside, not erased;
  the live judge goes through `nim_client` and fails closed.
- **Fixed** `run_once` keys on the completed row; the promotion gate's gauntlet check is one-sided and
  its regression gate runs the real suite.
- **Removed** unused lifted modules (router handlers, meta router, cascade handler, vector index, most
  of `engine/reasoning/`, eval harness, gauntlet, iterate), `engine/_deprecated/`, `deploy/` and the
  unused exec-report template.
- **Changed** web: Next 16.4.1 and React 19.2 (Node 22.6+ for `npm test`), `npm audit` clean, `ENGINE_URL` defaults to
  `127.0.0.1`, a bad `ENGINE_TIMEOUT_MS` is rejected, `next-env.d.ts` is no longer tracked.
- **Changed** CI: pytest on Python 3.11 and 3.14, secret scan, demo run diffed against `examples/`,
  web `npm test`, MCP server audit and smoke, docs-sync on pull requests, pinned action SHAs.
- **Changed** `grounded_numbers.py` checks `exposure_usd` too.
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
- **Decided** offline-deterministic no-regression mode for `eval_harness`
  (`NSOS_EVAL_OFFLINE_DETERMINISTIC`), mirroring the 2026-06-02 quality_judge precedent; production
  stays fail-closed, offline mode never fabricates an "adopt". Record:
  `docs/decisions/2026-06-07-offline-deterministic-eval-harness.md`.
- **Verified** P5.T4 promotion gate green (5/5) on `runs/synthetic-client-a/proposal.md`; eval
  no-regression passes; **132 unit tests pass**; grounded_numbers + quality_judge + pillar5_security
  all green.

### 2026-05-28 — Conglomeration foundation (Phase 0 + 0.5)
- **Decided** architecture: monorepo (Python `engine/` + Next.js `web/`), NIM-primary brain,
  WWOD × 5-pillar SOW scoring. Record: `docs/decisions/2026-05-28-saas-conglomeration-architecture.md`.
- **Added** living docs:
  - `docs/PRODUCT.md` — product description + product-description changelog (the thesis and 5-stage flow).
  - `docs/STATE.md` — build state per component.
  - `docs/ROADMAP.md` — phased plan, recursive to STATE (checkbox tracker).
  - `docs/GTM.md` — ICP, design partners, pricing, unit economics, eval-set-as-IP, trust collateral.
  - `docs/UPDATE-PROTOCOL.md` — the rule + CI gate keeping docs/viz in sync with code.
  - `docs/BUILD-PLAN.md` — the approved implementation plan (verbatim).
- **Added** `docs/site/index.html` — clickable product mind map (Mermaid, nodes colored by real build
  state, click → in-page description panels deep-linking to the docs).
- **Added** `.github/workflows/ci.yml` — CI scaffold (python tests gate; web + docs-sync jobs land Phase 1).
- **Preserved** prior bootstrap work as the baseline (council protocol, NIM-only
  sanitization replacing `llm_adapter.py` → `nim_client.py`, lifted engine).

### Hardening folded into the roadmap
- Outcome flywheel (`learning/feedback/`) as first-class + recurring tier (Phase 5).
- Grounded-numbers gate: every $/hrs source-traced + confidence-banded (Phase 2).
- Eval set built from the realized outcomes of consenting engagements (cross-cutting).
- `quality_judge` human-in-loop gate on client-facing output (Phase 2).
- A teaser finding at onboarding, before the full run (Phase 1).
