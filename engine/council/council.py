"""Council orchestrator — pairwise judge tournament -> Borda positions -> recursive weights.

Called after the meta-teams have produced findings. The only judge today is
deterministic_judge (higher impact_usd wins). No model ranks findings yet.
"""
from __future__ import annotations
from collections import defaultdict
from itertools import combinations
import json
import math
import random
from pathlib import Path
from typing import Callable, Sequence

from .recursive_weights import rank_findings, ScoreBreakdown


def deterministic_judge(a: dict, b: dict) -> str:
    """The council's judge: the higher impact_usd wins."""
    if a.get("impact_usd", 0) > b.get("impact_usd", 0):
        return "A"
    if b.get("impact_usd", 0) > a.get("impact_usd", 0):
        return "B"
    return "TIE"


def borda_from_pairwise(
    findings: Sequence[dict],
    judge: Callable[[dict, dict], str],
    *,
    sample_size: int | None = None,
    seed: int = 42,
) -> dict[str, float]:
    """Run pairwise comparisons, aggregate into Borda positions.

    For N findings:
      - if N <= 20: full round-robin (N*(N-1)/2 pairs)
      - else: sample O(N log N) random pairs
    """
    n = len(findings)
    if n <= 1:
        return {f["id"]: 1.0 for f in findings}

    pairs = list(combinations(findings, 2))
    if sample_size is None:
        sample_size = n * (n - 1) // 2 if n <= 20 else int(n * math.log2(n))
    if sample_size < len(pairs):
        rng = random.Random(seed)
        pairs = rng.sample(pairs, sample_size)

    wins: dict[str, int] = defaultdict(int)
    for a, b in pairs:
        result = judge(a, b)
        if result == "A":
            wins[a["id"]] += 1
        elif result == "B":
            wins[b["id"]] += 1
        else:
            wins[a["id"]] += 0.5
            wins[b["id"]] += 0.5

    # Borda position: N - rank-by-wins (higher wins → higher Borda)
    sorted_ids = sorted(wins, key=lambda k: -wins[k])
    return {fid: float(n - i) for i, fid in enumerate(sorted_ids)}


def run_council(
    findings: Sequence[dict],
    ceo_priorities: Sequence[dict],
    known_baseline: Sequence[dict],
    *,
    judge: Callable[[dict, dict], str] = deterministic_judge,
    artifacts_dir: Path | str | None = None,
) -> list[ScoreBreakdown]:
    """End-to-end council pass."""
    borda = borda_from_pairwise(findings, judge=judge)
    ranked = rank_findings(findings, ceo_priorities, known_baseline, borda_positions=borda)

    if artifacts_dir:
        out = Path(artifacts_dir)
        out.mkdir(parents=True, exist_ok=True)
        (out / "candidates.jsonl").write_text(
            "\n".join(json.dumps(_dump(r)) for r in ranked)
        )
        (out / "final.jsonl").write_text(
            "\n".join(json.dumps(_dump(r)) for r in ranked)
        )

    return ranked


def _dump(r: ScoreBreakdown) -> dict:
    return {
        "finding_id": r.finding_id,
        "priority": r.priority,
        "novelty": r.novelty,
        "corroboration": r.corroboration,
        "impact": r.impact,
        "composite": r.composite,
        "borda": r.borda,
        "final": r.final,
    }
