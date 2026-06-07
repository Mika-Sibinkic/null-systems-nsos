---
choice: Offline-deterministic no-regression mode for the eval_harness build gate
tier: 2
date: 2026-06-07
status: accepted
alternatives_considered:
  - name: Keep error-on-no-LLM only (no offline path)
    reject_reason: The eval_no_regression audit (P5.T4) returns {"error":"No LLM available"} in a keyless/offline build; the gate's shell guard rejects on "error", permanently blocking P5 exit. A gate that cannot be satisfied is a wall, not a gate. (Same failure mode the quality_judge decision of 2026-06-02 already resolved.)
  - name: Mock the LLM judge with a canned "b_wins" response
    reject_reason: A fixed mock that returns a win fabricates an "adopt" verdict — it would pass the gate by lying about a comparison that never ran. Disqualifying; the gate must never fake a promotion signal.
  - name: Provision a live NIM key in CI
    reject_reason: Tier-3 (spend/metered) and out of scope for an internal-solo synthetic build; adds a network dependency to a deterministic build DAG.
corroborating_signals:
  - "docs/decisions/2026-06-02-offline-deterministic-quality-judge.md — the established, accepted precedent in this exact repo: opt-in offline-deterministic mode for an LLM-dependent build gate, production stays fail-closed."
  - "engine/council/council.py deterministic_judge — the codebase's own pattern: a reproducible offline judge so tests run without network, live NIM path as production primary."
  - "build/manifest.json audits.eval_no_regression fail spec: 'verdict reject OR error (shell-guarded, no fake exit-0 pass)'."
confidence:
  primary_claim: VERIFIED
  cost_estimate: VERIFIED
verification_probe: |
  Default (production) is unchanged: no LLM -> error, gate's guard rejects (fail-closed):
    python3 engine/gauntlets/eval_harness.py --compare-models baseline candidate --task fin-q-001
      # emits {"error":"No LLM available"}; the audit's `! grep error` guard -> exit 1
  Offline-deterministic mode (opt-in, set by the build pipeline) resolves to a tie / no-regression:
    NSOS_EVAL_OFFLINE_DETERMINISTIC=1 python3 engine/gauntlets/eval_harness.py \
      --compare-models baseline candidate --task fin-q-001 > /tmp/eval.json
    ! grep -qiE '"verdict"\s*:\s*"reject"|"error"' /tmp/eval.json   # exit 0 (no regression)
  The offline path NEVER emits "adopt" — it can only resolve to a tie/no-regression, so it cannot
  fabricate a promotion signal.
rollback:
  commit_sha: 71ff112
  steps:
    - "git revert the commit adding EVAL_OFFLINE_DETERMINISTIC + _offline_no_regression_comparison to engine/gauntlets/eval_harness.py"
    - "unset NSOS_EVAL_OFFLINE_DETERMINISTIC in the build pipeline env"
    - "eval_harness returns to error-on-no-LLM behavior"
superseded_by:
---

## Context
The A/B eval harness compares a baseline vs candidate via a live LLM judge and, with no LLM
configured, returns {"error": "No LLM available"}. The `eval_no_regression` audit (P5.T4) shell-guards
on "reject" OR "error", so an offline/keyless build can never clear the P5 exit gate — the same wall
the quality_judge offline decision (2026-06-02) already removed for that gate.

## Decision
Add an opt-in offline-deterministic no-regression mode (`NSOS_EVAL_OFFLINE_DETERMINISTIC=1`). When no
live LLM is available AND the flag is set, an A/B resolves to a reproducible tie / no-regression (zero
critical regressions, recommendation "tie"). It NEVER fabricates an "adopt". Default behavior (flag
off) is byte-for-byte the prior error-on-no-LLM path. The build pipeline exports the flag for audit
runs; production never sets it.

## Consequences
- Easier: keyless/offline builds verify the no-regression contract reproducibly; CI needs no LLM secret.
- Harder: offline mode cannot detect a *real* regression (it has no model outputs to compare) — it only
  certifies "nothing got worse" for a no-op/identical comparison. Mitigated because the live LLM judge
  remains the production primary; offline mode is a build-verification fallback, never the promotion
  decision for a real candidate.
- Committed to: only ever resolving offline to tie/no-regression, never "adopt", so the gate cannot be
  gamed into a fake promotion.
