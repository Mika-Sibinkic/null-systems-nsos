"""Tests for engine/council/recursive_weights.py and council.py."""
from __future__ import annotations
import sys
from pathlib import Path

# Allow importing from engine/ without packaging
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from engine.council import rank_findings, run_council  # noqa: E402
from engine.council.recursive_weights import cosine, z_norm  # noqa: E402


def _emb(*xs):
    return list(xs)


def test_cosine_basic():
    assert cosine(_emb(1, 0), _emb(1, 0)) == 1.0
    assert cosine(_emb(1, 0), _emb(0, 1)) == 0.0
    assert abs(cosine(_emb(1, 1), _emb(1, 0)) - 0.7071) < 0.001


def test_z_norm_handles_zero_sd():
    assert z_norm(5, [5, 5, 5]) == 0.0


def test_rank_orders_higher_impact_first():
    findings = [
        {"id": "low", "team": "financial", "impact_usd": 10000, "impact_hours": 50, "embedding": _emb(0.1, 0.1, 0.1)},
        {"id": "high", "team": "financial", "impact_usd": 500000, "impact_hours": 800, "embedding": _emb(0.1, 0.1, 0.1)},
        {"id": "mid", "team": "financial", "impact_usd": 100000, "impact_hours": 200, "embedding": _emb(0.1, 0.1, 0.1)},
    ]
    ranked = rank_findings(findings, ceo_priorities=[], known_baseline=[])
    assert ranked[0].finding_id == "high"
    assert ranked[-1].finding_id == "low"


def test_priority_alignment_boosts_score():
    base = {"id": "f1", "team": "ops", "impact_usd": 100000, "impact_hours": 200, "embedding": _emb(1, 0, 0)}
    other = {"id": "f2", "team": "ops", "impact_usd": 100000, "impact_hours": 200, "embedding": _emb(0, 1, 0)}
    priorities = [{"text": "tilt one", "embedding": _emb(1, 0, 0), "weight": 1.0}]
    ranked = rank_findings([base, other], ceo_priorities=priorities, known_baseline=[])
    assert ranked[0].finding_id == "f1"


def test_novelty_demotes_already_known():
    f_new = {"id": "new", "team": "ops", "impact_usd": 100000, "impact_hours": 200, "embedding": _emb(1, 0, 0)}
    f_known = {"id": "known", "team": "ops", "impact_usd": 100000, "impact_hours": 200, "embedding": _emb(0, 1, 0)}
    known = [{"text": "we already know this one", "embedding": _emb(0, 1, 0)}]
    ranked = rank_findings([f_new, f_known], ceo_priorities=[], known_baseline=known)
    assert ranked[0].finding_id == "new"


def test_run_council_endtoend_deterministic():
    findings = [
        {"id": "a", "team": "financial", "impact_usd": 50000, "impact_hours": 100, "embedding": _emb(0.5, 0.5)},
        {"id": "b", "team": "operational", "impact_usd": 200000, "impact_hours": 400, "embedding": _emb(0.5, 0.5)},
        {"id": "c", "team": "strategic", "impact_usd": 100000, "impact_hours": 200, "embedding": _emb(0.5, 0.5)},
    ]
    ranked = run_council(findings, ceo_priorities=[], known_baseline=[], debate_rounds=1)
    assert ranked[0].finding_id == "b"
    assert all(r.borda > 0 for r in ranked)


if __name__ == "__main__":
    # Cheap test runner
    failures = []
    for name, fn in list(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn()
                print(f"✓ {name}")
            except AssertionError as e:
                failures.append((name, str(e)))
                print(f"✗ {name}: {e}")
    print(f"\n{len(failures)} failures" if failures else "\nALL PASS")
    sys.exit(1 if failures else 0)
