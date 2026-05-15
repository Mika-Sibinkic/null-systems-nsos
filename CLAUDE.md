# NSOS — Operator Agent Manual

> Instructions for any Claude Code agent working on this productized NSOS codebase.

## Operator profile (canonical, machine-wide)

@~/.claude/operator-profile/mika.md
@~/.claude/operator-profile/communication-rules.md

## Capability menu

Reference the index at `~/conductor/workspaces/null-systems-business-framework/taipei/.claude/index/CAPABILITY_INDEX.md` BEFORE planning any non-trivial task. It enumerates every MCP / skill / CLI / script / integration / external signal available.

## What this codebase is

NSOS is the **consultation and diagnostic** arm of Null Systems. Multi-tenant. Generates executive-language opportunity scope from client firm data. Confirmed scope hands off to FDEs.

This repo is a **fork** of the architectural DNA from the personal NSOS at `business-framework/Active Projects/NSOS/`. The personal version stays in place untouched — *do not modify it from here*.

## Layer ownership

| Layer | Purpose | Source |
|-------|---------|--------|
| `client/` | Tenant-specific code (per-firm onboarding, adapters, snapshots) | NEW |
| `engine/reasoning/` | Predict / compare / extract / update cycle | LIFTED (verbatim) |
| `engine/gaps/` | Open reasoning gap detection + impact scoring | LIFTED (verbatim) |
| `engine/prediction-residual/` | Predict → measure → residual loop | LIFTED (verbatim) |
| `engine/vector-index/` | Hybrid BM25 + TF-IDF semantic search | LIFTED (verbatim) |
| `engine/cascade-handler/` | 7 recovery strategies, provider-agnostic | LIFTED (verbatim) |
| `engine/router/` | NIM primary + Groq/Cerebras/Anthropic fallbacks | LIFTED (sanitized + generalized) |
| `engine/gauntlets/` | JSONL-defined hardcoded question batteries | LIFTED (sanitized) + NEW question sets |
| `engine/meta-levels/{financial,operational,organizational,customer,technology,strategic}/` | One folder per agent team | NEW |
| `engine/council/` | Debate protocol + recursive-weight scoring | NEW |
| `learning/rl/` | RL-style cross-run learning | NEW |
| `learning/external-signals/` | HN / GH / Reddit pollers | NEW |
| `learning/self-triggers/` | Cron NSOS sets for itself | NEW |
| `learning/promotion-gate/` | Regression + perf gate for internal-pipeline promotions | NEW |
| `presentation/` | CEO-language report + side-by-side + narrative | NEW |
| `mcp-servers/correction-server/` | Indexed corrections | LIFTED (rebrand) |
| `mcp-servers/nsos-server/` | Engine exposed via MCP | NEW |

## How to work in this repo

1. **Read the layer manifest above before touching files** — verbatim-lifted code stays verbatim unless we discover a tenant-coupling bug.
2. **Use TDD** for any NEW code. Tests live in `tests/`. Fixtures in `tests/fixtures/`.
3. **Sanitization rules** for any further lift: no "Mika", no "Null Systems", no Dell / Telegram / RustDesk references in code; provider endpoints come from env / config.
4. **Council protocol changes** require a regression run — gauntlet score must stay within ±5 of the lifted baseline (74.6).
5. **Synthetic client examples** are the smoke-test target. Any engine change must pass `examples/synthetic-client-a/`.

## Don't

- Don't modify the personal NSOS at `business-framework/Active Projects/NSOS/` from this repo. Lift, don't edit-in-place.
- Don't add tenant-specific code to `engine/`. That belongs in `client/`.
- Don't write to `presentation/` from `engine/`. The presentation layer pulls from engine outputs; engine doesn't push.
- Don't introduce new LLM providers without updating `engine/router/llm_router.py` AND the cascade handler config.

## Decision tiers (inherited from operator profile)

- Tier 0/1: just do it.
- Tier 2 (e.g., new provider, schema change, council weight change): surface to Mika first.
- Tier 3 (publish to client, spend money, modify personal NSOS): hard stop, always confirm.

## Session startup

1. Read this file
2. Read `docs/ARCHITECTURE.md`, `docs/COUNCIL-PROTOCOL.md`
3. Check `checkpoint.md` if it exists
4. Begin work
