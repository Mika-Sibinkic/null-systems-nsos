# NSOS: diagnostic engine for small and mid-sized firms

NSOS (Null Systems Operating System) reads a firm's accounting export (today a QuickBooks-like JSON shape, see Limits), finds where money and hours leak, and bundles the findings into two or three scored statements of work (SOWs). Every dollar in the output points at the export line it starts from and names the assumption that turns it into a yearly figure. The output is a short decision report written for the owner.

Built by [Null Systems](https://github.com/Mika-Sibinkic) as an in-house product. MIT licensed.

## Who it is for

- Owners of small and mid-sized firms who feel operational drag but cannot name the dollar figure. The revenue band is not decided yet.
- The consultancy that then scopes and does the chosen work. Every run ends in a handoff packet whose numbers, gaps and blockers become the engineer's checklist.

## Status

Internal prototype. It runs end to end on one fabricated client. Nothing is deployed to a real customer.

What works today, all exercised by the test suite from a clean clone with no API keys:

- Export → schema-valid tenant snapshot. The input is a QuickBooks-like JSON shape defined by `examples/synthetic-client-a/quickbooks_export.json`. There is no live connector; `ConnectorSecretStore` is an in-memory stand-in that pins the server-side-only rule in tests.
- Financial team → grounded findings (vendor and customer concentration, overdue receivables, advisory spend, proposal cycle time, margin). The engine rejects any `impact_usd`, `impact_hours` or `exposure_usd` that lacks a source trace and a confidence.
- Two or three SOW candidates, ranked by annual impact, each with a WWOD score, a deployability grade, and EBITDA and payback metrics checked by the same grounding probe.
- Owner-facing report, side-by-side comparison, and an FDE handoff packet (JSON and markdown).
- Outcome ledger (predicted vs realized, append-only).
- HTTP API between the web app and the Python engine (`engine/api/`, FastAPI): `GET /health`, `GET /teaser` behind the scoped token with per-tenant authz, and a dev-only token mint that disappears once `VINNY_TOKEN_SECRET` is set. Without that secret the API answers only loopback callers.

What is not built: the other five domain teams (operational, organizational, customer, technology, strategic), connectors other than QuickBooks, a model that ranks findings, a web page for picking an option, and PDF rendering.

## What the output looks like

```
python scripts/run_synthetic.py
cat runs/synthetic-client-a/presentation/report.md
```

An excerpt of the committed copy, `examples/synthetic-client-a/report.md`:

```text
## Side-by-side

| Dimension | Expand margin | Protect the revenue base | Reduce supplier concentration risk |
|---|---|---|---|
| **Annual impact** | $1,400,000/yr | $11,875/yr | $0/yr |
| **At risk (not in totals)** | — | $235,000 at risk | $8,400,000 at risk |
| **EBITDA lift** | +45% of net income | +0% of net income | +0% of net income |
| **Payback** | 2 months | 182 months | — |
| **Leadership hours freed / yr** | — | 48 hrs/yr | — |
| **Consultant conviction** | 54% | 24% | 26% |
| **Deployability grade** | A | B ⚠ | B ⚠ |
| **Evidence confidence** | 70% | 70% | 80% |
```

The middle option is a bad deal, and the report says so. Its $11,875 a year against an assumed $180,000 engagement cost is a 182-month payback, and the report flags it as under the $250,000 a year we assume an option needs to be worth an engagement. That floor is a judgment, not derived from the cost. One finding (advisory spend, confidence 0.60) is held for a person to review and is not in any option. CI is set to rerun the demo and fail if its report differs from the committed copy.

To change what counts as a finding, edit the thresholds and benchmarks at the top of `engine/meta_levels/financial/findings.py`. The engagement cost behind payback (`DEFAULT_ENGAGEMENT_COST_USD`) and the size floor behind the ⚠ (`MIN_WORTHWHILE_IMPACT_USD`) sit next to each other in `engine/sow/metrics.py`.

### Limits

- There is one tenant and it is fabricated. No real firm's books have been through this.
- No real QuickBooks file or API response is parsed yet. The adapter reads a JSON shape this repo defines: flat P&L totals, purchases already summed per vendor, and invoice fields `MetaData_FirstContact` and `MetaData_ScopeSent`. Those two dates are not QuickBooks fields; they would come from a CRM. The proposal-scoping finding depends on them.
- The recommended option's $1,400,000/yr is an assumed 5 points of revenue on a 60% gross margin (`MARGIN_RECOVERY_PTS` in `findings.py`), not a leak measured in the export.
- EBITDA lift divides by net income, because the export has no depreciation, amortization or interest lines. Real EBITDA is higher, so the true lift is lower. The report prints "+45% of net income" so the base is in view.
- The scoping finding ($11,875/yr) counts only the 7 deals in the export's invoice list. Those invoices total $1.45M against $28M of revenue, so the yearly figure covers that sample, not the whole book of business.
- Vendor concentration, customer concentration and overdue receivables show as dollars at risk and never count toward annual impact. A dependency is a risk, and overdue AR is one-time cash. The reasoning is in `docs/decisions/2026-11-11-exposure-is-not-impact.md`.
- The deployability grade is a placeholder. Three of its five checks are constant today, so the letter mostly reflects annual impact against $250,000/yr and the number of findings. On the demo, security is 0.9, compliance 1.0 and audit-replayable 0.94 to 0.96 for all three options; only throughput (1.0, 0.31, 0.30) and build quality (0.74 to 0.83) move (`grade_sow` on `runs/synthetic-client-a/sow/sow-candidates.jsonl`).
- The live judge path, with `NIM_API_KEY` set, has never run in a test. Every test runs offline-deterministic, and offline the quality gate is a regex check for a figure, an evidence word, a confidence word and a next step.
- Offline, every finding's text passes that regex check, so what the review gate holds is decided by its confidence floor (0.65) alone. Advisory spend has a fixed confidence of 0.60, so it is always held.
- Options rank by annual impact (`impact_usd`), highest first. Nothing smarter ranks them yet.

## Why it is built this way

A firm's books are sensitive, so the default is local. The snapshot is a file on disk, and the tests and the demo run with no model key and make no network call. The only model call in the code is the quality judge's. With `NIM_API_KEY` set and the offline flag off, its prompts, which include finding text, go to `NIM_BASE_URL` (default: NVIDIA's hosted API). The offline judge the tests and the demo use is an opt-in flag, `NSOS_JUDGE_OFFLINE_DETERMINISTIC=1`. Without it and without a key, the judge fails closed and the review gate holds every finding. No API route uses a model today.

Every dollar has to point at the export line it came from, because an owner who checks one number and finds it wrong stops trusting the rest.

## Glossary

- **FDE**: forward-deployed engineer, the person who does the chosen work at the client.
- **WWOD**: "What Would the Operator Do", where the operator is the consultant: a score for how hard we would push a SOW (`engine/sow/wwod_score.py`). With no past engagements on record it is a fixed formula of size, confidence and corroboration.
- **Vinny**: the name the report prints for the product. Same thing as NSOS.

## Architecture

```
client/        onboarding, the QuickBooks adapter, tenant snapshots
engine/        findings, review gate, SOW scoring, quality judge, HTTP API
learning/      outcome ledger
presentation/  owner-facing report, side-by-side, handoff packet
schemas/       baseline.json, the tenant snapshot contract
mcp-servers/   correction MCP server (separate tool, see below)
examples/      synthetic client for tests and the demo
web/           Next.js app: the onboarding demo
```

Flow: `client/` snapshot → `engine/meta_levels/financial` findings → `engine/meta_levels/financial/review_gate.py` → `engine/sow` assembly, ranking and scoring → `presentation/` report, side-by-side and handoff → `learning/feedback` outcome ledger. `docs/decisions/` has the recorded architecture choices.

What `python scripts/run_synthetic.py` writes under `runs/synthetic-client-a/`:

- `snapshots/synth-acme-services/baseline.json`: the tenant snapshot built from the export.
- `gauntlet/financial/findings.jsonl`: the financial team's findings.
- `review/fde_queue.jsonl`: findings the review gate held for a person.
- `sow/sow-candidates.jsonl`: the 2-3 SOW candidates.
- `presentation/report.md` and `presentation/side-by-side.json`: the owner-facing report.
- `handoff/fde-handoff-packet.json` and `.md`: the engineer's checklist.
- `flywheel/outcome-ledger.jsonl`: predicted outcomes, append-only.

Snapshots are stored per tenant, and the API serves a snapshot only to a token scoped to that tenant. Nothing reads across tenants.

## Design rules and what checks them

- Every `impact_usd`, `impact_hours` or `exposure_usd` carries a source and a confidence. `assert_grounded` in `engine/meta_levels/financial/findings.py` raises on an ungrounded finding. `tests/test_sow_metrics.py` and `tests/test_e2e_synthetic.py` run `scripts/probes/grounded_numbers.py` on the real artifacts, and CI runs both through pytest.
- The engine API boots and serves the teaser. CI starts `python -m engine.api` and curls `/health` and `/teaser`.
- The web layer never holds a connector secret. `scripts/probes/pillar5_security.py` scans for secret literals, and CI runs it.
- Every LLM call goes through `engine/router/nim_client.py`. No test checks this yet. It is a review rule.

## Run it locally

Python 3.11+ and Node 22.6+ (`npm test` uses `--experimental-strip-types`). Checked on Python 3.11.15, Python 3.14.7 and Node 22.22.3.

```
git clone https://github.com/Mika-Sibinkic/null-systems-nsos.git
cd null-systems-nsos
python3 -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt
python -m pytest -q
```

The demo run writes the report, the side-by-side and the handoff packet under `runs/synthetic-client-a/`:

```
python scripts/run_synthetic.py
cat runs/synthetic-client-a/presentation/report.md
```

The web app needs two terminals, both starting from the repo root. Neither needs an environment variable. Without a model key the engine runs offline-deterministic, and it mints a dev scoped token for the synthetic tenant.

Terminal 1, the engine on port 8000:

```
. .venv/bin/activate
python -m engine.api
```

Terminal 2, the web app on port 3000:

```
cd web
npm ci
npm run dev
```

Open http://localhost:3000/onboarding and press "Read the sample export". The finding shown is the engine's teaser for `synth-acme-services`: the report's proposal-scoping finding, same number and confidence. Stop the engine and press the button again to see the `engine_unreachable` fallback. An engine error comes back as a 502 carrying the engine's JSON error. This shows the same JSON:

```
curl -s -X POST http://localhost:3000/api/teaser
```

### Environment variables

All optional for local runs.

| Variable | Read by | Default | Effect |
|---|---|---|---|
| `NIM_API_KEY` | engine | unset | Model key for the quality judge. Unset means the judge cannot score, so the review gate holds every finding unless the offline flag is set. |
| `NIM_BASE_URL` | engine | `https://integrate.api.nvidia.com/v1` | Where model prompts go when `NIM_API_KEY` is set. |
| `NIM_PRIMARY_MODEL` | engine | `meta/llama-3.3-70b-instruct` | Model for the quality judge. |
| `NSOS_JUDGE_OFFLINE_DETERMINISTIC` | engine | unset (the demo sets `1`) | `1` means no model call at all, even with a key. |
| `VINNY_TOKEN_SECRET` | engine | dev secret | Signs scoped tokens. Set it anywhere outside local dev. Once set, the dev token mint is gone and non-loopback callers are served, so the web demo also needs `DEMO_SCOPED_TOKEN`. |
| `DEMO_SCOPED_TOKEN` | web | unset | Scoped token the onboarding demo sends to the engine. Unset means the web app asks the dev mint. |
| `DEMO_TENANT_ID` | web | `synth-acme-services` | Tenant the onboarding demo asks for. |
| `NSOS_SNAPSHOTS_ROOT` | engine | `client/snapshots` | Where the API reads tenant snapshots. |
| `ENGINE_URL` | web | `http://127.0.0.1:8000` | Engine address. |
| `ENGINE_TIMEOUT_MS` | web | `5000` | Engine request timeout. |
| `NSOS_API_HOST` / `NSOS_API_PORT` | engine | `127.0.0.1` / `8000` | Where `python -m engine.api` listens. |
| `CORRECTIONS_DIR` | correction MCP server | `~/.nsos/corrections` | Where the server stores corrections. |

### Correction MCP server

It speaks MCP over stdio, so an MCP client starts it. It stores corrections under `CORRECTIONS_DIR`. To install it and start it by hand:

```
cd mcp-servers/correction-server
npm ci
node index.js
```

## Tests

`python -m pytest -q` runs offline with no API key against two synthetic fixtures: `examples/synthetic-client-a/` (a fabricated QuickBooks export plus firm profile) and `client/snapshots/synth-acme-services/baseline.json` (the snapshot the adapter produces from it). Real tenant snapshots under `client/snapshots/` are gitignored.

Coverage is by layer: adapter and schema, onboarding auth, teaser, financial findings, review gate, quality judge, SOW assembly, scoring and metrics, side-by-side report, handoff packet, outcome ledger, the engine HTTP API, and one end-to-end run through the real pipeline.

On a clean clone (`git clone --local`, fresh venv, Python 3.14.7), `python -m pytest -q` reports 168 passed. I ran it 5 times in a row on an Apple M4 with a load average of about 2: pytest's own timer said 0.45 to 0.73 s, median 0.45 s, with the first run the slowest. On Python 3.11.15 it also reports 168 passed. The demo run, `python scripts/run_synthetic.py`, took 0.08 s wall clock (`/usr/bin/time`, one run). The web app has 4 `node --test` cases for the engine client (`cd web && npm test`), and the correction MCP server has 2 (`cd mcp-servers/correction-server && npm test`).

CI (`.github/workflows/ci.yml`) runs the same commands on every push and pull request: pytest on Python 3.11 and 3.14, the secret scan, the demo run diffed against `examples/`, and the engine API smoke test. For `web/` it runs `npm ci`, `npm audit --audit-level=high`, typecheck, `npm test` and `npm run build`. It also installs the correction MCP server, audits it, runs its `npm test` and checks that it lists its 10 tools. There is no linter; `tsc --noEmit` is the only static check. The 2026-09-29 version of this workflow passed on GitHub (`gh run list`); this version has not run there yet.

## Built with AI agents in the loop

Most commits in this repo were produced with Claude Code and carry a `Co-Authored-By: Claude` trailer. I wrote the specs and decision records, reviewed each diff, ran the tests, and checked the outputs before committing. `mcp-servers/correction-server/` is a separate tool from that loop: it stores corrections given to a coding agent. The diagnostic does not use it.

## License

MIT. See `LICENSE`.
