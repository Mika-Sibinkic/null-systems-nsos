# NSOS: diagnostic engine for small and mid-sized firms

NSOS (Null Systems Operating System) reads a firm's accounting export, finds where money and hours leak, and bundles the findings into two or three scored statements of work (SOWs). Every dollar in the output traces back to a line in the export. The output is a short decision report written for the owner.

Built by [Null Systems](https://github.com/Mika-Sibinkic) as an in-house product. MIT licensed.

## Who it is for

- Owners and operators of small and mid-sized firms who feel operational drag but cannot name the dollar figure. The revenue band is not decided yet; `docs/GTM.md` tracks it.
- The consultancy that then scopes and does the chosen work. Every run ends in a handoff packet whose numbers, gaps and blockers become the engineer's checklist.

## Status

Internal prototype. It runs end to end on one fabricated client. Nothing is deployed to a real customer.

What works today, all exercised by the test suite from a clean clone with no API keys:

- QuickBooks export → schema-valid tenant snapshot. Connector secrets stay server-side; the web layer gets a scoped token.
- Financial team → grounded findings (vendor and customer concentration, overdue receivables, advisory spend, proposal cycle time, margin). The engine rejects any `impact_usd`, `impact_hours` or `exposure_usd` that lacks a source trace and a confidence.
- Council ranking → two or three SOW candidates, each with a WWOD score, a deployability grade, and EBITDA and payback metrics checked by the same grounding probe.
- Owner-facing report, side-by-side comparison, and an FDE handoff packet (JSON and markdown).
- Outcome ledger (predicted vs realized, append-only), idempotent runs with capped retry, and a promotion gate for engine changes.
- HTTP API between the web app and the Python engine (`engine/api/`, FastAPI): `GET /health`, `GET /teaser` behind the scoped token with per-tenant authz, and a dev-only token mint that disappears once `VINNY_TOKEN_SECRET` is set.

What is not built: the other five domain teams (operational, organizational, customer, technology, strategic), connectors other than QuickBooks, the engine routes behind the review page, and PDF rendering. `docs/STATE.md` and `docs/ROADMAP.md` have the per-component view.

## What the output looks like

```
python scripts/run_synthetic.py
cat runs/synthetic-client-a/presentation/report.md
```

An excerpt of the committed copy, `examples/synthetic-client-a/report.md`:

```text
## Side-by-side

| Dimension | Expand margin and rationalize cost base | De-risk and grow the revenue base | Reduce supplier concentration risk |
|---|---|---|---|
| **Annual impact** | $1,400,000/yr | $11,875/yr | $0/yr |
| **At risk (not in totals)** | — | $188,000 at risk | $8,400,000 at risk |
| **EBITDA lift** | +45% | +0% | +0% |
| **Payback** | 2 months | 182 months | — |
| **Leadership hours freed / yr** | — | 48 hrs/yr | — |
| **Consultant conviction** | 54% | 24% | 26% |
| **Deployability grade** | A | B ⚠ | B ⚠ |
| **Evidence confidence** | 70% | 70% | 80% |
```

The middle option is a bad deal, and the report says so. Its $11,875 a year against an assumed $180,000 engagement cost is a 182-month payback, and the report flags it as below the engagement-viability floor. One finding (advisory spend, confidence 0.60) is held for a person to review and is not in any option. CI reruns the demo and fails if its report differs from the committed copy.

To change what counts as a finding, edit the thresholds and benchmarks at the top of `engine/meta-levels/financial/findings.py`. The engagement cost behind payback is `DEFAULT_ENGAGEMENT_COST_USD` in `engine/sow/metrics.py`.

### Limits

- There is one tenant and it is fabricated. No real firm's books have been through this.
- Vendor concentration, customer concentration and overdue receivables show as dollars at risk and never count toward annual impact. A dependency is a risk, and overdue AR is one-time cash. The reasoning is in `docs/decisions/2026-11-11-exposure-is-not-impact.md`.
- The deployability grade is a placeholder. Its security pillar returns a fixed score, so the letter grade says little yet.
- The live judge path, with `NIM_API_KEY` set, has never run in a test. Every test runs offline-deterministic.
- The review page at `web/app/diagnostic/[runId]` exists, but the routes it calls are not built, so it cannot load a run.

## Why it is built this way

A firm's books are sensitive, so the default is local. The snapshot is a file on disk, and the tests and the demo run with no model key. Every dollar has to point at the export line it came from, because an owner who checks one number and finds it wrong stops trusting the rest. When a step needs a model and there is no key, the engine fails with an error, a 503 from the API. The offline judge the tests and the demo use is an opt-in flag, `NSOS_JUDGE_OFFLINE_DETERMINISTIC=1`. Without it and without a key, the judge fails closed and the review gate holds every finding.

## Glossary

- **FDE**: forward-deployed engineer, the person who does the chosen work at the client.
- **WWOD**: "What Would the Operator Do", a score for how hard a consultant would push a SOW (`engine/sow/wwod_score.py`).
- **Council / Borda**: a judge compares findings in pairs, and the wins become a Borda ranking weighted by priority, novelty, corroboration and impact (`engine/council/`).
- **Promotion gate**: the five checks an engine change has to pass before it is adopted (`learning/promotion-gate/promotion_gate.py`).
- **Vinny**: the name the report prints for the product. Same thing as NSOS.

## Architecture

```
client/        tenant-specific data + onboarding adapters
engine/        reusable diagnostic logic + the HTTP API
learning/      outcome ledger + promotion gate
presentation/  engine output → owner-facing report, side-by-side, handoff
schemas/       JSON contracts shared across layers
mcp-servers/   correction MCP server
examples/      synthetic client for smoke tests + regression
web/           Next.js app: onboarding + diagnostic review
```

Flow: `client/` snapshot → `engine/meta-levels/*` findings → `engine/council` ranking → `engine/sow` assembly and scoring → `presentation/` report, side-by-side and handoff → `learning/feedback` outcome ledger. `docs/ARCHITECTURE.md` has the layer diagram, `docs/COUNCIL-PROTOCOL.md` the ranking rules, and `docs/decisions/` the recorded architecture choices.

## Design rules and what checks them

- Every `impact_usd`, `impact_hours` or `exposure_usd` carries a source and a confidence. `assert_grounded` in `engine/meta-levels/financial/findings.py` raises on an ungrounded finding. `tests/test_sow_metrics.py` and `tests/test_e2e_synthetic.py` run `scripts/probes/grounded_numbers.py` on the real artifacts, and CI runs both through pytest.
- The engine API boots and serves the teaser. CI starts `python -m engine.api` and curls `/health` and `/teaser`.
- The web layer never holds a connector secret. `scripts/probes/pillar5_security.py` scans for secret literals, and CI runs it.
- Every LLM call goes through `engine/router/nim_client.py`. No test checks this yet. It is a review rule.
- Docs follow code. `scripts/check_docs_sync.py origin/main...HEAD` fails when source changes without `docs/STATE.md`, `docs/ROADMAP.md` or `docs/site/index.html`. `tests/test_docs_sync.py` tests the script, and CI runs it on every pull request.

## Run it locally

Python 3.11+ and Node 20.9+ (Next 16 needs it). Checked on Python 3.11.15, Python 3.14.7 and Node 22.22.3.

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

Open http://localhost:3000/onboarding and press "Connect & get first finding". The finding shown is the engine's teaser for `synth-acme-services`. Stop the engine and press connect again to see the `engine_unreachable` fallback. An engine error comes back as a 502 carrying the engine's JSON error. This shows the same JSON:

```
curl -s -X POST http://localhost:3000/api/teaser
```

### Environment variables

All optional for local runs.

| Variable | Read by | Default | Effect |
|---|---|---|---|
| `NIM_API_KEY` | engine | unset | Model key. Unset means offline-deterministic; routes that need a model return 503. |
| `VINNY_TOKEN_SECRET` | engine | dev secret | Signs scoped tokens. Set it anywhere outside local dev. Once set, the dev token mint is gone, so the web demo also needs `DEMO_SCOPED_TOKEN`. |
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

Coverage is by layer: adapter and schema, onboarding auth, teaser, council weights, financial findings, review gate, SOW assembly, scoring and metrics, side-by-side report, handoff packet, outcome ledger, durable execution, the docs-sync script, the engine HTTP API, and one end-to-end run through the real pipeline.

On a clean clone, `python -m pytest -q` reports 193 passed. I ran it 5 times in a row on an Apple M4 (10 cores, load average about 6 from other work): pytest's own timer said 0.83 to 1.29 s, median 0.90 s, with the first run the slowest. The demo run, `python scripts/run_synthetic.py`, took 0.12 s wall clock (`/usr/bin/time`, one run). The web app has 4 `node --test` cases for the engine client (`cd web && npm test`).

CI (`.github/workflows/ci.yml`) runs the same commands on every push and pull request: pytest on Python 3.11 and 3.14, the secret scan, the demo run diffed against `examples/`, and the engine API smoke test. For `web/` it runs `npm ci`, `npm audit --audit-level=high`, typecheck, `npm test` and `npm run build`. It also installs the correction MCP server, audits it and checks that it lists its 10 tools. On pull requests it runs the docs-sync check. There is no linter; `tsc --noEmit` is the only static check.

## Built with AI agents in the loop

Most commits in this repo were produced with Claude Code and carry a `Co-Authored-By: Claude` trailer. I wrote the specs and decision records, reviewed each diff, ran the tests, and checked the outputs before committing. The correction store (`mcp-servers/correction-server/`) and the promotion gate (`learning/promotion-gate/`) exist because that review loop is part of the product design as much as the development process.

## License

MIT. See `LICENSE`.
