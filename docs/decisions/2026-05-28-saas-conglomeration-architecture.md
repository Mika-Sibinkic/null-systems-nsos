---
choice: SaaS conglomeration architecture — monorepo (Python engine + Next.js surface), NIM-primary brain, WWMD×5-pillar SOW scoring
tier: 2
date: 2026-05-28
status: accepted
alternatives_considered:
  - name: Port Vinnie's Electron app as the product surface
    reject_reason: Wrong form factor. Vinnie is a single-operator desktop app; an SMB SaaS needs a multi-tenant web surface. Vinnie contributes patterns (auth, tool-auth tiers, connector ingestion, operator-shell UX), not code.
  - name: Two repos (engine repo + separate surface repo)
    reject_reason: Splits CI, source-of-truth, and typed contracts across boundaries for a solo→small-team product. Monorepo gives one-command bring-up (Build-quality pillar) and one promotion gate.
  - name: Headless-first (engine + API/MCP only, surface later)
    reject_reason: The seamless onboarding UX is the product wedge — it's how an SMB operator gets to first value. Deferring it defers the thing clients actually buy.
  - name: Cross the brains (use Vinnie's Claude-CLI orchestration in the engine)
    reject_reason: The engine is deliberately NIM-primary (cost, independence, no client data to a frontier vendor). Crossing it would break the cost model and the data-trust story. Claude stays a gated escalation tier only.
corroborating_signals:
  - Direct code/doc sweep 2026-05-28 (this repo): council→recursive_weights→report_generator works end-to-end on examples/synthetic-client-a (report.md, $1.38M/yr). client/adapters + engine/meta-levels empty.
  - docs/ARCHITECTURE.md (this repo): client-view flow + layer map + LangGraph orchestration + multi-tenant isolation already specified.
  - ~/.claude/operator-profile/engineering-bar.md: 5 pillars; Build-quality one-command bring-up; Throughput durable execution + spend caps; Audit-replayable decision records.
  - WWMD: personal NSOS reasoning_engine.predict + meta/wwmd_recursion.py + knowledge/mika_patterns.jsonl (read-only lift source; Tier-3, do not edit in place).
  - Founder/engineer/market lens (Karpathy/Tan/LeCun synthesis [LIKELY]): outcome flywheel as moat, grounded numbers, eval-set-as-asset, GTM/unit-economics.
confidence:
  primary_claim: VERIFIED
  cost_estimate: LIKELY
verification_probe: |
  1. `git -C null-systems-nsos branch --show-current` == dev; baseline parent commit == c6b1f83.
  2. `python3 tests/test_recursive_weights.py` → ALL PASS (proves last-mile engine intact post-branch).
  3. Repo layout shows engine/ (Python) + web/ (Next.js) as monorepo siblings; one .github/workflows/ci.yml gates both.
  4. No edits land under business-framework/medan/Active Projects/NSOS/ (salvage is lift-out only).
rollback:
  commit_sha: c6b1f83746d294cfa7aa176fd7e98f154c5a703f
  steps:
    - git checkout main
    - git branch -D dev          # discard the conglomeration branch
    - (engine/ on main is untouched by this decision; no data migration to reverse)
superseded_by: null
---

## Context

Null Systems is productizing its consulting practice into an AI B2B SaaS for SMBs: an operator
onboards their existing infra (accounting, CRM, comms, ops), the NSOS diagnostic reads ops /
timelines / dollars-missed / bottlenecks graded by Null Systems' acquired consulting signaling,
and outputs 2–3 SOWs with quantified success metrics that the operator chooses between. FDEs deploy
the chosen high-leverage work. Thesis: turn old-economy SMBs into AI-native companies → EBITDA
multiples. This decision sets the founding architecture for that build.

## Decision

Build in a single monorepo at `null-systems-nsos`: keep the existing **Python `engine/`** (the
diagnostic brain, NIM-primary with Claude as a gated escalation tier only) and add a new
**Next.js/Vercel `web/`** surface for SMB onboarding + SOW review. Vinnie contributes **patterns
only** (re-implemented in the web stack), not Electron code. SOWs are scored by the bridge of
**WWMD** (which SOW a Null Systems consultant would push) × the **5-pillar engineering bar** (is it
deployable). The existing `engine/gauntlets/` + `learning/promotion-gate/` harness is the CI spine;
GitHub Actions adds lint/typecheck/test on top.

## Consequences

- **Easier:** one source of truth, one CI/promotion gate, one-command bring-up; clean web↔engine
  HTTP/MCP boundary; cost model and data-trust story stay intact (NIM-primary, no client data to a
  frontier vendor).
- **Harder:** must maintain a polyglot monorepo (Python + TS); the web surface is net-new build;
  durable execution for multi-hour diagnostic runs is not yet built (sync skeleton today).
- **Committed to:** NIM-primary brain; multi-tenant isolation by `tenant_id`; every client-facing
  number is source-traced + confidence-banded (LLM narrates, math computes); docs/viz kept
  recursively in sync with state via the UPDATE-PROTOCOL CI check.
