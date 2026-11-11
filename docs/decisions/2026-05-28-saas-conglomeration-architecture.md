---
choice: One monorepo (Python engine + Next.js web) with one model client
date: 2026-05-28
status: accepted; amended 2026-11-11
alternatives_considered:
  - name: Two repos (engine repo + separate web repo)
    reject_reason: Splits CI, source of truth and typed contracts across a boundary for a small product. One repo gives one-command bring-up and one CI workflow.
  - name: Headless first (engine + API only, web later)
    reject_reason: Onboarding is how an owner gets to a first result. Deferring the web surface defers the part people try first.
verification_probe: |
  engine/ (Python) and web/ (Next.js) are siblings in this repo, and one
  .github/workflows/ci.yml runs both.
rollback: none recorded; there is no data migration to reverse.
superseded_by: null
---

## Context

Null Systems is turning its consulting diagnostic into a product for small and mid-sized firms. An owner connects their accounting and other systems, NSOS reads them, and it outputs 2-3 SOWs with quantified success metrics for the owner to pick between. An engineer then does the chosen work. This record set the founding layout. The design was adapted from an earlier private prototype; no code from it is in this repo.

## Decision

One monorepo: the Python `engine/` and a Next.js `web/` surface for onboarding. Every model call goes through one client, `engine/router/nim_client.py`. Each SOW is scored by how hard a consultant would push it (WWOD) and by a deployability grade.

## Consequences

- **Easier:** one source of truth, one CI workflow, one-command bring-up, and a plain HTTP boundary between web and engine.
- **Harder:** a two-language repo (Python and TypeScript). Durable execution for long runs is not built; a run is one synchronous process.
- **Committed to:** tenant isolation by `tenant_id`, and every client-facing number source-traced and confidence-banded (the model may narrate, arithmetic computes).

## Amended 2026-11-11

The original record claimed more than the code does. What is true:

- **Where data goes.** With `NIM_API_KEY` set and `NSOS_JUDGE_OFFLINE_DETERMINISTIC` unset, prompts, which include finding text, go to `NIM_BASE_URL`, by default NVIDIA's hosted API. The original "no client data to a frontier vendor" does not hold for that path. Offline, which is how the tests and the demo run, nothing leaves the machine.
- **No Claude tier.** `nim_client` is the only model client, and its only caller is the quality judge.
- **No promotion gate.** `learning/promotion-gate/` was removed. CI is `.github/workflows/ci.yml`.
- **No rollback commit.** The commit the original record named predates the published history, so the reference was removed.
- **The deployability grade is a placeholder.** One of its five checks in `engine/sow/pillar_grade.py` returns a fixed score.
