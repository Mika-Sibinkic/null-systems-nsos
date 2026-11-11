---
choice: Offline-deterministic fallback for the quality_judge build gate
tier: 2
date: 2026-06-02
status: accepted
alternatives_considered:
  - name: Keep fail-CLOSED only (no offline path)
    reject_reason: The quality_judge gate can never pass in a keyless/offline build, so the tests and the demo could never check client-facing output. A gate that cannot be satisfied is not a gate, it is a wall.
  - name: Mock the LLM adapter with a canned JSON response
    reject_reason: A fixed mock verifies nothing about the output under test — every input scores identically, so the gate stops discriminating good from bad findings. No real signal.
  - name: Provision a live NIM key in CI
    reject_reason: Tier-3 (spend/metered) and out of scope for an internal-solo synthetic build; adds a network dependency to a deterministic build DAG.
corroborating_signals:
  - "engine/council/council.py deterministic_judge — the codebase's own established pattern: a reproducible offline judge so tests run without network, with the live NIM path as the production primary."
  - "engine/teaser/teaser.py — same design DNA: pure-arithmetic, offline, source-traced + confidence-banded so it survives the same gates the LLM path does."
confidence:
  primary_claim: VERIFIED
  cost_estimate: VERIFIED
verification_probe: |
  Default (production) is unchanged and fail-closed:
    python3 engine/gauntlets/quality_judge.py --gate --text "test"   # exit 1 (judge unavailable)
  Offline-deterministic mode (opt-in, set by the build pipeline) scores structurally and gates honestly:
    NSOS_JUDGE_OFFLINE_DETERMINISTIC=1 python3 engine/gauntlets/quality_judge.py --gate \
      --text "<grounded $-impact + evidence + confidence + next step>"   # exit 0
    NSOS_JUDGE_OFFLINE_DETERMINISTIC=1 python3 engine/gauntlets/quality_judge.py --gate \
      --text "x"                                                          # exit 1 (weak output gated)
rollback:
  commit_sha: 71ff112
  steps:
    - "git revert the commit adding OFFLINE_DETERMINISTIC + _deterministic_score to engine/gauntlets/quality_judge.py"
    - "unset NSOS_JUDGE_OFFLINE_DETERMINISTIC in the build pipeline env"
    - "quality_judge returns to fail-closed-only behavior"
superseded_by:
---

## Context
The quality judge calls a live LLM rubric and, when that call fails, fails CLOSED — the
correct production posture. But this synthetic internal-solo build runs with no NIM key, so the
`quality_judge` gate could never pass in the tests or the demo.

## Decision
Add an opt-in offline-deterministic structural rubric (`NSOS_JUDGE_OFFLINE_DETERMINISTIC=1`). When the
flag is set, make no model call and score the output 0-5 / 0.0-1.0 from defensible textual
signals (cites dollars/hours, names a concrete action, points at evidence, carries a confidence word).
Default behavior (flag off) is byte-for-byte the prior fail-closed production path. The build pipeline
exports the flag for audit runs; production never sets it.

## Consequences
- Easier: keyless/offline builds verify gating logic reproducibly; CI needs no LLM secret.
- Harder: the deterministic rubric is structural, not semantic — a fluent-but-wrong finding could pass
  the offline gate. Mitigated because the live LLM judge remains the production primary; offline mode
  is a build-verification fallback, not the client-facing gate.
- Committed to: keeping the offline scorer's signals aligned with the LLM rubric dimensions so the two
  paths don't diverge in what they reward.

## Amended 2026-11-11
The first version called the live judge first and used the offline rubric only after that call failed, so with `NIM_API_KEY` in the shell the tests and the demo sent finding text to the model. The flag now skips the model call entirely, in `quality_judge.score` and in `nim_client.judge_pair`.
