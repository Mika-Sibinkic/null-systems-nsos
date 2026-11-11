---
choice: Offline-deterministic fallback for the quality_judge build gate
date: 2026-06-02
status: accepted; amended 2026-11-11
alternatives_considered:
  - name: Keep fail-CLOSED only (no offline path)
    reject_reason: The quality_judge gate can never pass in a keyless/offline build, so the tests and the demo could never check client-facing output. A gate that cannot be satisfied is not a gate, it is a wall.
  - name: Mock the LLM adapter with a canned JSON response
    reject_reason: A fixed mock verifies nothing about the output under test — every input scores identically, so the gate stops discriminating good from bad findings. No real signal.
  - name: Provision a live NIM key in CI
    reject_reason: Every CI run would cost money and depend on the network, in a build that is otherwise deterministic.
corroborating_signals:
  - "engine/council/council.py deterministic_judge — the codebase's own pattern: a reproducible offline judge so tests run without network."
  - "engine/teaser/teaser.py — same design: pure arithmetic, offline, source-traced and confidence-banded, so it survives the same gates."
verification_probe: |
  Default is fail-closed (no key, flag unset):
    python3 engine/gauntlets/quality_judge.py --gate --text "test"   # exit 1 (judge unavailable)
  Offline-deterministic mode (opt-in, set by the demo and the tests) scores structurally and gates honestly:
    NSOS_JUDGE_OFFLINE_DETERMINISTIC=1 python3 engine/gauntlets/quality_judge.py --gate \
      --text "<grounded $-impact + evidence + confidence + next step>"   # exit 0
    NSOS_JUDGE_OFFLINE_DETERMINISTIC=1 python3 engine/gauntlets/quality_judge.py --gate \
      --text "x"                                                          # exit 1 (weak output gated)
rollback:
  steps:
    - "git revert the commit adding offline_deterministic + _deterministic_score to engine/gauntlets/quality_judge.py"
    - "unset NSOS_JUDGE_OFFLINE_DETERMINISTIC in the build pipeline env"
    - "quality_judge returns to fail-closed-only behavior"
superseded_by:
---

## Context
The quality judge calls a live LLM rubric and, when that call fails, fails CLOSED — the
correct production posture. But this synthetic build runs with no NIM key, so the
`quality_judge` gate could never pass in the tests or the demo.

## Decision
Add an opt-in offline-deterministic structural rubric (`NSOS_JUDGE_OFFLINE_DETERMINISTIC=1`). When the
flag is set, make no model call and score the output 0-5 / 0.0-1.0 from defensible textual
signals (cites dollars/hours, names a concrete action, points at evidence, carries a confidence word).
Default behavior (flag off) is the fail-closed production path. The demo and the tests set the flag;
production never sets it.

## Consequences
- Easier: keyless/offline builds verify gating logic reproducibly; CI needs no LLM secret.
- Harder: the deterministic rubric is structural, not semantic — a fluent-but-wrong finding could pass
  the offline gate. The live judge is the intended production path, and it has never run in a test.
  Offline, what the review gate holds is decided by its confidence floor alone.
- Committed to: keeping the offline scorer's signals aligned with the LLM rubric dimensions so the two
  paths don't diverge in what they reward.

## Amended 2026-11-11
- The first version called the live judge first and used the offline rubric only after that call failed, so with `NIM_API_KEY` in the shell the tests and the demo sent finding text to the model. The flag now skips the model call entirely, and `quality_judge` reads it on every call.
- `gate_decision()` itself holds text the judge could not score. Before, each caller had to check the status, and a caller that only asked `gate_decision()` would have published unscored text.
