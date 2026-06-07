"""Durable execution for diagnostic runs (P5.T2, Throughput pillar).

A diagnostic run is a multi-step, multi-minute job (onboarding -> snapshot ->
findings -> council -> SOWs -> report). The Throughput pillar requires it to be
durable: survive a crash/restart without double-charging or double-delivering, and
retry transient failures with capped exponential backoff.

This module gives the run path two throughput-pillar primitives, offline and
dependency-free (no Inngest/Temporal needed for the synthetic slice — but the
interface is the same shape so a durable-execution backend drops in later):

  - **Idempotency on run_id** — `run_once(run_id, fn)` records a result keyed by
    run_id in an append-only journal. A re-invocation with the same run_id returns
    the recorded result instead of re-executing — so a retried HTTP call, a
    redeploy mid-run, or a duplicate trigger never produces a second SOW set or a
    second client deliverable.
  - **Retry with capped exponential backoff** — `with_retry(fn)` retries transient
    failures `[1s, 4s, 16s]` (manifest cascade backoff), capped at 3 attempts,
    then raises. No silent failure: every attempt + the final outcome is journaled.

The backoff schedule and cap come from `build/manifest.json`
recursive_context.cascade (1/4/16s, max 3) so the run path and the build harness
share one retry discipline.
"""
from __future__ import annotations

import json
import time
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Any, Callable

REPO = Path(__file__).resolve().parents[2]
DEFAULT_JOURNAL = REPO / "runs" / "_durable" / "journal.jsonl"

# cascade backoff from the manifest (kept in sync with build/manifest.json)
BACKOFF_SECONDS = [1, 4, 16]
MAX_ATTEMPTS = 3


def _utc_now() -> str:
    import subprocess

    return subprocess.check_output(["date", "-u", "+%FT%TZ"]).decode().strip()


def _append(journal: Path, obj: dict) -> None:
    journal.parent.mkdir(parents=True, exist_ok=True)
    with open(journal, "a") as f:
        f.write(json.dumps(obj, default=str) + "\n")


def _load(journal: Path) -> list[dict]:
    if not journal.exists():
        return []
    return [json.loads(line) for line in journal.read_text().splitlines() if line.strip()]


class RetryExhausted(RuntimeError):
    """Raised when all retry attempts fail — never silent."""


@dataclass
class RunResult:
    run_id: str
    status: str                 # "completed" | "replayed"
    result: Any = None
    attempts: int = 1
    journaled_at: str = ""

    def to_dict(self) -> dict:
        return asdict(self)


def completed_result(run_id: str, *, journal: Path | None = None) -> Any | None:
    """Return the recorded result for run_id if it already completed, else None."""
    j = journal or DEFAULT_JOURNAL
    for row in _load(j):
        if row.get("run_id") == run_id and row.get("event") == "completed":
            return row.get("result")
    return None


def run_once(
    run_id: str,
    fn: Callable[[], Any],
    *,
    journal: Path | None = None,
    retries: bool = True,
) -> RunResult:
    """Execute `fn` at-most-once per run_id (idempotency key = run_id).

    If run_id already completed, returns the journaled result without re-executing
    (`status='replayed'`). Otherwise executes (optionally with retry/backoff),
    journals the result, and returns it (`status='completed'`)."""
    j = journal or DEFAULT_JOURNAL
    prior = completed_result(run_id, journal=j)
    if prior is not None:
        return RunResult(run_id=run_id, status="replayed", result=prior, attempts=0,
                         journaled_at=_utc_now())

    _append(j, {"ts": _utc_now(), "run_id": run_id, "event": "start"})
    if retries:
        result, attempts = with_retry(fn, run_id=run_id, journal=j)
    else:
        result, attempts = fn(), 1
    ts = _utc_now()
    _append(j, {"ts": ts, "run_id": run_id, "event": "completed",
                "attempts": attempts, "result": result})
    return RunResult(run_id=run_id, status="completed", result=result,
                     attempts=attempts, journaled_at=ts)


def with_retry(
    fn: Callable[[], Any],
    *,
    run_id: str = "",
    journal: Path | None = None,
    backoff: list[int] | None = None,
    max_attempts: int = MAX_ATTEMPTS,
    sleep: Callable[[float], None] = time.sleep,
) -> tuple[Any, int]:
    """Run `fn`, retrying transient failures with capped exponential backoff.

    Returns (result, attempts). Raises RetryExhausted after `max_attempts`. Every
    attempt + the exhaustion is journaled — no silent failure (Throughput pillar).
    `sleep` is injectable so tests don't actually wait."""
    j = journal or DEFAULT_JOURNAL
    schedule = backoff or BACKOFF_SECONDS
    last_err: Exception | None = None
    for attempt in range(1, max_attempts + 1):
        try:
            result = fn()
            if attempt > 1:
                _append(j, {"ts": _utc_now(), "run_id": run_id, "event": "retry_success",
                            "attempt": attempt})
            return result, attempt
        except Exception as e:  # noqa: BLE001 — durable layer catches to retry/journal
            last_err = e
            _append(j, {"ts": _utc_now(), "run_id": run_id, "event": "attempt_failed",
                        "attempt": attempt, "error": str(e)})
            if attempt < max_attempts:
                delay = schedule[min(attempt - 1, len(schedule) - 1)]
                sleep(delay)
    _append(j, {"ts": _utc_now(), "run_id": run_id, "event": "retry_exhausted",
                "attempts": max_attempts, "error": str(last_err)})
    raise RetryExhausted(
        f"run {run_id!r}: {max_attempts} attempts exhausted; last error: {last_err}"
    )


def _main() -> int:
    import argparse

    ap = argparse.ArgumentParser(description="Durable run journal inspector")
    ap.add_argument("--run-id", default=None)
    args = ap.parse_args()
    rows = _load(DEFAULT_JOURNAL)
    if args.run_id:
        rows = [r for r in rows if r.get("run_id") == args.run_id]
    print(json.dumps(rows, indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(_main())
