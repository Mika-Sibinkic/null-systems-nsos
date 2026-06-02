"""Financial meta-team — runs its question battery against a tenant baseline.

This is one of the six meta-teams (financial / operational / organizational /
customer / technology / strategic). Only the financial team is wired for the MVP
slice; the others are empty dirs (see docs/STATE.md). The team's job is narrow and
verifiable: load `questions.jsonl`, run each question's deterministic analytic over
the baseline snapshot, and emit a per-question gauntlet result.

Everything is offline + deterministic — pure arithmetic over the QuickBooks-derived
`baseline.json`, no LLM call — so the financial gauntlet runs in seconds and its
numbers are reproducible. Findings (the client-facing dollar/hours impacts) are the
job of `findings.py`, which consumes this team's analytic outputs; `team.py` is the
"did the battery run and answer every question against real data" layer.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Callable

# The analytics live in findings.py so there is exactly one implementation of each
# financial computation (team.py answers questions; findings.py turns the same
# analytics into client-facing impacts). Imported lazily to keep this module's
# import graph clean for the compile probe.
QUESTIONS_PATH = Path(__file__).resolve().parent / "questions.jsonl"


def load_questions(path: Path | str | None = None) -> list[dict[str, Any]]:
    """Load the financial question battery from questions.jsonl."""
    p = Path(path) if path else QUESTIONS_PATH
    out: list[dict[str, Any]] = []
    for line in p.read_text().splitlines():
        line = line.strip()
        if line:
            out.append(json.loads(line))
    return out


def _analytics() -> dict[str, Callable[[dict], dict | None]]:
    """Map question `method` -> the analytic function from findings.py.

    Imported here (not at module top) so `python3 -m compileall` never has to
    resolve findings.py to byte-compile team.py.
    """
    from .findings import ANALYTICS  # noqa: WPS433

    return ANALYTICS


def run_team(baseline: dict[str, Any], *, questions: list[dict] | None = None) -> dict[str, Any]:
    """Run the financial battery against a baseline snapshot.

    Returns a result envelope:
      {team, tenant_id, questions_run, answered, results:[{question_id, method,
       answered, summary, analytic}]}
    `answered` is True when the question's analytic produced a non-null result
    grounded in the baseline (the team genuinely answered it from real data).
    """
    qs = questions if questions is not None else load_questions()
    analytics = _analytics()
    acct = baseline.get("accounting") or {}
    if not acct:
        raise ValueError("baseline has no accounting view — financial team cannot run")

    results: list[dict[str, Any]] = []
    answered = 0
    for q in qs:
        method = q.get("method", "")
        fn = analytics.get(method)
        analytic = fn(baseline) if fn else None
        was_answered = analytic is not None
        if was_answered:
            answered += 1
        results.append({
            "question_id": q["id"],
            "category": q.get("category"),
            "method": method,
            "answered": was_answered,
            "summary": (analytic or {}).get("summary") if analytic else "no signal in baseline",
            "analytic": analytic,
        })

    return {
        "team": "financial",
        "tenant_id": baseline.get("tenant_id"),
        "questions_run": len(qs),
        "answered": answered,
        "results": results,
    }


def from_snapshot(tenant_id: str, *, snapshots_root: Path | None = None) -> dict[str, Any]:
    """Convenience: load a tenant's baseline.json and run the financial team."""
    root = snapshots_root or (Path(__file__).resolve().parents[3] / "client" / "snapshots")
    baseline = json.loads((root / tenant_id / "baseline.json").read_text())
    return run_team(baseline)


def _main() -> int:
    import argparse

    p = argparse.ArgumentParser(description="Run the financial meta-team against a tenant baseline")
    p.add_argument("--tenant", required=True)
    args = p.parse_args()
    out = from_snapshot(args.tenant)
    print(json.dumps(out, indent=2))
    return 0 if out["answered"] > 0 else 1


if __name__ == "__main__":
    raise SystemExit(_main())
