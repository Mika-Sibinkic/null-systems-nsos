"""Recursive-weight scoring for council finding aggregation.

Implements the algorithm from docs/COUNCIL-PROTOCOL.md:
  composite = w_prio*prio + w_nov*novelty + w_corrob*corroboration + w_impact*impact
  final     = borda_position * (1 + composite)

The Borda position comes from a pairwise LLM-judge tournament (see council.py).
"""
from __future__ import annotations
from dataclasses import dataclass
from typing import Iterable, Sequence
import math
import statistics

DEFAULT_WEIGHTS = {
    "priority": 0.30,
    "novelty": 0.25,
    "corroboration": 0.20,
    "impact": 0.25,
}


def cosine(a: Sequence[float], b: Sequence[float]) -> float:
    if not a or not b or len(a) != len(b):
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(y * y for y in b))
    if na == 0 or nb == 0:
        return 0.0
    return dot / (na * nb)


def z_norm(value: float, population: Sequence[float]) -> float:
    if len(population) < 2:
        return 0.0
    mean = statistics.fmean(population)
    sd = statistics.stdev(population)
    if sd == 0:
        return 0.0
    return (value - mean) / sd


@dataclass
class ScoreBreakdown:
    finding_id: str
    priority: float
    novelty: float
    corroboration: float
    impact: float
    composite: float
    borda: float
    final: float


def score_finding(
    finding: dict,
    all_findings: Sequence[dict],
    ceo_priorities: Sequence[dict],
    known_baseline: Sequence[dict],
    *,
    weights: dict = None,
) -> ScoreBreakdown:
    """Compute the multiplicative composite for a single finding.

    Borda position is set to 0.0 here — populate via run_council() which
    runs the pairwise tournament and back-fills.
    """
    w = weights or DEFAULT_WEIGHTS
    emb = finding.get("embedding", [])

    # (a) Priority alignment
    prio = max(
        (cosine(emb, p.get("embedding", [])) * float(p.get("weight", 1.0)) for p in ceo_priorities),
        default=0.0,
    )

    # (b) Novelty
    novelty = 1.0 - max(
        (cosine(emb, k.get("embedding", [])) for k in known_baseline),
        default=0.0,
    )

    # (c) Cross-team corroboration
    cluster_teams = {finding["team"], *(c.get("team") for c in finding.get("cluster", []))}
    corrob = math.log2(1 + len(cluster_teams))

    # (d) Impact (z-normalized blend)
    usd_pop = [f.get("impact_usd", 0) for f in all_findings]
    hours_pop = [f.get("impact_hours", 0) for f in all_findings]
    impact = 0.6 * z_norm(finding.get("impact_usd", 0), usd_pop) + 0.4 * z_norm(
        finding.get("impact_hours", 0), hours_pop
    )

    composite = (
        w["priority"] * prio
        + w["novelty"] * novelty
        + w["corroboration"] * corrob
        + w["impact"] * impact
    )

    return ScoreBreakdown(
        finding_id=finding["id"],
        priority=prio,
        novelty=novelty,
        corroboration=corrob,
        impact=impact,
        composite=composite,
        borda=0.0,
        final=0.0,
    )


def rank_findings(
    findings: Sequence[dict],
    ceo_priorities: Sequence[dict],
    known_baseline: Sequence[dict],
    *,
    borda_positions: dict[str, float] | None = None,
    weights: dict | None = None,
) -> list[ScoreBreakdown]:
    """Score + rank findings. Provide pre-computed borda_positions from
    council.run_council() for the full algorithm; otherwise borda defaults to
    1.0 (i.e. ranking is by composite alone, lower fidelity but useful for tests).
    """
    breakdowns = [
        score_finding(f, findings, ceo_priorities, known_baseline, weights=weights)
        for f in findings
    ]
    for b in breakdowns:
        b.borda = (borda_positions or {}).get(b.finding_id, 1.0)
        b.final = b.borda * (1 + b.composite)

    return sorted(breakdowns, key=lambda x: -x.final)
