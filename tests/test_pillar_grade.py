"""Tests for the 5-pillar deployability grade (P3.T3)."""
import importlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

pg = importlib.import_module("engine.sow.pillar_grade")
assembly = importlib.import_module("engine.sow.assembly")
findings_mod = importlib.import_module("engine.meta-levels.financial.findings")

BASELINE_TENANT = "synth-acme-services"


def _real_sows():
    baseline = json.loads(
        (ROOT / "client" / "snapshots" / BASELINE_TENANT / "baseline.json").read_text()
    )
    return assembly.assemble_sows(findings_mod.run_findings(baseline))


def test_grades_all_five_pillars():
    for g in pg.grade_sows(_real_sows()):
        assert set(g.scores.keys()) == set(pg.PILLARS)
        for v in g.scores.values():
            assert 0.0 <= v <= 1.0


def test_aggregate_and_letter_grade():
    for g in pg.grade_sows(_real_sows()):
        assert 0.0 <= g.aggregate <= 1.0
        assert g.grade in {"A", "B", "C", "D", "F"}


def test_each_pillar_has_a_rationale():
    for g in pg.grade_sows(_real_sows()):
        assert set(g.rationale.keys()) == set(pg.PILLARS)
        assert all(g.rationale[p] for p in pg.PILLARS)


def test_grounded_sow_passes_compliance_and_audit():
    """Real SOWs are source-traced, so compliance + audit pillars must clear the
    block threshold."""
    for g in pg.grade_sows(_real_sows()):
        assert g.scores["compliance"] >= pg.BLOCK_THRESHOLD
        assert g.scores["audit_replayable"] >= pg.BLOCK_THRESHOLD


def test_ungrounded_sow_flags_compliance_blocker():
    ungrounded = {
        "id": "bad", "title": "t", "objective": "o", "impact_usd": 1_000_000.0,
        "impact_hours": 0.0, "confidence": 0.0, "finding_ids": ["x"],
        "source": [], "findings": [{"id": "x", "impact_usd": 1_000_000.0}],  # no source
    }
    g = pg.grade_sow(ungrounded)
    assert g.scores["compliance"] < 1.0
    assert g.scores["audit_replayable"] < pg.BLOCK_THRESHOLD
    assert any("audit_replayable" in b or "compliance" in b for b in g.blockers)


def test_tiny_impact_flags_throughput():
    tiny = {
        "id": "tiny", "title": "t", "objective": "o", "impact_usd": 12_000.0,
        "impact_hours": 0.0, "confidence": 0.7, "finding_ids": ["x"],
        "source": ["s1"], "findings": [{"id": "x", "source": ["s1"]}],
    }
    g = pg.grade_sow(tiny)
    assert g.scores["throughput"] < 0.6


def test_high_impact_clears_throughput():
    big = {
        "id": "big", "title": "t", "objective": "o", "impact_usd": 8_400_000.0,
        "impact_hours": 0.0, "confidence": 0.8, "finding_ids": ["x", "y", "z"],
        "source": ["s1"],
        "findings": [{"id": i, "source": ["s1"]} for i in ("x", "y", "z")],
    }
    g = pg.grade_sow(big)
    assert g.scores["throughput"] >= 0.6


def test_attach_grades_embeds_block():
    sows = _real_sows()
    enriched = pg.attach_grades(sows)
    assert len(enriched) == len(sows)
    for d in enriched:
        assert "pillar_grade" in d
        assert "scores" in d["pillar_grade"]
        assert "grade" in d["pillar_grade"]


def test_blockers_below_threshold_only():
    for g in pg.grade_sows(_real_sows()):
        for pillar, score in g.scores.items():
            flagged = any(b.startswith(pillar + ":") for b in g.blockers)
            assert flagged == (score < pg.BLOCK_THRESHOLD)
