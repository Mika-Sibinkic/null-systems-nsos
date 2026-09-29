# Changelog

All notable changes to the Null Systems Diagnostic SaaS ("Vinny"). Format loosely follows
Keep-a-Changelog; the diagnostic engine's internal pattern/eval promotions are tracked separately by
`learning/promotion-gate/ledger.jsonl`.

## [Unreleased] — dev branch

### 2026-06-07 — P4 + P5 build pass: MVP slice complete (presentation → choice → flywheel → E2E)
- **Added** P4 — SOW presentation + operator choice:
  - `presentation/exec-report/report_generator.py::render_sow_report` — CEO-language decision report
    rendering the 2–3 scored SOWs side-by-side; passes the `quality_judge` gate.
  - `presentation/side-by-side/sbs.py` — enriches each SOW with WWOD push + 5-pillar grade + metrics
    into a comparison matrix + an honest single recommendation; markdown + machine-readable artifact.
  - `web/app/diagnostic/[runId]/page.tsx` + server-side `/api/runs/[runId]/{side-by-side,select}` routes
    — operator reviews + selects a SOW; scoped token only, secrets server-side (`tsc --noEmit` clean,
    `pillar5_security` pass).
  - `presentation/handoff/packet.py` — selected SOW → FDE engagement packet (JSON + markdown brief);
    every number source-traced; gaps/blockers become the FDE validation checklist.
- **Added** P5 — outcome flywheel + durable execution + E2E + promotion:
  - `learning/feedback/outcome_loop.py` + `schema.json` — append-only predicted-vs-realized ledger;
    paired-outcome deltas + accuracy ratio export to the eval set (the moat's measurement layer).
  - `engine/run/durable.py` — idempotency on `run_id` (at-most-once) + capped exponential retry/backoff
    (1/4/16s, max 3) matching the manifest cascade; every attempt journaled (no silent failure).
  - `learning/feedback/monitoring.py` — recurring-diagnostic cadence + realized-impact tracking stub
    (land-and-expand tier).
  - `tests/test_e2e_synthetic.py` — full real pipe on synthetic-client-a: onboarding → QB snapshot →
    grounded findings → council → 2–3 scored SOWs → side-by-side → report → FDE packet → flywheel
    prediction. Real data, not fixtures.
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
  - `docs/PRODUCT.md` — product description + product-description changelog (the thesis, 5-stage flow, moat).
  - `docs/STATE.md` — ground-truth build state (🟢/🟡/🔴 per component).
  - `docs/ROADMAP.md` — phased plan, recursive to STATE (checkbox tracker).
  - `docs/GTM.md` — ICP, design partners, pricing, unit economics, eval-set-as-IP, trust collateral.
  - `docs/UPDATE-PROTOCOL.md` — the rule + CI gate keeping docs/viz in sync with code.
  - `docs/BUILD-PLAN.md` — the approved implementation plan (verbatim).
- **Added** `docs/site/index.html` — clickable product mind map (Mermaid, nodes colored by real build
  state, click → in-page description panels deep-linking to the docs).
- **Added** `.github/workflows/ci.yml` — CI scaffold (python tests gate; web + docs-sync jobs land Phase 1).
- **Preserved** prior bootstrap WIP as baseline commit `c6b1f83` (council protocol, NIM-only
  sanitization replacing `llm_adapter.py` → `nim_client.py`, lifted engine).

### Hardening folded into the roadmap (Karpathy · Tan · LeCun)
- Outcome flywheel (`learning/feedback/`) as first-class moat + recurring tier (Phase 5).
- Grounded-numbers gate: every $/hrs source-traced + confidence-banded (Phase 2).
- Eval-set versioned as IP, cold-started from prior Null Systems engagements (cross-cutting).
- `quality_judge` human-in-loop gate on client-facing output (Phase 2).
- <1h time-to-value teaser at onboarding (Phase 1).
