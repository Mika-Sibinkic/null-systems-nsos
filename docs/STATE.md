<a id="top"></a>
# STATE — ground truth of what's built

> Single source of "where we are." Updated on every milestone merge (see [UPDATE-PROTOCOL](./UPDATE-PROTOCOL.md)).
> Legend: 🟢 built & verified · 🟡 partial / not wired · 🔴 empty / planned · 🔵 external service.
> Last verified: **2026-06-02** (P1 + P2 + P3 build pass, `dev` branch).

<a id="summary"></a>
## One-line summary

Last-mile works (council → scoring → report, $1.38M synthetic SOW). **P1 + P2 + P3 complete:** QuickBooks
adapter → valid `baseline.json`, scoped-token onboarding (secrets server-side, per-tenant authz),
<1h teaser, the Next.js web surface, the **financial meta-team** that turns the snapshot into
**6 real grounded findings** (vendor/customer concentration, overdue-AR, advisory-spend, scope cycle
time, margin) — every `impact_usd` source-traced + confidence-banded, low-confidence findings routed
to an FDE-review queue — and now the **SOW bridge**: those findings bundle into **3 coherent scored
SOW candidates** (de-risk revenue, expand margin, reduce supplier concentration), each carrying a
**WWMD consultant-would-push score**, a **5-pillar deployability grade** (all 3 grade A), and
**quantified success metrics** (EBITDA +21–273%/yr, payback 0.3–3.3 months — all source-traced).
Remaining: render the 2–3 SOWs side-by-side + operator choice + FDE handoff (P4); outcome flywheel + E2E (P5).

<a id="engine"></a>
## Engine (the brain) — mostly 🟢, lifted from personal NSOS

| Component | State | Path | Notes |
|---|---|---|---|
| Council (pairwise judge + Borda) | 🟢 | `engine/council/council.py` | deterministic judge fallback for tests |
| Recursive-weight scoring | 🟢 | `engine/council/recursive_weights.py` | 0.30 prio + 0.25 novelty + 0.20 corrob + 0.25 impact, z-normed $/hrs |
| Reasoning engine (predict/compare/extract/update) | 🟢 | `engine/reasoning/reasoning_engine.py` | lifted; powers WWMD SOW scoring |
| Agent memory / tracker / context / prompt-evolver | 🟢 | `engine/reasoning/` | ~2.7k LOC lifted |
| Cascade handler (7 recovery strategies) | 🟢 | `engine/cascade-handler/cascade_handler.py` | |
| NIM client (NIM-only enforced) | 🟢 | `engine/router/nim_client.py` | `judge_pair` for council |
| Meta-teams — financial | 🟢 | `engine/meta-levels/financial/` | question battery (`questions.jsonl` + `team.py`), data→findings engine (`findings.py`) → 6 grounded findings; in-engine grounding gate (fail-closed); FDE-review gate (`review_gate.py`) |
| Meta-teams — other 5 | 🔴 | `engine/meta-levels/{operational,organizational,customer,technology,strategic}/` | empty — post-MVP |
| Gaps / prediction-residual | 🔴 | `engine/gaps/`, `engine/prediction-residual/` | empty |

<a id="harness"></a>
## CI / governance harness — 🟢 (the spine)

| Component | State | Path |
|---|---|---|
| Promotion gate (5-gate) | 🟢 | `learning/promotion-gate/promotion_gate.py` |
| Eval harness (A/B, net-positive-all-metrics) | 🟢 | `engine/gauntlets/eval_harness.py` |
| Gauntlet (self-play) | 🟢 | `engine/gauntlets/gauntlet.py` |
| Quality judge (3-layer) | 🟢 | `engine/gauntlets/quality_judge.py` |
| GitHub Actions CI (lint/typecheck/test) | 🟡 | `.github/workflows/ci.yml` | engine job live; web + docs-sync jobs staged (workflow-scope escalation) |
| docs_sync gate | 🟢 | `scripts/check_docs_sync.py` | fails on source-vs-docs drift; `[skip-docs-sync]` override |
| Unit tests (adapter/auth/teaser/weights/financial/review-gate) | 🟢 | `tests/` | 57 PASS |
| Quality judge offline-deterministic fallback | 🟢 | `engine/gauntlets/quality_judge.py` | opt-in `NSOS_JUDGE_OFFLINE_DETERMINISTIC=1`; prod stays fail-closed ([decision](./decisions/2026-06-02-offline-deterministic-quality-judge.md)) |

<a id="client"></a>
## Client ingestion (first three miles) — 🟢 P1 (QB path)

| Component | State | Path |
|---|---|---|
| Onboarding flow | 🟢 | `client/onboarding/onboarding.py` — connect → server-side secret → snapshot → scoped web token |
| Scoped-token auth (Vinnie pattern) | 🟢 | `client/onboarding/auth.py` — HMAC scoped token, per-tenant authz, secrets-server-side wall |
| QuickBooks adapter | 🟢 | `client/adapters/quickbooks.py` — read-only QB export → `baseline.json` (schema-valid) |
| Connectors (HubSpot, Slack, Pocket) | 🔴 | `client/adapters/` — QB only so far |
| Tenant snapshots | 🟢 | `client/snapshots/{tenant}/baseline.json` + `schemas/baseline.json` |
| <1h teaser signal | 🟢 | `engine/teaser/teaser.py` — cheap grounded finding, near-instant |

<a id="sow"></a>
## SOW output + scoring — 🟢 (P3 complete)

| Component | State | Path |
|---|---|---|
| Exec report generator | 🟡 | `presentation/exec-report/report_generator.py` | finding-list today, 2–3 chooseable SOWs render in P4 |
| SOW assembly (bundle findings → 2–3 candidates) | 🟢 | `engine/sow/assembly.py` — thrust taxonomy bundles 6 findings → 3 coherent SOWs; impact-weighted confidence; source-traced union (no invented numbers) |
| WWMD SOW scoring (consultant-would-push) | 🟢 | `engine/sow/wwmd_score.py` — `predict()` learned-policy + deterministic deal-quality prior; cold-start falls back to prior (no silent 0); confidence + honest gaps[] |
| 5-pillar deployability grade | 🟢 | `engine/sow/pillar_grade.py` — each SOW graded on security/compliance/build/throughput/audit-replayable; letter grade + sub-0.5 blockers; 3 real SOWs grade A |
| Quantified success metrics | 🟢 | `engine/sow/metrics.py` — EBITDA %/yr + hrs/yr + payback months per SOW; every number source-traced to NetIncome + cost assumption; grounded-numbers probe validates the metrics artifact |
| Narrative / side-by-side | 🔴 | `presentation/{narrative,side-by-side}/` (empty — P4) |
| Grounded-numbers gate (source-trace + confidence band) | 🟢 | `engine/meta-levels/financial/findings.py` (`assert_grounded`, fail-closed) + `build/probes/grounded_numbers.py` |

<a id="flywheel"></a>
## Learning / outcome flywheel — 🔴 (the moat, currently empty)

| Component | State | Path |
|---|---|---|
| Feedback (predicted vs realized) | 🔴 | `learning/feedback/` (empty) |
| RL / external-signals / self-triggers | 🔴 | `learning/{rl,external-signals,self-triggers}/` (empty) |

<a id="surface"></a>
## Web surface — 🟡 (P1 scaffold live)

| Component | State | Path |
|---|---|---|
| Next.js/Vercel app | 🟢 | `web/` — App Router, `tsc --noEmit` clean, Next 14.2.35 (patched) |
| Onboarding page + first-finding UX | 🟢 | `web/app/onboarding/page.tsx` |
| Engine HTTP boundary (scoped token only) | 🟢 | `web/lib/engine.ts` + `web/app/api/teaser/route.ts` |
| SOW review/choose UI | 🔴 | `web/app/diagnostic/[runId]/` (P4) |
| Web CI job | 🟡 | staged at `build/ci-web-job.staged.yml` — workflow-scope escalation logged |

<a id="docs"></a>
## Docs + visualization — 🟢 (this session)

| Component | State | Path |
|---|---|---|
| Decision record (Tier-2 architecture) | 🟢 | `docs/decisions/2026-05-28-saas-conglomeration-architecture.md` |
| PRODUCT / STATE / ROADMAP / GTM / UPDATE-PROTOCOL | 🟢 | `docs/` |
| Clickable product mind map | 🟢 | `docs/site/index.html` |
