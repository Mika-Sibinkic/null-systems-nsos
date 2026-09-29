# NSOS: diagnostic engine for small and mid-sized firms

NSOS ingests a firm's own data (accounting first; CRM, ops and comms adapters planned), runs domain question batteries against it, ranks the findings in a council, and bundles them into two or three scored statements of work with dollar and hours impact that trace back to source lines. The output is a short decision report written for a CEO, not for an engineer. The client-facing name for the product is "Vinny"; this repo uses NSOS throughout.

Built by [Null Systems](https://github.com/Mika-Sibinkic) as its own product, not client work. MIT licensed.

## Who it is for

- Owners and operators of firms in roughly the $5M to $100M revenue range who feel operational drag but cannot name the dollar figure.
- The consultancy that then scopes and executes the chosen work. Every NSOS run ends in a handoff packet whose numbers, gaps and blockers become the engineer's validation checklist.

## Status

Internal prototype. It runs end to end on one synthetic client and nothing is deployed to a real customer yet.

What works today, all exercised by the test suite from a clean clone with no API keys:

- QuickBooks export → schema-valid tenant snapshot, with connector secrets kept server-side and a scoped token minted for the web layer.
- Financial meta-team → six grounded findings (vendor and customer concentration, overdue receivables, advisory spend, proposal cycle time, margin). Any `impact_usd` or `impact_hours` without a source trace and a confidence is rejected in-engine, fail-closed.
- Council ranking (pairwise judge + Borda, with recursive weights for priority alignment, novelty, corroboration and impact) → 2 to 3 SOW candidates.
- Per-SOW scoring: consultant-conviction ("would we push this?"), a five-pillar deployability grade, and EBITDA / payback metrics validated by the same grounding probe.
- CEO-language report, side-by-side comparison, and an FDE handoff packet (JSON + markdown).
- Outcome flywheel (append-only predicted-vs-realized ledger), idempotent runs with capped retry, and a promotion gate for engine changes.
- HTTP boundary between the web app and the Python engine (`engine/api/`, FastAPI): `GET /health`, `GET /teaser` behind the scoped token with per-tenant authz, and a dev-only token mint that disappears once `VINNY_TOKEN_SECRET` is set. The web route calls it with a timeout and returns a finding labeled `engine_unreachable` only when the engine cannot be reached; an engine error comes back as a 502 with the engine's JSON error, never as a made-up number.

What is not built: the other five meta-teams (operational, organizational, customer, technology, strategic), the non-QuickBooks connectors, the engine endpoints behind the diagnostic review page (`/runs/{id}/side-by-side` and `/select` are declared in `web/lib/engine.ts` but not served yet), and PDF rendering. Scoring runs in an offline-deterministic mode in tests; production paths that need a live model stay fail-closed rather than fabricate a verdict. The headline numbers in `docs/STATE.md` are computed from fabricated QuickBooks data. See `docs/STATE.md` and `docs/ROADMAP.md` for the per-component view.

## Architecture

```
client/        tenant-specific data + onboarding adapters
engine/        reusable diagnostic intelligence (lifted + new)
learning/      RL-style cross-run improvement + external signal ingestion
presentation/  engine output → CEO-language report (markdown / PDF / Notion)
schemas/       JSON contracts shared across layers
mcp-servers/   Model Context Protocol servers (correction + nsos)
examples/      synthetic clients for smoke tests + regression
deploy/        docker-compose + deployment notes
web/           Next.js surface: onboarding + diagnostic review
```

Flow: `client/` snapshot → `engine/meta-levels/*` findings → `engine/council` ranking → `engine/sow` assembly and scoring → `presentation/` report, side-by-side and handoff → `learning/feedback` outcome ledger. `docs/ARCHITECTURE.md` has the layer diagram; `docs/COUNCIL-PROTOCOL.md` the ranking rules; `docs/decisions/` the recorded architecture choices.

Design rules the code enforces rather than documents: every LLM call goes through one client (`engine/router/nim_client.py`); every dollar figure carries a source and a confidence (`scripts/probes/grounded_numbers.py`); the web layer never holds a connector secret (`scripts/probes/pillar5_security.py`).

## Run it locally

Python 3.11+ and Node 18+ (verified on Python 3.14 and Node 22).

```
git clone https://github.com/Mika-Sibinkic/null-systems-nsos.git
cd null-systems-nsos
pip install -r requirements.txt
python -m pytest -q
```

To see the actual output, run the end-to-end test and read what it writes:

```
python -m pytest -q tests/test_e2e_synthetic.py
cat runs/synthetic-client-a/presentation/report.md
cat runs/synthetic-client-a/handoff/fde-handoff-packet.md
```

Web surface. Two terminals from the repo root: the engine first, then the web app. Neither needs an environment variable; the engine runs offline-deterministic without a model key and mints a dev scoped token for the synthetic tenant.

Terminal 1, the engine on port 8000:

```
cd null-systems-nsos
python -m engine.api
```

Terminal 2, the web app on port 3000:

```
cd null-systems-nsos/web
npm ci
npm run dev
```

Then open http://localhost:3000/onboarding and press connect; the finding shown is the engine's teaser for `synth-acme-services`. Stop the engine and press connect again to see the `engine_unreachable` fallback. `curl -s -X POST http://localhost:3000/api/teaser` shows the same JSON. The web app reads the engine address from `ENGINE_URL` (default `http://localhost:8000`) and the request timeout from `ENGINE_TIMEOUT_MS` (default 5000); the engine reads `NSOS_API_HOST` and `NSOS_API_PORT`. `npm run build` and `npm run typecheck` pass clean.

## Tests

`tests/` holds 17 files and 145 test functions. They run offline in under a second against two synthetic fixtures: `examples/synthetic-client-a/` (a fabricated QuickBooks export plus firm profile) and `client/snapshots/synth-acme-services/baseline.json` (the snapshot the adapter produces from it). Real tenant snapshots under `client/snapshots/` are gitignored; only the synthetic one is committed.

Coverage is by layer: adapter and schema validation, onboarding auth, teaser, council weights, financial findings, review gate, SOW assembly / scoring / metrics, side-by-side report, handoff packet, outcome loop, durable execution, docs-sync gate, the engine HTTP API (health, teaser over the wire against the synthetic snapshot, token rejection, dev token gating, fail-closed when a live model is required), and one end-to-end run through the real pipeline. Two tests shell out to `scripts/probes/grounded_numbers.py` so the grounding rule is checked by the same script CI would run, not a mock.

CI (`.github/workflows/ci.yml`) runs `python -m pytest -q`, then boots the engine API with uvicorn and curls `/health` and `/teaser`, and runs `npm ci && npm run typecheck && npm run build`, on every push and pull request.

## Built with AI agents in the loop

Most commits in this repo were produced with Claude Code and carry a `Co-Authored-By: Claude` trailer. The operator wrote the specs and decision records, reviewed each diff, ran the tests, and verified the outputs before committing. The engine's own correction store (`mcp-servers/correction-server/`) and promotion gate (`learning/promotion-gate/`) exist because that review loop belongs to the product design as much as to the development process.

## License

MIT. See `LICENSE`.
