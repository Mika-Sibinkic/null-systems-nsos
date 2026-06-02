"""Tests for the financial meta-team + data->findings engine (P2.T1/T2)."""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import importlib  # noqa: E402

team = importlib.import_module("engine.meta-levels.financial.team")
findings_mod = importlib.import_module("engine.meta-levels.financial.findings")

BASELINE = json.loads(
    (ROOT / "client" / "snapshots" / "synth-acme-services" / "baseline.json").read_text()
)


# ── P2.T1: question battery runs against baseline ──────────────────────────────
def test_questions_load():
    qs = team.load_questions()
    assert len(qs) >= 5
    assert all("method" in q and "id" in q for q in qs)


def test_team_runs_battery_against_baseline():
    out = team.run_team(BASELINE)
    assert out["team"] == "financial"
    assert out["tenant_id"] == "synth-acme-services"
    assert out["questions_run"] == len(team.load_questions())
    # the financial team must genuinely answer most questions from real data
    assert out["answered"] >= 4
    for r in out["results"]:
        assert "question_id" in r and "answered" in r


def test_team_answers_are_grounded():
    out = team.run_team(BASELINE)
    for r in out["results"]:
        if r["answered"]:
            assert r["analytic"] is not None
            assert r["analytic"].get("source"), f"{r['question_id']} answered without source"


# ── P2.T2: findings engine emits grounded impacts ─────────────────────────────
def test_findings_emitted_with_impact():
    fs = findings_mod.run_findings(BASELINE)
    assert fs, "financial engine produced no findings from a real baseline"
    for f in fs:
        has_impact = f.get("impact_usd", 0) > 0 or f.get("impact_hours", 0) > 0
        assert has_impact, f"finding {f['id']} has no impact"


def test_findings_carry_evidence_and_confidence():
    fs = findings_mod.run_findings(BASELINE)
    for f in fs:
        assert f.get("evidence"), f"{f['id']} missing evidence[]"
        assert f.get("source"), f"{f['id']} missing source[]"
        assert f.get("confidence") is not None
        assert f.get("bottleneck"), f"{f['id']} missing bottleneck"


def test_findings_pass_grounded_numbers_shape():
    # mirror build/probes/grounded_numbers.py
    fs = findings_mod.run_findings(BASELINE)
    for f in fs:
        if f.get("impact_usd") or f.get("impact_hours"):
            src = f.get("evidence") or f.get("source")
            assert src and f.get("confidence") is not None


def test_findings_sorted_by_impact_desc():
    fs = findings_mod.run_findings(BASELINE)
    impacts = [f.get("impact_usd", 0) for f in fs]
    assert impacts == sorted(impacts, reverse=True)


def test_findings_written_to_run_dir(tmp_path):
    out = tmp_path / "findings.jsonl"
    fs = findings_mod.run_findings(BASELINE, out_path=out)
    assert out.exists()
    lines = [l for l in out.read_text().splitlines() if l.strip()]
    assert len(lines) == len(fs)
    for l in lines:
        json.loads(l)  # valid JSON per line


def test_vendor_concentration_flags_subcontractor():
    a = findings_mod.a_vendor_concentration(BASELINE)
    assert a is not None
    # Subcontractor Group ($8.4M) dominates vendor spend -> flagged concentration
    assert a["flagged"] is True
    assert a["top_vendor"] == "Subcontractor Group"


def test_ar_overdue_detects_two_overdue():
    a = findings_mod.a_ar_overdue(BASELINE)
    assert a is not None
    assert a["overdue_count"] == 2  # INV-1003 + INV-1006
    assert a["exposure_usd"] == 235000.0  # 95000 + 140000


# ── P2.T3: grounding gate wired into the producer (fail-closed) ───────────────
def test_grounding_gate_passes_real_findings():
    for f in findings_mod.run_findings(BASELINE):
        # must not raise — every real finding is grounded
        assert findings_mod.assert_grounded(f) is f


def test_grounding_gate_rejects_missing_source():
    import pytest
    bad = {"id": "x", "impact_usd": 1000, "evidence": [], "source": [], "confidence": 0.7}
    with pytest.raises(findings_mod.UngroundedFindingError):
        findings_mod.assert_grounded(bad)


def test_grounding_gate_rejects_missing_confidence():
    import pytest
    bad = {"id": "y", "impact_usd": 1000, "evidence": ["acct.x=1000"], "confidence": None}
    with pytest.raises(findings_mod.UngroundedFindingError):
        findings_mod.assert_grounded(bad)


def test_grounding_gate_allows_zero_impact_without_source():
    # no impact asserted -> grounding not required
    ok = {"id": "z", "impact_usd": 0, "impact_hours": 0}
    assert findings_mod.assert_grounded(ok) is ok
