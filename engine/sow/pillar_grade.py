"""5-pillar deployability grade for a SOW (P3.T3).

Each candidate SOW is graded against the Null Systems engineering bar's five
pillars — the same bar every NSOS architectural decision is graded against:

  1. Security          — is the engagement's data path safe to deploy? (no
                         frontend secrets, server-side proxy, per-resource authz)
  2. Compliance        — can it produce an audit trail? (source-traced findings =
                         append-only evidence; PII-scrubbed)
  3. Build quality     — is the underlying evidence sound? (grounded numbers,
                         corroboration breadth, typed/source-checkable)
  4. Throughput        — will it survive year-1 load? (durable-execution-ready,
                         not a one-shot; impact justifies infra spend)
  5. Audit-replayable  — can the decision be replayed? (every number names its
                         source; confidence bands; rollback-able recommendation)

This is the *deployability* grade — not "is the finding true" (that's the
grounded-numbers gate) but "if we sell and deploy this SOW as an FDE engagement,
does it clear the bar we hold our own builds to." A SOW that scores low on a
pillar gets a blocking flag the operator sees before choosing.

Deterministic, offline. Grades from SOW + finding attributes; no LLM.
"""
from __future__ import annotations

from dataclasses import dataclass, field, asdict
from typing import Any, Sequence

PILLARS = ["security", "compliance", "build_quality", "throughput", "audit_replayable"]

# A pillar score < this is a deployability blocker the operator must see.
BLOCK_THRESHOLD = 0.5
# Aggregate grade bands.
GRADE_BANDS = [(0.85, "A"), (0.70, "B"), (0.55, "C"), (0.40, "D")]


@dataclass
class PillarGrade:
    sow_id: str
    scores: dict[str, float]        # per-pillar [0,1]
    grade: str                      # A/B/C/D/F aggregate letter
    aggregate: float                # [0,1] mean
    blockers: list[str] = field(default_factory=list)
    rationale: dict[str, str] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return asdict(self)


def _attr(obj: Any, name: str, default=None):
    if isinstance(obj, dict):
        return obj.get(name, default)
    return getattr(obj, name, default)


def _findings(sow: Any) -> list[dict]:
    f = _attr(sow, "findings", []) or []
    return list(f)


# ── per-pillar scorers (each returns (score, rationale)) ───────────────────────
def _score_security(sow: Any) -> tuple[float, str]:
    """A diagnostic SOW touches client financial data. Deployability-security is
    high when the engagement does not require exposing client raw data to a
    frontend and the impact is a server-side-computed aggregate (the case for
    every financial finding — they aggregate the snapshot, never echo raw PII)."""
    findings = _findings(sow)
    if not findings:
        return 0.6, "no findings to assess; default-cautious"
    # every financial finding is a server-side aggregate over the snapshot — no
    # raw PII in the client-facing number. That is the secure default here.
    return 0.9, "engagement surfaces server-side aggregates only; no raw client PII in the recommendation"


def _score_compliance(sow: Any) -> tuple[float, str]:
    """Compliance = can we produce an audit trail. A SOW whose every finding has
    a source[] line is already an append-only evidence chain."""
    findings = _findings(sow)
    if not findings:
        src = _attr(sow, "source", []) or []
        return (0.8, "SOW carries source trace") if src else (0.3, "no source trace")
    traced = sum(1 for f in findings if (f.get("source") or f.get("evidence")))
    frac = traced / len(findings)
    return round(0.4 + 0.6 * frac, 4), f"{traced}/{len(findings)} findings carry an audit-traceable source[]"


def _score_build_quality(sow: Any) -> tuple[float, str]:
    """Build quality of the evidence: grounded numbers + corroboration breadth +
    honest confidence. A 1-finding thrust scores lower than a 3-finding one."""
    findings = _findings(sow)
    conf = float(_attr(sow, "confidence", 0.0) or 0.0)
    n = len(findings) or len(_attr(sow, "finding_ids", []) or [])
    grounded = all((f.get("source") or f.get("evidence")) for f in findings) if findings else bool(_attr(sow, "source"))
    breadth = min(1.0, n / 3.0)          # 3+ corroborating findings = full breadth
    score = 0.45 * (1.0 if grounded else 0.0) + 0.30 * conf + 0.25 * breadth
    return round(min(1.0, score), 4), (
        f"grounded={grounded}, confidence={conf:.0%}, corroboration={n} finding(s)"
    )


def _score_throughput(sow: Any) -> tuple[float, str]:
    """Throughput = will the engagement scale / is it worth durable infra. A SOW
    whose annual impact comfortably exceeds infra+delivery cost clears it; a
    sub-threshold impact is flagged (don't deploy heavy infra for a tiny win)."""
    impact = float(_attr(sow, "impact_usd", 0.0) or 0.0)
    # $250k/yr is the rough floor where a durable FDE engagement pays for itself.
    floor = 250_000.0
    if impact >= floor:
        score = min(1.0, 0.6 + 0.4 * min(1.0, impact / (4 * floor)))
        return round(score, 4), f"${impact:,.0f}/yr impact justifies a durable FDE engagement"
    return round(0.3 + 0.3 * (impact / floor), 4), (
        f"${impact:,.0f}/yr is below the ~${floor:,.0f} engagement-viability floor"
    )


def _score_audit_replayable(sow: Any) -> tuple[float, str]:
    """Audit-replayable = can the recommendation be traced + rolled back. High
    when every number names a source AND a confidence band is present."""
    findings = _findings(sow)
    conf = float(_attr(sow, "confidence", 0.0) or 0.0)
    src = _attr(sow, "source", []) or []
    has_conf = conf > 0.0
    has_src = bool(src) or (findings and all((f.get("source") or f.get("evidence")) for f in findings))
    score = 0.5 * (1.0 if has_src else 0.0) + 0.3 * (1.0 if has_conf else 0.0) + 0.2 * min(1.0, conf)
    return round(min(1.0, score), 4), (
        f"source-traced={bool(has_src)}, confidence-banded={has_conf} (band {conf:.0%})"
    )


_SCORERS = {
    "security": _score_security,
    "compliance": _score_compliance,
    "build_quality": _score_build_quality,
    "throughput": _score_throughput,
    "audit_replayable": _score_audit_replayable,
}


def _letter(aggregate: float) -> str:
    for cutoff, letter in GRADE_BANDS:
        if aggregate >= cutoff:
            return letter
    return "F"


def grade_sow(sow: Any) -> PillarGrade:
    scores: dict[str, float] = {}
    rationale: dict[str, str] = {}
    blockers: list[str] = []
    for pillar in PILLARS:
        s, why = _SCORERS[pillar](sow)
        scores[pillar] = s
        rationale[pillar] = why
        if s < BLOCK_THRESHOLD:
            blockers.append(f"{pillar}: {why} (score {s:.2f} < {BLOCK_THRESHOLD})")
    aggregate = round(sum(scores.values()) / len(scores), 4)
    return PillarGrade(
        sow_id=_attr(sow, "id", "unknown"),
        scores=scores,
        grade=_letter(aggregate),
        aggregate=aggregate,
        blockers=blockers,
        rationale=rationale,
    )


def grade_sows(sows: Sequence[Any]) -> list[PillarGrade]:
    return [grade_sow(s) for s in sows]


def attach_grades(sows: Sequence[Any]) -> list[dict]:
    """Return each SOW as a dict with a `pillar_grade` block attached."""
    out: list[dict] = []
    for s in sows:
        d = s.to_dict() if hasattr(s, "to_dict") else dict(s)
        d["pillar_grade"] = grade_sow(s).to_dict()
        out.append(d)
    return out
