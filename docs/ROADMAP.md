<a id="top"></a>
# ROADMAP — future plans, recursive to state

> Each phase links to its [STATE.md](./STATE.md) entry + success criteria + the decision record it
> depends on. Reading top-down tells you what's done, what's next, and why. Checkboxes update on
> every milestone merge per [UPDATE-PROTOCOL](./UPDATE-PROTOCOL.md). This is the recursive tracker:
> ROADMAP says where we're going, STATE says where we are, they reconcile at every merge.

Strategy: **vertical slice first** — prove the whole pipe at depth-one (one connector → one team →
real findings → scored SOWs → operator choice) before going wide. Governs decision:
[2026-05-28 conglomeration architecture](./decisions/2026-05-28-saas-conglomeration-architecture.md).

<a id="phase0"></a>
## Phase 0 — Repo + governance  ·  ✅ done (2026-05-28)
- [x] `dev` branch off baseline `c6b1f83`
- [x] Tier-2 decision record written
- [x] Living docs (PRODUCT/STATE/ROADMAP/GTM/UPDATE-PROTOCOL)
- [x] Clickable product mind map (`docs/site/`)
- [ ] Private remote (`gh repo create`) — deferred until first real code lands
- [ ] `.github/workflows/ci.yml` wired green (scaffolded 🟡 → green when `web/` + python lint exist)
> State: [STATE#docs](./STATE.md#docs), [STATE#harness](./STATE.md#harness)

<a id="phase1"></a>
## Phase 1 — Onboarding + ONE connector (QuickBooks)
- [ ] Web onboarding flow (secrets server-side; scoped token — Vinnie auth pattern)
- [ ] `client/adapters/quickbooks.py` → `client/snapshots/{tenant_id}/baseline.json`
- [ ] Tenant isolation by `tenant_id`
- [ ] <1h **teaser** path (one cheap high-signal finding)
- **Success:** a synthetic tenant's QuickBooks data lands as a valid `baseline.json`; teaser renders.
> State: [STATE#client](./STATE.md#client), [STATE#surface](./STATE.md#surface)

<a id="phase2"></a>
## Phase 2 — Financial meta-team executes  *(the missing core)*
- [ ] Expand `sample-financial.jsonl` → financial question battery
- [ ] `engine/meta-levels/financial/` runs gauntlet vs `baseline.json` → **real** `findings.jsonl`
- [ ] Bottleneck / time-leak / dollars-missed logic
- [ ] **Grounded-numbers gate**: every `impact_usd`/`impact_hours` source-traced + confidence-banded; unsourced number → rejected (LeCun grounding; #1 trust risk)
- [ ] `quality_judge` gate: low-confidence findings → FDE review before client sees (Karpathy autonomy slider)
- **Success:** real (not fixture) findings with sourced numbers flow from QB snapshot.
> State: [STATE#engine](./STATE.md#engine), [STATE#sow](./STATE.md#sow)

<a id="phase3"></a>
## Phase 3 — Council + SOW assembly + scoring
- [ ] Council ranks real findings (works today)
- [ ] Bundle ranked findings → 2–3 **SOW candidates**
- [ ] Score each: **WWMD** (consultant-would-push + confidence + gaps) × **5-pillar** (deployable)
- [ ] Attach quantified success metrics (EBITDA %/yr, hrs/yr, payback months)
- **Success:** synthetic client yields 2–3 scored, metric-bearing SOWs.
> State: [STATE#sow](./STATE.md#sow)

<a id="phase4"></a>
## Phase 4 — SOW presentation + operator choice
- [ ] `report_generator.py` → 2–3 SOWs, CEO-language, side-by-side
- [ ] Web: operator reviews + picks → FDE handoff packet
- **Success:** operator can compare and select a SOW in the web UI; packet exports.
> State: [STATE#sow](./STATE.md#sow), [STATE#surface](./STATE.md#surface)

<a id="phase5"></a>
## Phase 5 — Outcome flywheel + E2E gate
- [ ] Wire `learning/feedback/` — capture predicted vs realized per shipped SOW (the moat)
- [ ] Monitoring/recurring tier hook (land-and-expand)
- [ ] E2E on synthetic-client-a through the **real** pipe
- [ ] `promotion_gate.evaluate_proposal()` green; `eval_harness` no regression; CI green
- **Success:** full pipe runs end-to-end; flywheel captures its first (synthetic) outcome.
> State: [STATE#flywheel](./STATE.md#flywheel)

<a id="cross"></a>
## Cross-cutting (apply every phase)
- [ ] Eval set versioned as IP; cold-start from prior Null Systems engagements ([GTM#eval](./GTM.md#eval))
- [ ] Durable execution for multi-hour runs (queue + retries + idempotency on `run_id`)
- [ ] Per-tenant LLM spend cap; cache identical gauntlet calls
- [ ] Messy-real-data robustness (dirty QuickBooks exports), not just happy path
- [ ] Trust collateral: DPA + SOC2 path + "no shared-model training" ([GTM#trust](./GTM.md#trust))

<a id="stage"></a>
## Stage gate
Currently `internal-solo`. **Promotion → `client-mvp` triggers on first SMB pilot** — at that point a
separate Tier-2 decision record + dev/PR/CI ceremony + pre-push hook (per engineering-bar stage policy).
