#!/usr/bin/env python3
"""promotion_gate.py — regression + performance gate for internal-pipeline promotions.

A proposal (markdown) is promoted only when every gate passes: the regression
suite, the gauntlet score within tolerance of baseline, the performance delta,
council corroboration, and an explicit operator sign-off checkbox. Each
evaluation is appended to a local ledger (gitignored).
"""
from __future__ import annotations
import json, sys, subprocess
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
LEDGER = REPO_ROOT / "learning" / "promotion-gate" / "ledger.jsonl"


def now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def regression_runner(repo_path: Path) -> dict:
    test_path = repo_path / "tests" / "test_recursive_weights.py"
    if not test_path.exists():
        return {"gate": "regression", "pass": False, "reason": f"test suite not found at {test_path}"}
    try:
        result = subprocess.run(
            ["python3", str(test_path)], capture_output=True, text=True, timeout=120,
        )
        passed = "ALL PASS" in result.stdout
        return {
            "gate": "regression",
            "pass": passed,
            "stdout_tail": result.stdout.strip().splitlines()[-3:],
            "rc": result.returncode,
        }
    except Exception as e:
        return {"gate": "regression", "pass": False, "reason": str(e)}


def gauntlet_score_check(repo_path: Path, baseline: float = 74.6, tolerance: float = 5.0) -> dict:
    score_file = repo_path / "runs" / "latest-gauntlet-score.json"
    if not score_file.exists():
        return {
            "gate": "gauntlet",
            "pass": False,
            "reason": f"no recent score file: {score_file.relative_to(repo_path)}",
            "note": "fallback: must run gauntlet harness first",
        }
    score = json.loads(score_file.read_text()).get("score", 0)
    delta = abs(score - baseline)
    return {
        "gate": "gauntlet",
        "pass": delta <= tolerance,
        "score": score,
        "baseline": baseline,
        "delta": delta,
        "tolerance": tolerance,
    }


def performance_analyzer(repo_path: Path, latency_pct: float = 10.0, cost_pct: float = 5.0) -> dict:
    perf_file = repo_path / "runs" / "perf-delta.json"
    if not perf_file.exists():
        return {"gate": "performance", "pass": False, "reason": f"no perf delta file"}
    perf = json.loads(perf_file.read_text())
    lat_delta = perf.get("latency_pct", 0)
    cost_delta = perf.get("cost_pct", 0)
    ok = lat_delta <= latency_pct and cost_delta <= cost_pct
    return {
        "gate": "performance",
        "pass": ok,
        "latency_pct": lat_delta,
        "cost_pct": cost_delta,
    }


def council_corroboration(proposal_path: Path) -> dict:
    review_path = proposal_path.with_suffix(".reviews.json")
    if not review_path.exists():
        return {"gate": "council", "pass": False, "reason": "no review file"}
    reviews = json.loads(review_path.read_text())
    positive = sum(1 for r in reviews if r.get("verdict") == "net-positive")
    return {
        "gate": "council",
        "pass": positive >= 2,
        "positive_count": positive,
        "required": 2,
    }


def operator_checkbox(proposal_path: Path) -> dict:
    if not proposal_path.exists():
        return {"gate": "operator", "pass": False, "reason": "proposal file not found"}
    md = proposal_path.read_text()
    return {
        "gate": "operator",
        "pass": "- [x] Operator reviewed" in md,
    }


def evaluate_proposal(proposal_path: Path, repo_path: Path = REPO_ROOT) -> dict:
    results = [
        regression_runner(repo_path),
        gauntlet_score_check(repo_path),
        performance_analyzer(repo_path),
        council_corroboration(proposal_path),
        operator_checkbox(proposal_path),
    ]
    overall = all(r.get("pass") for r in results)
    return {
        "ts": now_iso(),
        "proposal": str(proposal_path),
        "overall_pass": overall,
        "gates": results,
    }


def append_ledger(evaluation: dict) -> None:
    LEDGER.parent.mkdir(parents=True, exist_ok=True)
    with LEDGER.open("a") as f:
        f.write(json.dumps(evaluation) + "\n")


def main():
    import argparse
    p = argparse.ArgumentParser()
    p.add_argument("proposal", help="path to proposal markdown")
    p.add_argument("--repo", default=str(REPO_ROOT))
    args = p.parse_args()
    eval_ = evaluate_proposal(Path(args.proposal), Path(args.repo))
    append_ledger(eval_)
    print(json.dumps(eval_, indent=2))
    sys.exit(0 if eval_["overall_pass"] else 1)


if __name__ == "__main__":
    main()
