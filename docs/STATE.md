<a id="top"></a>
# STATE — ground truth of what's built

> Single source of "where we are." Updated on every milestone merge (see [UPDATE-PROTOCOL](./UPDATE-PROTOCOL.md)).
> Legend: 🟢 built & verified · 🟡 partial / not wired · 🔴 empty / planned · 🔵 external service.
> Last verified: **2026-05-28** (direct code sweep, `dev` branch off baseline `c6b1f83`).

<a id="summary"></a>
## One-line summary

Last-mile works (council → scoring → report, $1.38M synthetic SOW). The first three miles —
connectors → meta-team execution → quantified findings from real data — are empty. **The single
missing core is `client data → quantified findings`.**

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
| Meta-teams (6) | 🔴 | `engine/meta-levels/{financial,operational,organizational,customer,technology,strategic}/` | empty dirs — **MVP work** |
| Gaps / prediction-residual | 🔴 | `engine/gaps/`, `engine/prediction-residual/` | empty |

<a id="harness"></a>
## CI / governance harness — 🟢 (the spine)

| Component | State | Path |
|---|---|---|
| Promotion gate (5-gate) | 🟢 | `learning/promotion-gate/promotion_gate.py` |
| Eval harness (A/B, net-positive-all-metrics) | 🟢 | `engine/gauntlets/eval_harness.py` |
| Gauntlet (self-play) | 🟢 | `engine/gauntlets/gauntlet.py` |
| Quality judge (3-layer) | 🟢 | `engine/gauntlets/quality_judge.py` |
| GitHub Actions CI (lint/typecheck/test) | 🟡 | `.github/workflows/ci.yml` | scaffolded this session; wire on first real code |
| Recursive-weights unit tests | 🟢 | `tests/test_recursive_weights.py` | PASS |

<a id="client"></a>
## Client ingestion (first three miles) — 🔴 the MVP work

| Component | State | Path |
|---|---|---|
| Onboarding flow | 🔴 | `client/onboarding/` (empty) |
| Connectors / adapters (QB, HubSpot, Slack, Pocket) | 🔴 | `client/adapters/` (0 files) |
| Tenant snapshots | 🔴 | `client/snapshots/` (schema only) |
| <1h teaser signal | 🔴 | not built |

<a id="sow"></a>
## SOW output + scoring — 🟡

| Component | State | Path |
|---|---|---|
| Exec report generator | 🟡 | `presentation/exec-report/report_generator.py` | finding-list today, not yet 2–3 chooseable SOWs |
| SOW assembly (bundle findings → 2–3 candidates) | 🔴 | not built |
| WWMD × 5-pillar SOW scoring | 🔴 | not built (engine pieces exist) |
| Narrative / side-by-side | 🔴 | `presentation/{narrative,side-by-side}/` (empty) |
| Grounded-numbers gate (source-trace + confidence band) | 🔴 | not built — **client-trust blocker** |

<a id="flywheel"></a>
## Learning / outcome flywheel — 🔴 (the moat, currently empty)

| Component | State | Path |
|---|---|---|
| Feedback (predicted vs realized) | 🔴 | `learning/feedback/` (empty) |
| RL / external-signals / self-triggers | 🔴 | `learning/{rl,external-signals,self-triggers}/` (empty) |

<a id="surface"></a>
## Web surface — 🔴 (net-new)

| Component | State | Path |
|---|---|---|
| Next.js/Vercel app | 🔴 | `web/` (not yet created) |
| Auth (scoped token, Vinnie pattern) | 🔴 | not built |
| Connector tool-auth tiers (Vinnie pattern) | 🔴 | not built |

<a id="docs"></a>
## Docs + visualization — 🟢 (this session)

| Component | State | Path |
|---|---|---|
| Decision record (Tier-2 architecture) | 🟢 | `docs/decisions/2026-05-28-saas-conglomeration-architecture.md` |
| PRODUCT / STATE / ROADMAP / GTM / UPDATE-PROTOCOL | 🟢 | `docs/` |
| Clickable product mind map | 🟢 | `docs/site/index.html` |
