# Architecture — NSOS Productized Diagnostic Platform

> This is the target design. What exists today is in [STATE.md](./STATE.md): one financial team, a council with no debate step, and no LangGraph or AutoGen.

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
│   │  operational     │  │ + recursive-weight scoring (Borda)       │
│   │  organizational  │  │                                          │  │
│   │  customer        │──▶│ pairwise LLM-judge tournament            │  │
│   │  technology      │  │                                          │  │
│   │  strategic       │  │                                          │  │
│   └──────────────────┘  └──────────────────────────────────────────┘  │
│        │                                                              │
│        ▼ (each team uses)                                            │
│   gauntlets/ (quality judge)   router/ (nim_client)                   │
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
└────────────────────────────────────────────────────────────────────────┘
```

## Top-level orchestration

A LangGraph state machine wraps:
- 6× MetaTeam nodes (run in parallel) — each is an AutoGen-style hierarchical group-chat
- Council node (debate-based consensus over candidate findings)
- Reporter node (CEO-language synthesis)

Not built. Today `scripts/run_synthetic.py` calls each step in order in one process. The reason for LangGraph was durable state and replay, so a client-facing diagnostic can be audited.

## Data model

What `python scripts/run_synthetic.py` writes today, under `runs/synthetic-client-a/`:

- `snapshots/{tenant_id}/baseline.json`: the tenant snapshot built from the export.
- `gauntlet/financial/findings.jsonl`: the financial team's findings.
- `review/fde_queue.jsonl`: findings the review gate held for a person.
- `sow/sow-candidates.jsonl`: the 2-3 SOW candidates.
- `presentation/report.md` and `presentation/side-by-side.json`: the owner-facing report.
- `handoff/fde-handoff-packet.json` and `.md`: the engineer's checklist.
- `flywheel/outcome-ledger.jsonl`: predicted outcomes, append-only.

The CEO's stated objectives and known-already items come from `examples/synthetic-client-a/firm.json`. No council ranking file and no PDF are written.

## LLM provider

One client, `engine/router/nim_client.py`, and one default model, `meta/llama-3.3-70b-instruct` (`NIM_PRIMARY_MODEL`). With `NIM_API_KEY` set, prompts, which include finding text, go to `NIM_BASE_URL` (default: NVIDIA's hosted API). With `NSOS_JUDGE_OFFLINE_DETERMINISTIC=1` or no key, nothing leaves the machine. No other provider is wired.

## Multi-tenant isolation

Every artifact is namespaced by `{tenant_id}/`. The engine never reads across tenants without explicit cross-tenant aggregation flag (used only by `learning/rl/`).
