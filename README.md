# Vinny — Diagnostic Platform by Null Systems

> Client-facing brand: **Vinny**. Internal engine name: NSOS. Both refer to the same codebase; we use "Vinny" externally and "NSOS" in implementation.

The consultation arm of Null Systems. Runs *before* engineering execution.

## What it does (client view)

A CEO connects their firm's data sources — accounting, CRM, ops dashboards, comms tools, plus a few exec interviews. Within 24–72 hours, Vinny returns a 3–5 page diagnostic written in time/cost language:

> *"Three opportunities ranked by impact. (1) Restructuring how proposals get assembled saves an estimated $180k/year and 11 hours of partner time per week. (2) Switching one supplier dependency saves $42k/year. (3) Your current AI initiative as scoped would cost $1.2M and save $400k/year — here's the side-by-side with a leaner version that costs $230k and saves the same. Confirm any of these and Null Systems will scope an FDE engagement to execute."*

Confirmed scope is exported to Null Systems' delivery side. FDEs execute. NSOS keeps watching — outcomes feed back as residuals to improve future diagnostics.

## How it works (one paragraph)

Six meta-level agent teams (financial / operational / organizational / customer / technology / strategic) work in parallel against the client's data snapshot, each running hundreds of hardcoded executive-grade questions ("gauntlets"). Findings reconvene in a council debate weighted by recursive context — alignment with stated priorities, novelty vs what's already known, cross-team corroboration, projected impact. The executive presentation layer translates engine output into CEO-language with optional side-by-side comparison against any client-supplied idea.

## What this is NOT

- Not the personal NSOS daemon (that lives in `business-framework/Active Projects/NSOS/` and is Mika's own learning loop).
- Not deployed by FDEs — runs *before* them.
- Not a tool the CEO operates — they upload data and read the report. Everything else is automated.

## Architecture overview

See `docs/ARCHITECTURE.md` for full layout. Top-level:

```
client/        — tenant-specific data + onboarding adapters
engine/        — reusable diagnostic intelligence (lifted + new)
learning/      — RL-style cross-run improvement + external signal ingestion
presentation/  — engine output → CEO-language report (markdown / PDF / Notion)
schemas/       — universal JSON contracts (lifted from business-framework)
mcp-servers/   — Model Context Protocol servers (correction + nsos)
examples/      — synthetic clients for smoke tests + regression
deploy/        — docker-compose + deployment notes
```

## Status

Bootstrap phase. Skeleton + lift batches in progress. Smoke-test target: `examples/synthetic-client-a/` produces a CEO-language report.

See `CLAUDE.md` for operator-agent instructions.
