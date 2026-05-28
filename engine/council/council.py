"""Council orchestrator — runs the pairwise LLM-judge tournament + debate rounds.

This is the entry point called by the top-level LangGraph state machine after
all 6 meta-teams have produced findings.

Skeleton: the LLM-judge calls are stubbed to deterministic comparisons for
unit-testing. Wire to engine/router/llm_router.py for production.
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
    """Offline-deterministic judge for tests. Picks higher impact_usd as winner.

    Production path: `engine.router.nim_client.judge_pair` (NIM v4 llama-3.3-70b).
    This function remains the offline fallback so tests can run without network.
    """
    if a.get("impact_usd", 0) > b.get("impact_usd", 0):
        return "A"
    if b.get("impact_usd", 0) > a.get("impact_usd", 0):
        return "B"
    return "TIE"


def nim_judge(a: dict, b: dict) -> str:
    """Production judge — routes through engine.router.nim_client (NIM only).

    Falls back to deterministic_judge if NIM client cannot be imported (offline
    or env missing).
    """
    try:
        from ..router.nim_client import judge_pair
        return judge_pair(a, b, criterion="higher client impact ($ + hours saved)")
    except Exception:
        return deterministic_judge(a, b)


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


def run_debate_round(
    ranked: list[ScoreBreakdown],
    findings_by_id: dict[str, dict],
    *,
    nominator: Callable[[str, list[ScoreBreakdown]], dict | None] = None,
    judge: Callable[[list[dict]], list[tuple[str, str]]] = None,
    max_swaps: int = 3,
) -> tuple[list[ScoreBreakdown], list[dict]]:
    """One round of council debate. Returns (new_ranked, debate_log)."""
    debate_log: list[dict] = []
    if nominator is None or judge is None:
        return ranked, debate_log  # No-op when stubs aren't wired

    teams = sorted({findings_by_id[r.finding_id]["team"] for r in ranked})
    promotes, demotes = [], []
    for t in teams:
        nom = nominator(t, ranked)
        if not nom:
            continue
        debate_log.append(nom)
        if nom["action"] == "promote":
            promotes.append(nom)
        else:
            demotes.append(nom)

    swaps = judge(debate_log)[:max_swaps]
    by_id = {r.finding_id: r for r in ranked}
    for fid_up, fid_down in swaps:
        if fid_up in by_id and fid_down in by_id:
            by_id[fid_up].final, by_id[fid_down].final = (
                by_id[fid_down].final,
                by_id[fid_up].final,
            )
    new_ranked = sorted(by_id.values(), key=lambda r: -r.final)
    return new_ranked, debate_log


def run_council(
    findings: Sequence[dict],
    ceo_priorities: Sequence[dict],
    known_baseline: Sequence[dict],
    *,
    judge: Callable[[dict, dict], str] = deterministic_judge,
    debate_rounds: int = 2,
    artifacts_dir: Path | str | None = None,
) -> list[ScoreBreakdown]:
    """End-to-end council pass."""
    borda = borda_from_pairwise(findings, judge=judge)
    ranked = rank_findings(findings, ceo_priorities, known_baseline, borda_positions=borda)

    findings_by_id = {f["id"]: f for f in findings}
    debate_log_all: list[dict] = []
    for _ in range(debate_rounds):
        ranked, log = run_debate_round(ranked, findings_by_id)
        debate_log_all.extend(log)
        if not log:
            break

    if artifacts_dir:
        out = Path(artifacts_dir)
        out.mkdir(parents=True, exist_ok=True)
        (out / "candidates.jsonl").write_text(
            "\n".join(json.dumps(_dump(r)) for r in ranked)
        )
        (out / "debate-rounds.jsonl").write_text(
            "\n".join(json.dumps(d) for d in debate_log_all)
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
