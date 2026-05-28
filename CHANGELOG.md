# Changelog

All notable changes to the Null Systems Diagnostic SaaS ("Vinny"). Format loosely follows
Keep-a-Changelog; the diagnostic engine's internal pattern/eval promotions are tracked separately by
`learning/promotion-gate/ledger.jsonl`.

## [Unreleased] — dev branch

### 2026-05-28 — Conglomeration foundation (Phase 0 + 0.5)
- **Decided** Tier-2 architecture: monorepo (Python `engine/` + Next.js `web/`), NIM-primary brain,
  WWMD × 5-pillar SOW scoring. Record: `docs/decisions/2026-05-28-saas-conglomeration-architecture.md`.
  Rollback baseline: `c6b1f83`.
- **Added** living docs, all in `dev`:
  - `docs/PRODUCT.md` — product description + product-description changelog (the thesis, 5-stage flow, moat).
  - `docs/STATE.md` — ground-truth build state (🟢/🟡/🔴 per component).
  - `docs/ROADMAP.md` — phased plan, recursive to STATE (checkbox tracker).
  - `docs/GTM.md` — ICP, design partners, pricing, unit economics, eval-set-as-IP, trust collateral.
  - `docs/UPDATE-PROTOCOL.md` — the rule + CI gate keeping docs/viz in sync with code.
  - `docs/BUILD-PLAN.md` — the approved implementation plan (verbatim).
  - `docs/research/vinnie-nsos-salvage.md` — Vinnie↔NSOS salvage analysis + Karpathy/Tan/LeCun hardening.
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
