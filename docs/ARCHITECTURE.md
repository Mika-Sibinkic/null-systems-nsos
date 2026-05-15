# Architecture — NSOS Productized Diagnostic Platform

## Client-view flow (the one a CEO actually sees)

1. **Onboarding (30 min, no FDE present).** Client connects accounting/ERP, CRM, ops dashboards, comms (Slack/email), and uploads 1–3 exec interviews recorded via Pocket AI or similar. Under the hood, NSOS hits each source through provider-specific adapters and snapshots a baseline of the firm's reality.
2. **Diagnostic runs autonomously (24–72 hours).** Six meta-level agent teams work in parallel — each runs its gauntlet (hundreds of hardcoded executive-grade questions) against the snapshot.
3. **Council debate.** Findings reconvene in a council weighted by recursive context: alignment with the CEO's stated priorities, novelty vs known baseline, cross-team corroboration, projected impact in $/hours.
4. **Executive report.** A 3–5 page diagnostic in time/cost language. Optional: side-by-side of any client-supplied idea vs. NSOS-recommended alternative.
5. **Scope handoff.** Confirmed scope exports to Null Systems' delivery side; FDEs pick it up. NSOS keeps watching — outcomes feed back as residuals.

## Layer responsibilities (backend support)

```
┌────────────────────────────────────────────────────────────────────────┐
│ presentation/                                                          │
│   exec-report  →  side-by-side  →  narrative (plain-language)          │
└────────────────────────────────────────────────────────────────────────┘
                                   ▲
                          (read-only consumer)
                                   │
┌────────────────────────────────────────────────────────────────────────┐
│ engine/                                                                │
│   ┌──────────────────┐  ┌──────────────────────────────────────────┐  │
│   │ meta-levels/     │  │ council/                                 │  │
│   │  financial       │──▶│ debate-based consensus                   │  │
│   │  operational     │  │ + recursive-weight scoring (Borda + Plackett-Luce-lite) │
│   │  organizational  │  │                                          │  │
│   │  customer        │──▶│ pairwise LLM-judge tournament            │  │
│   │  technology      │  │                                          │  │
│   │  strategic       │  │                                          │  │
│   └──────────────────┘  └──────────────────────────────────────────┘  │
│        │                                                              │
│        ▼ (each team uses)                                            │
│   gauntlets/   reasoning/   gaps/   prediction-residual/   vector-index/ │
│   cascade-handler/   router/                                          │
└────────────────────────────────────────────────────────────────────────┘
                                   ▲
                          (consumes snapshot)
                                   │
┌────────────────────────────────────────────────────────────────────────┐
│ client/                                                                │
│   onboarding/  →  adapters/(QB, HubSpot, Slack, Pocket, …)  →  snapshots/ │
└────────────────────────────────────────────────────────────────────────┘
                                   ▲
                                   │
┌────────────────────────────────────────────────────────────────────────┐
│ learning/                                                              │
│   rl/ (cross-run)   feedback/ (rejections + outcomes)                  │
│   external-signals/ (HN, GH, Reddit)   self-triggers/ (cron)           │
│   promotion-gate/ (regression + perf gate from internal pipeline)      │
└────────────────────────────────────────────────────────────────────────┘
```

## Top-level orchestration

A LangGraph state machine wraps:
- 6× MetaTeam nodes (run in parallel) — each is an AutoGen-style hierarchical group-chat
- Council node (debate-based consensus over candidate findings)
- Reporter node (CEO-language synthesis)

Why LangGraph: durable state + replay (auditing client-facing diagnostics is a hard requirement). Why AutoGen group-chat inside teams: handles intra-team conversational dynamics. Why pairwise comparisons in council: outperforms scalar scoring for ranking (per 2025–2026 LLM-judge literature).

## Data model

- **Tenant snapshot** (`client/snapshots/{tenant_id}/baseline.json`): structured dump of all connected sources at onboarding time.
- **Tenant priors** (`client/snapshots/{tenant_id}/priors.json`): CEO's stated objectives, weights, what's known-already.
- **Gauntlet output** (`runs/{run_id}/gauntlet/{team}/findings.jsonl`): per-team raw findings.
- **Council output** (`runs/{run_id}/council/ranked.jsonl`): ordered list with scores.
- **Report** (`runs/{run_id}/report/exec-summary.md` + `pdf`): final deliverable.

## LLM provider strategy

Per provider research:
- **NIM DeepSeek V3.2** — primary synthesis (council + reporter)
- **NIM R1-distill-32b** — reserved for council judge tie-breaking
- **Cerebras (free, 1M tok/day)** — bulk gauntlet calls (8k context cap is OK per question)
- **Groq Llama 3.3 70B** — latency-critical fallback
- **Anthropic** — escalation for genuinely hard reasoning (rare; requires explicit tier-gate)

Routed by `engine/router/llm_router.py` with cascade handler attached.

## Multi-tenant isolation

Every artifact is namespaced by `{tenant_id}/`. The engine never reads across tenants without explicit cross-tenant aggregation flag (used only by `learning/rl/`).
