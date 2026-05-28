<a id="top"></a>
# Product — Null Systems Diagnostic SaaS ("Vinny")

> The living product description. Mind-map nodes in `docs/site/index.html` deep-link to the
> anchors in this file. Update the **changelog** at the bottom on every product-description change —
> append, don't overwrite.

<a id="thesis"></a>
## The thesis

Old-economy SMBs run on bottlenecks AI has made obsolete — manual proposal assembly, blind
retention drag, over-scoped tooling, leadership hours sunk in coordination. We turn an SMB into an
**AI-native company** and unlock **multiples on EBITDA** versus peers still operating the old way.
The wedge is a **diagnostic** that an operator can run themselves; the monetizable handoff is **2–3
SOWs**, each with quantified success metrics, that the operator chooses between by intuition about
where they want to grow first. Null Systems FDEs deploy the chosen work.

<a id="who"></a>
## Who it's for

SMB operators (CEO/COO/owner) who already feel the drag but can't name the dollar figure. ICP detail
and go-to-market live in [GTM.md](./GTM.md). The product must speak **time/cost language**, never
implementation detail — the CEO sees dollars-missed and hours-reclaimed, not prompts and pipelines.

<a id="flow"></a>
## The client-view flow

<a id="onboarding"></a>
### 1. Seamless onboarding (target <30 min, first signal <1h)
Operator connects existing infra — accounting/ERP, CRM, comms (Slack/email), ops dashboards — and
optionally uploads 1–3 recorded exec interviews. Connector secrets are stored **server-side only**;
the web surface holds a scoped, short-lived token. Each source is read through a provider adapter and
snapshotted to `client/snapshots/{tenant_id}/baseline.json`. A **<1h teaser** surfaces one
high-signal finding to hook the operator while the full run proceeds async.

<a id="diagnostic"></a>
### 2. The diagnostic (24–72h, autonomous)
Six meta-level teams — **financial, operational, organizational, customer, technology, strategic** —
each run a gauntlet of executive-grade questions against the snapshot, producing findings with
quantified `impact_usd` / `impact_hours` / `bottleneck`. **Every number traces to source data**
(invoice line, timesheet, CRM event, benchmark) and carries a confidence band. The LLM narrates; the
math computes. Findings below a confidence threshold route to FDE review before the client ever sees
them.

<a id="council"></a>
### 3. Council ranking
Findings reconvene in a council weighted by recursive context — alignment with the CEO's stated
priorities, novelty vs known baseline, cross-team corroboration, and projected $/hours impact
(`engine/council/recursive_weights.py`). Pairwise LLM-judge tournament + debate, not scalar scoring.

<a id="sow"></a>
### 4. Two or three SOWs, scored and chooseable
Ranked findings bundle into 2–3 coherent **SOW candidates** (each a growth thrust). Each SOW is
scored by the **decision bridge**: **WWMD** predicts whether a Null Systems consultant would push it
(+ confidence + gaps); the **5-pillar engineering bar** grades whether it's deployable. Each SOW
carries quantified success metrics — e.g. *EBITDA +X%/yr, N hrs/yr reclaimed, payback in M months* —
so the operator chooses on evidence + their own sense of priority.

<a id="handoff"></a>
### 5. FDE handoff + outcome flywheel
The chosen SOW exports as an FDE handoff packet. NSOS keeps watching: **predicted vs realized**
impact feeds back (`learning/feedback/`), compounding the diagnostic's accuracy and powering a
**monitoring/recurring tier** (land-and-expand). This loop is the moat — anyone can call an LLM;
nobody else has the realized-outcome dataset.

<a id="moat"></a>
## Why it's defensible

1. **Outcome flywheel** — realized-impact data competitors can't copy. [STATE](./STATE.md#flywheel)
2. **Eval set = crown jewel** — the labeled diagnostic signaling, bootstrapped from Null Systems'
   prior consulting engagements + design-partner outcomes, versioned as IP.
3. **FDE deployment arm** — we don't just diagnose, we deploy. The SOW is a real engagement, not a PDF.
4. **Trust posture** — NIM-primary means client financials never train a shared frontier model;
   "we don't train shared models on your data" + DPA + SOC2 path are sales collateral. [GTM](./GTM.md#trust)

<a id="surface"></a>
## Surface (what's wired underneath)

Next.js/Vercel `web/` ↔ Python `engine/` over an HTTP/MCP boundary. Auth/tool-tiers/connector-flow
patterns lifted from Vinnie. Diagnostic runs use durable execution (queue + retries + idempotency on
`run_id`). Multi-tenant isolation by `tenant_id`. Full architecture: [ARCHITECTURE.md](./ARCHITECTURE.md).

---

## Product-description changelog

- **2026-05-28** — Initial product description. Defined thesis, 5-stage client flow (onboarding →
  diagnostic → council → 2–3 scored SOWs → FDE handoff + flywheel), defensibility, surface. Added the
  <1h teaser, grounded-numbers requirement, WWMD×5-pillar SOW scoring, and the outcome flywheel /
  recurring tier as first-class (per Karpathy/Tan/LeCun hardening pass).
