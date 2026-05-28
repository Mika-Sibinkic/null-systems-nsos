# Null Systems SaaS — Conglomeration Build Plan (Vinnie + NSOS + WWMD + Eng-Bar)

> The approved implementation plan (2026-05-28). Source of the phased roadmap in
> [ROADMAP.md](./ROADMAP.md) and the architecture in
> [decisions/2026-05-28-saas-conglomeration-architecture.md](./decisions/2026-05-28-saas-conglomeration-architecture.md).
> Research backing it: [research/vinnie-nsos-salvage.md](./research/vinnie-nsos-salvage.md).

## Context

Productize Null Systems' consulting into an **AI B2B SaaS for SMBs**. An operator runs a
**seamless onboarding** that connects their existing infra/tools (accounting, CRM, comms, ops).
The product reads into ops, timelines, dollars-missed, and bottlenecks — graded by Null Systems'
acquired consulting signaling — and runs the **NSOS diagnostic**. Output: **2–3 SOWs**, each with
**quantified success metrics**, that the operator chooses between using their own intuition about
where to grow first. FDEs then deploy the chosen high-leverage developments.

**The thesis (operator's words):** turn old-economy SMBs into AI-native companies, removing
bottlenecks that AI has made obsolete, to yield multiples on EBITDA. The onboarding-fed diagnostic
is the wedge; the SOWs are the monetizable handoff.

This plan conglomerates four assets that already exist in pieces:
- **Vinnie** (Electron) — surface/safety **patterns** (auth, tool-auth tiers, connector ingestion, operator-shell UX). Patterns lift; Electron code does not (SaaS = web).
- **NSOS** (Python, `null-systems-nsos`) — the diagnostic **brain**; ~30% built (last-mile works, first-three-miles empty).
- **WWMD + engineering-bar** — the **decision bridge** that scores SOWs (expert-recommend × deployable).
- **CI/CD harness** — already in `engine/gauntlets/` (`eval_harness`, `gauntlet`, `quality_judge`, `promotion_gate`).

All confidence tags `[VERIFIED]` reflect the direct code/doc sweep across the three trees.

---

## Architecture decision (Tier 2)

| Layer | Choice | Source |
|---|---|---|
| Brain / engine | `null-systems-nsos` Python (keep **NIM-primary**, Claude escalation gated — deliberate cost/independence fork, do not cross with Vinnie's Claude-CLI brain) | existing `engine/` |
| SMB surface | **NEW Next.js / Vercel web app** at `web/` (monorepo sibling of `engine/`) | new build; Vinnie patterns |
| Surface↔engine | HTTP/MCP boundary (engine has `nim_client.py`, `vinny-dispatch/router/orchestrator.py`, `mcp-servers/` skeleton) | existing seam |
| Auth / safety | server-side secrets only; web gets scoped server-issued token; per-tenant authz (per-resource, not per-route) | Vinnie `auth.js` + `tool-auth.js` patterns, re-impl in web |
| SOW scoring | **WWMD** (which SOW a Null Systems consultant would push) × **5-pillar** (is it deployable) | `reasoning_engine.predict`, `meta/wwmd_recursion.py`, `engineering-bar.md` |
| CI/CD | existing `promotion_gate` (5-gate) + `eval_harness` (A/B) + NEW GitHub Actions | `engine/gauntlets/`, `.github/workflows/` |
| Durable exec | diagnostic runs (hours) → queue + retries + idempotency keyed on `run_id` (pillar 4) | new (orchestration is sync skeleton today) |

**Repo home:** monorepo in `null-systems-nsos` (`engine/` Python + `web/` Next.js). One dev branch, one CI.
**Stage:** `internal-solo` during build. Promotion → `client-mvp` triggers on **first SMB pilot**.

---

## Current state (what's real vs empty) — `[VERIFIED]`

- **WORKS (last mile):** `engine/council/council.py` → `recursive_weights.py` (0.30 prio + 0.25 novelty + 0.20 corrob + 0.25 impact, z-normed $/hours) → `presentation/exec-report/report_generator.py` → synthetic SOW $1.38M/yr, 612 hrs. Tests pass.
- **WORKS (governance/CI):** `learning/promotion-gate/promotion_gate.py`; `engine/gauntlets/{eval_harness,gauntlet,quality_judge,iterate}.py`.
- **WORKS (lifted brain):** `engine/reasoning/*` (~2.7k LOC); `engine/cascade-handler/`; `engine/router/nim_client.py`.
- **EMPTY (first three miles — the MVP work):** `client/adapters/`, `client/onboarding/`, `client/snapshots/`, `engine/meta-levels/{6 teams}/`, `engine/gaps/`, `engine/prediction-residual/`, `learning/{rl,feedback,external-signals,self-triggers}/`. Findings are hand-authored fixtures.

**The single missing core:** *client data → quantified findings.* Everything downstream works.

---

## Build plan — vertical slice MVP

Prove the whole pipe depth-one before breadth: **one connector → one team → real findings → scored SOWs → operator choice**. Phased breakdown with success criteria + checkboxes: [ROADMAP.md](./ROADMAP.md).

- **Phase 0** — repo + governance (dev branch, decision record, CI). ✅ done.
- **Phase 0.5** — living docs + clickable visualization. ✅ done.
- **Phase 1** — onboarding + QuickBooks adapter → `baseline.json`; <1h teaser; tenant isolation.
- **Phase 2** — financial meta-team executes vs snapshot → real findings; grounded-numbers gate; quality_judge review gate. *(the missing core)*
- **Phase 3** — council ranks → 2–3 SOW candidates → WWMD × 5-pillar scoring + success metrics.
- **Phase 4** — SOW presentation + operator choice → FDE handoff packet.
- **Phase 5** — outcome flywheel (`learning/feedback/`) + E2E + promotion gate green.

---

## Salvage map (condensed)

- **From Vinnie (patterns → re-impl in web):** `auth.js`, `tool-auth.js`, connector/ingestion flow, operator-shell UX.
- **From NSOS personal → already lifted into `engine/`:** reasoning_engine, agent_memory, prompt_evolver, cascade_handler, gauntlet/eval/quality harness, promotion_gate, vector index.
- **From WWMD:** `reasoning_engine.predict` + `meta/wwmd_recursion.py` + `mika_patterns.jsonl` → SOW expert-ranking. (Lift out of personal NSOS; **Tier 3 — do not edit in place.**)
- **From engineering-bar:** 5-pillar probe as SOW deployability grader + decision-record discipline.

---

## Founder / engineer / market hardening (Karpathy · Tan · LeCun lens)

Syntheses of their public stances `[LIKELY]`. Full detail: [research/vinnie-nsos-salvage.md](./research/vinnie-nsos-salvage.md).

1. **Outcome flywheel = moat + recurring revenue** — wire `learning/feedback/` (predicted vs realized); turns one-shot into recurring tier.
2. **Grounded, defensible numbers** — every $/hrs source-traced + confidence band. LLM narrates, math computes. #1 trust risk.
3. **Eval set = crown-jewel IP** — versioned; cold-start from prior Null Systems engagements.
4. **Human-in-loop autonomy slider** — `quality_judge` gates client-facing output; low-confidence → FDE review.
5. **Time-to-value teaser** — <1h signal at onboarding; full run async.
6. **GTM + unit economics** ([GTM.md](./GTM.md)) — ICP, design partners, cost-per-diagnostic vs price = margin.
7. **Trust as sales collateral** — "no shared-model training" + DPA + SOC2 path.
8. **Demo→product is 10x** — weight toward messy-real-data robustness.

Items 1, 3, 6 decide fundable-product vs clever-pipeline.

---

## Engineering-bar guardrails (apply throughout)

- **Security:** connector secrets server-side only; no keys in `web/`; per-tenant authz; rotate on access change.
- **Compliance:** append-only event log per diagnostic run (PII-scrubbed); retention per data class.
- **Throughput:** durable execution (queue + retries + idempotency on `run_id`); per-tenant LLM spend cap; cache identical gauntlet calls.
- **Audit-replayable:** every SOW carries WWMD signal sources + pillar grades + confidence tags.

---

## Verification

- **E2E:** synthetic client → onboarding → QB snapshot → financial findings → council → 2–3 scored SOWs → web render.
- **CI:** `.github/workflows/ci.yml` green; `python3 tests/test_recursive_weights.py` ALL PASS.
- **Gate:** `promotion_gate.evaluate_proposal()` passes 5 gates on the MVP slice.
- **Salvage integrity:** lifted modules run in isolation; no in-place edits to personal NSOS.
- **Docs/viz:** `docs/{STATE,ROADMAP,PRODUCT}.md` consistent; mind map clickable; UPDATE-PROTOCOL CI check live.
