<a id="top"></a>
# ROADMAP: what is done and what is next

> Each phase links to its [STATE.md](./STATE.md) entry and its success criteria. A box is ticked
> only when the thing has run.

Strategy: **vertical slice first** — prove the whole pipe at depth-one (one connector → one team →
real findings → scored SOWs → operator choice) before going wide. Governs decision:
[2026-05-28 conglomeration architecture](./decisions/2026-05-28-saas-conglomeration-architecture.md).

<a id="phase0"></a>
## Phase 0 — Repo + governance  ·  done (2026-05-28)
- [x] `dev` branch off baseline `c6b1f83`
- [x] Tier-2 decision record written
- [x] STATE and ROADMAP docs
- [x] Git remote + CI. The 2026-09-29 workflow passed on GitHub; the launch version's demo-diff, web-test and MCP jobs have not run there yet
> State: [STATE#docs](./STATE.md#docs), [STATE#harness](./STATE.md#harness)

<a id="phase1"></a>
## Phase 1 — Onboarding + ONE connector (QuickBooks)  ·  done (2026-06-02)
- [x] Web onboarding flow (secrets server-side; scoped token)
- [x] `client/adapters/quickbooks.py` → `client/snapshots/{tenant_id}/baseline.json` (schema-valid)
- [x] Tenant isolation by `tenant_id` (per-tenant authz in `client/onboarding/auth.py`)
- [x] <1h **teaser** path (one cheap high-signal finding, grounded)
- [x] Next.js web surface (`tsc --noEmit` clean) + engine HTTP boundary
- **Success:** met. Synthetic tenant's QuickBooks data lands as a valid `baseline.json`; teaser renders.
> State: [STATE#client](./STATE.md#client), [STATE#surface](./STATE.md#surface)

<a id="phase2"></a>
## Phase 2 — Financial meta-team executes  ·  done (2026-06-02)
- [x] `engine/meta-levels/financial/` runs gauntlet vs `baseline.json` → grounded `findings.jsonl`
- [x] Bottleneck / time-leak / dollars-missed logic (`findings.py`: vendor/customer concentration, overdue-AR, advisory-spend, scope cycle-time, margin)
- [x] **Grounded-numbers gate**: every `impact_usd`/`impact_hours` source-traced + confidence-banded; unsourced number → rejected in-engine (`assert_grounded`, fail-closed) + `scripts/probes/grounded_numbers.py`
- [x] `quality_judge` gate: low-confidence findings → FDE review queue before client sees (`review_gate.py`)
- **Success:** findings with sourced numbers flow from the snapshot of a fabricated QuickBooks fixture.
> State: [STATE#engine](./STATE.md#engine), [STATE#sow](./STATE.md#sow)

<a id="phase3"></a>
## Phase 3 — Council + SOW assembly + scoring  ·  done (2026-06-02)
- [x] Council ranks real findings (works today)
- [x] Bundle ranked findings → 2–3 **SOW candidates** (`engine/sow/assembly.py` — thrust taxonomy, source-traced union)
- [x] Score each: **WWOD** (consultant-would-push + confidence + gaps, `engine/sow/wwod_score.py`) × **5-pillar** deployability grade (`engine/sow/pillar_grade.py`; security pillar is a constant, so the grade is a placeholder)
- [x] Attach quantified success metrics (EBITDA %/yr, hrs/yr, payback months — `engine/sow/metrics.py`, grounded-numbers-validated)
- **Success:** synthetic client yields 2–3 scored, metric-bearing SOWs.
> State: [STATE#sow](./STATE.md#sow)

<a id="phase4"></a>
## Phase 4 — SOW presentation + operator choice  ·  partial
- [x] `report_generator.py` → 2–3 SOWs, CEO-language, side-by-side (`render_sow_report` + `presentation/side-by-side/sbs.py`; passes the offline quality_judge regex check)
- [x] FDE handoff packet: `presentation/handoff/packet.py` exports JSON + markdown brief
- [ ] Web: operator reviews + picks. `web/app/diagnostic/[runId]/page.tsx` exists; the `/api/runs/[runId]/*` routes it calls and the engine routes behind them are not built
- **Success:** operator can compare and select a SOW in the web UI; packet exports. Packet exports; selection in the web UI is not met.
> State: [STATE#sow](./STATE.md#sow), [STATE#surface](./STATE.md#surface)

<a id="phase5"></a>
## Phase 5 — Outcome flywheel + E2E gate  ·  done
- [x] Wire `learning/feedback/` — capture predicted vs realized per shipped SOW (`outcome_loop.py` + `schema.json`; append-only ledger → eval-set deltas)
- [x] E2E on synthetic-client-a through the **real** pipe — `tests/test_e2e_synthetic.py` (fabricated QuickBooks fixture)
- **Success:** full pipe runs end-to-end; flywheel captures its first (synthetic) outcome. Met.
> State: [STATE#flywheel](./STATE.md#flywheel)

<a id="cross"></a>
## Cross-cutting (apply every phase)
- [ ] Eval set from realized outcomes; cold-start from prior Null Systems engagements
- [ ] Durable execution for multi-hour runs (queue + retries + idempotency on `run_id`)
- [ ] Per-tenant LLM spend cap; cache identical gauntlet calls
- [ ] Messy-real-data robustness (dirty QuickBooks exports), not just happy path
- [ ] Trust collateral: DPA and a SOC2 path

<a id="stage"></a>
## Stage gate
Currently `internal-solo`. **Promotion → `client-mvp` triggers on first SMB pilot** — at that point a
separate Tier-2 decision record + dev/PR/CI ceremony + pre-push hook (per stage policy).
