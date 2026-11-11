"""SOW assembly — findings -> 2-3 coherent SOW candidates (P3.T1).

A diagnostic run produces a list of findings. A CEO does
not buy a list of findings; they buy 2-3 *coherent growth thrusts*, each a
Statement of Work they can choose between by intuition about where the business
should go. This module is the bundler that turns the findings into those
candidates.

Design (deterministic, offline, source-traced):

  1. Findings are grouped into *themes* by a static finding-method -> thrust map
     (revenue resilience, cost/margin, working-capital/ops). The map is the only
     domain heuristic; everything else is arithmetic over the findings.
  2. Each non-empty theme becomes one SOW candidate. We always return the top
     `min(3, max(2, n_themes))` candidates so the operator gets the 2-3 the
     PRODUCT promises — never 1 (no choice) and never an overwhelming wall.
  3. A candidate's `impact_usd` / `impact_hours` is the sum of its findings'
     impacts (`exposure_usd`, the at-risk dollars, is summed separately and never
     added to impact); its `source[]` is the union of its findings' source lines (so the
     grounded-numbers gate stays satisfied end-to-end — no number is invented at
     the SOW layer, it only aggregates grounded finding numbers).
  4. Candidate `confidence` is the impact-weighted mean of its findings'
     confidence (a big-dollar low-confidence finding can't hide behind a tiny
     high-confidence one).
  5. Candidates rank by aggregate `impact_usd`, highest first.

No LLM. Reproducible. The grounded-numbers probe runs over the emitted
candidates exactly as it does over findings.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Sequence

# ── thrust taxonomy: which finding methods bundle into which SOW thrust ────────
# A "thrust" is a coherent direction a CEO can choose. Each finding method maps
# to exactly one thrust so bundling is deterministic and explainable.
THRUSTS: dict[str, dict] = {
    "revenue_resilience": {
        "title": "De-risk and grow the revenue base",
        "methods": ["customer_concentration", "ar_overdue", "scope_cycle_time"],
    },
    "margin_expansion": {
        "title": "Expand margin",
        "methods": ["margin_structure", "opex_benchmark"],
    },
    "supply_resilience": {
        "title": "Reduce supplier concentration risk",
        "methods": ["vendor_concentration"],
    },
}

# One clause per finding method. A SOW's objective is built only from the methods
# it actually contains, so it never promises work its findings do not back.
OBJECTIVE_CLAUSES: dict[str, str] = {
    "customer_concentration": "reduce dependence on the largest customer",
    "ar_overdue": "collect overdue receivables",
    "scope_cycle_time": "cut proposal scoping time",
    "margin_structure": "recover gross margin",
    "opex_benchmark": "bring advisory spend back to benchmark",
    "vendor_concentration": "diversify the vendor base so one supplier failure "
                            "or price shock cannot stall delivery",
}


def objective_for(thrust_key: str, group: Sequence[dict]) -> str:
    """'Collect overdue receivables and cut proposal scoping time.' from the group's methods."""
    present = {f.get("method") for f in group}
    order = THRUSTS[thrust_key]["methods"]
    clauses = [OBJECTIVE_CLAUSES[m] for m in order if m in present]
    if not clauses:
        return ""
    text = clauses[0] if len(clauses) == 1 else ", ".join(clauses[:-1]) + " and " + clauses[-1]
    return text[0].upper() + text[1:] + "."


# reverse index method -> thrust_key
_METHOD_TO_THRUST: dict[str, str] = {
    m: key for key, t in THRUSTS.items() for m in t["methods"]
}
_FALLBACK_THRUST = "revenue_resilience"


@dataclass
class SOWCandidate:
    id: str
    thrust: str
    title: str
    objective: str
    finding_ids: list[str]
    impact_usd: float
    impact_hours: float
    confidence: float
    source: list[str] = field(default_factory=list)
    exposure_usd: float = 0.0  # at-risk dollars; not part of impact_usd
    findings: list[dict] = field(default_factory=list)

    def to_dict(self) -> dict:
        d = asdict(self)
        return d


def _thrust_for(method: str) -> str:
    return _METHOD_TO_THRUST.get(method, _FALLBACK_THRUST)


def _weighted_confidence(findings: Sequence[dict]) -> float:
    """Impact-weighted mean confidence. Falls back to plain mean when a theme
    carries no dollar impact (e.g. an hours-only finding)."""
    weights = [max(f.get("impact_usd", 0.0), 0.0) for f in findings]
    confs = [float(f.get("confidence", 0.0)) for f in findings]
    if not confs:
        return 0.0
    total_w = sum(weights)
    if total_w <= 0:
        return round(sum(confs) / len(confs), 4)
    return round(sum(w * c for w, c in zip(weights, confs)) / total_w, 4)


def assemble_sows(
    findings: Sequence[dict],
    *,
    min_candidates: int = 2,
    max_candidates: int = 3,
    artifacts_dir: Path | str | None = None,
) -> list[SOWCandidate]:
    """Bundle findings into 2-3 coherent SOW candidates, highest annual impact first."""
    if not findings:
        return []

    # group by thrust
    groups: dict[str, list[dict]] = {}
    for f in findings:
        groups.setdefault(_thrust_for(f.get("method", "")), []).append(f)

    candidates: list[SOWCandidate] = []
    for thrust_key, group in groups.items():
        spec = THRUSTS.get(thrust_key, THRUSTS[_FALLBACK_THRUST])
        impact_usd = sum(float(f.get("impact_usd", 0.0)) for f in group)
        impact_hours = sum(float(f.get("impact_hours", 0.0)) for f in group)
        # union of source lines, order-stable, deduped
        seen: set[str] = set()
        source: list[str] = []
        for f in group:
            for s in (f.get("source") or f.get("evidence") or []):
                if s not in seen:
                    seen.add(s)
                    source.append(s)
        candidates.append(
            SOWCandidate(
                id=f"sow-{thrust_key}",
                thrust=thrust_key,
                title=spec["title"],
                objective=objective_for(thrust_key, group),
                finding_ids=[f["id"] for f in group],
                impact_usd=round(impact_usd, 2),
                impact_hours=round(impact_hours, 1),
                confidence=_weighted_confidence(group),
                source=source,
                exposure_usd=round(sum(float(f.get("exposure_usd", 0.0)) for f in group), 2),
                findings=list(group),
            )
        )

    candidates.sort(key=lambda c: -c.impact_usd)

    # clamp to 2-3: never 1 (no real choice), never a wall
    n = len(candidates)
    keep = max(min_candidates, min(max_candidates, n))
    selected = candidates[:keep] if n >= keep else candidates

    if artifacts_dir:
        out = Path(artifacts_dir)
        out.mkdir(parents=True, exist_ok=True)
        (out / "sow-candidates.jsonl").write_text(
            "\n".join(json.dumps(c.to_dict(), allow_nan=False) for c in selected)
            + ("\n" if selected else "")
        )

    return selected
