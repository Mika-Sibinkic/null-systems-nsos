"""Human-in-the-loop review gate: a person checks a finding before it is priced.

Before any finding reaches a client-facing surface (the report and its side-by-side),
it passes this gate. Two checks, both fail-toward-human:

  1. Confidence floor — a finding below `CONF_FLOOR` is auto-queued for FDE review.
  2. Quality judge — each finding's client-facing text is scored by
     `engine/gauntlets/quality_judge.py`; if the judge *gates* it (low rubric
     scores) OR the judge is unavailable (fail-CLOSED), it is queued for review.

Findings that clear both checks are `auto_cleared` and may surface. Everything
else lands in the FDE-review queue with a reason — nothing low-confidence reaches
a client silently. The queue is written to runs/{run_id}/review/fde_queue.jsonl.

The quality_judge is offline-deterministic in CI when
NSOS_JUDGE_OFFLINE_DETERMINISTIC=1 (set by the build pipeline), so this gate
verifies reproducibly without a live LLM key while keeping the production
fail-closed behavior when the flag is off.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from engine.gauntlets import quality_judge

CONF_FLOOR = 0.65  # findings below this confidence always go to a human

_REPO = Path(__file__).resolve().parents[3]


def _client_text(finding: dict) -> str:
    """The client-facing rendering of a finding (what the judge scores)."""
    parts = [finding.get("headline", "")]
    ev = finding.get("evidence") or finding.get("source") or []
    if ev:
        parts.append("Evidence: " + "; ".join(str(e) for e in ev[:3]))
    if finding.get("impact_usd"):
        parts.append(f"Impact: ${finding['impact_usd']:,.0f}/yr")
    if finding.get("exposure_usd"):
        parts.append(f"At risk: ${finding['exposure_usd']:,.0f}")
    conf = finding.get("confidence")
    if conf is not None:
        parts.append(f"Confidence: {conf}")
    return ". ".join(p for p in parts if p)


def review_finding(finding: dict) -> dict:
    """Run a single finding through the gate. Returns a decision record."""
    reasons: list[str] = []
    conf = float(finding.get("confidence") or 0.0)
    if conf < CONF_FLOOR:
        reasons.append(f"confidence {conf:.2f} < floor {CONF_FLOOR:.2f}")

    text = _client_text(finding)
    scores = quality_judge.score(text, context={"source": "review_gate", "verb": "finding"})
    if quality_judge.gate_decision(scores):
        reasons.append("quality_judge unavailable (fail-closed)" if scores.get("status") != "ok"
                       else "quality_judge gated output below threshold")

    queued = bool(reasons)
    return {
        "finding_id": finding.get("id"),
        "headline": finding.get("headline"),
        "confidence": conf,
        "queued_for_review": queued,
        "auto_cleared": not queued,
        "reasons": reasons,
        "judge_scores": {k: scores.get(k) for k in ("status", "relevance", "actionability", "calibration", "confidence")},
    }


def review_findings(findings: list[dict], *, run_id: str | None = None,
                    runs_root: Path | None = None) -> dict[str, Any]:
    """Gate a list of findings. Writes the FDE-review queue; returns a summary.

    Returns {total, auto_cleared, queued, decisions:[...], queue_path}.
    """
    decisions = [review_finding(f) for f in findings]
    queue = [d for d in decisions if d["queued_for_review"]]
    cleared = [d for d in decisions if d["auto_cleared"]]

    queue_path = None
    if run_id is not None:
        runs = runs_root or (_REPO / "runs")
        qp = runs / run_id / "review" / "fde_queue.jsonl"
        qp.parent.mkdir(parents=True, exist_ok=True)
        qp.write_text("\n".join(json.dumps(d) for d in queue) + ("\n" if queue else ""))
        queue_path = str(qp)

    return {
        "total": len(decisions),
        "auto_cleared": len(cleared),
        "queued": len(queue),
        "decisions": decisions,
        "queue_path": queue_path,
    }
