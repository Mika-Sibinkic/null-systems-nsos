"""Tests for WWOD SOW scoring (P3.T2)."""
import importlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

wwod = importlib.import_module("engine.sow.wwod_score")
assembly = importlib.import_module("engine.sow.assembly")
findings_mod = importlib.import_module("engine.meta-levels.financial.findings")

BASELINE_TENANT = "synth-acme-services"


def _real_sows():
    baseline = json.loads(
        (ROOT / "client" / "snapshots" / BASELINE_TENANT / "baseline.json").read_text()
    )
    findings = findings_mod.run_findings(baseline)
    return assembly.assemble_sows(findings)


def test_every_sow_gets_a_score():
    sows = _real_sows()
    scores = wwod.score_sows(sows)
    assert len(scores) == len(sows)
    for s in scores:
        assert 0.0 <= s.wwod_score <= 1.0
        assert 0.0 <= s.confidence <= 1.0


def test_score_carries_gaps_list():
    scores = wwod.score_sows(_real_sows())
    for s in scores:
        assert isinstance(s.gaps, list)


def test_cold_start_falls_back_to_prior_not_zero():
    """With no matching patterns (cold start), a large high-confidence SOW must
    still score meaningfully — never a silent 0."""
    big_sow = {
        "id": "sow-big",
        "title": "Expand margin",
        "objective": "lift EBITDA",
        "impact_usd": 1_896_200.0,
        "impact_hours": 0.0,
        "confidence": 0.67,
        "finding_ids": ["f1", "f2"],
        "source": ["accounting.x=1", "accounting.y=2"],
    }
    sc = wwod.score_sow(big_sow)
    assert sc.wwod_score > 0.3, "large well-evidenced SOW should not score near zero at cold start"
    assert sc.prior_signal > 0.0


def test_higher_impact_scores_higher_all_else_equal():
    base = {
        "id": "a", "title": "t", "objective": "o", "impact_hours": 0.0,
        "confidence": 0.8, "finding_ids": ["x", "y"], "source": ["s1", "s2"],
    }
    low = dict(base, id="low", impact_usd=200_000.0)
    high = dict(base, id="high", impact_usd=1_800_000.0)
    assert wwod.score_sow(high).wwod_score > wwod.score_sow(low).wwod_score


def test_low_confidence_sow_flags_gap():
    weak = {
        "id": "weak", "title": "t", "objective": "o", "impact_usd": 500_000.0,
        "impact_hours": 0.0, "confidence": 0.3, "finding_ids": ["x"],
        "source": ["s1"],
    }
    sc = wwod.score_sow(weak)
    assert any("confidence" in g.lower() for g in sc.gaps)


def test_single_finding_thrust_flags_thin_corroboration():
    solo = {
        "id": "solo", "title": "t", "objective": "o", "impact_usd": 8_400_000.0,
        "impact_hours": 0.0, "confidence": 0.8, "finding_ids": ["only"],
        "source": ["s1"],
    }
    sc = wwod.score_sow(solo)
    assert any("single-finding" in g.lower() or "corroboration" in g.lower() for g in sc.gaps)


def test_attach_scores_embeds_wwod_block():
    sows = _real_sows()
    enriched = wwod.attach_scores(sows)
    assert len(enriched) == len(sows)
    for d in enriched:
        assert "wwod" in d
        assert "wwod_score" in d["wwod"]
        assert "gaps" in d["wwod"]


def test_no_new_dollar_numbers_minted():
    """WWOD scores the push, not the impact — it must not alter impact_usd."""
    sows = _real_sows()
    enriched = wwod.attach_scores(sows)
    by_id = {s.id: s for s in sows}
    for d in enriched:
        assert d["impact_usd"] == by_id[d["id"]].impact_usd
