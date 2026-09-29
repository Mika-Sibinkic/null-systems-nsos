"""Tests for the side-by-side SOW comparison + decision report (P4.T1).

Covers `presentation/side-by-side/sbs.py` and `render_sow_report` in
`presentation/exec-report/report_generator.py`. Uses REAL SOW candidates
assembled from the synthetic tenant baseline (not fixtures), then runs the
actual quality_judge gate over the rendered client-facing report —
verification, not assertion.
"""
import importlib
import importlib.util
import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

assembly = importlib.import_module("engine.sow.assembly")
findings_mod = importlib.import_module("engine.meta-levels.financial.findings")

BASELINE_TENANT = "synth-acme-services"


def _load(name: str, rel: str):
    spec = importlib.util.spec_from_file_location(name, str(ROOT / rel))
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod  # required so @dataclass can resolve cls.__module__
    spec.loader.exec_module(mod)
    return mod


sbs_mod = _load("nsos_sbs_test", "presentation/side-by-side/sbs.py")
report_mod = _load("nsos_report_test", "presentation/exec-report/report_generator.py")


def _baseline():
    return json.loads(
        (ROOT / "client" / "snapshots" / BASELINE_TENANT / "baseline.json").read_text()
    )


def _firm():
    return json.loads((ROOT / "examples" / "synthetic-client-a" / "firm.json").read_text())


def _sows(baseline):
    return assembly.assemble_sows(findings_mod.run_findings(baseline))


# ── side-by-side module ───────────────────────────────────────────────────────

def test_sbs_has_two_to_three_columns():
    b = _baseline()
    sbs = sbs_mod.build_side_by_side(_sows(b), b)
    assert 2 <= len(sbs.columns) <= 3


def test_every_column_carries_all_scoring_layers():
    b = _baseline()
    sbs = sbs_mod.build_side_by_side(_sows(b), b)
    for c in sbs.columns:
        # metrics
        assert c.ebitda_uplift_pct >= 0.0
        assert c.payback_months >= 0.0
        # wwod
        assert 0.0 <= c.wwod_score <= 1.0
        assert 0.0 <= c.wwod_confidence <= 1.0
        # pillar grade
        assert c.grade in ("A", "B", "C", "D", "F")
        assert 0.0 <= c.pillar_aggregate <= 1.0
        # grounding
        assert c.source, f"{c.sow_id} has no source trace"


def test_recommendation_is_a_real_column():
    b = _baseline()
    sbs = sbs_mod.build_side_by_side(_sows(b), b)
    ids = {c.sow_id for c in sbs.columns}
    assert sbs.recommended_sow_id in ids


def test_recommendation_prefers_deployable_high_conviction():
    b = _baseline()
    sbs = sbs_mod.build_side_by_side(_sows(b), b)
    rec = next(c for c in sbs.columns if c.sow_id == sbs.recommended_sow_id)
    deployable = [c for c in sbs.columns if not c.blockers]
    if deployable:
        # recommendation must be the max-WWOD among deployable
        assert rec.wwod_score == max(c.wwod_score for c in deployable)


def test_markdown_table_renders_all_columns():
    b = _baseline()
    sbs = sbs_mod.build_side_by_side(_sows(b), b)
    md = sbs_mod.render_markdown(sbs)
    for c in sbs.columns:
        assert c.title in md
    assert "Annual impact" in md
    assert "Payback" in md
    assert "recommendation" in md.lower()


def test_sbs_artifact_written(tmp_path):
    b = _baseline()
    sbs = sbs_mod.build_side_by_side(_sows(b), b)
    p = sbs_mod.write_artifact(sbs, tmp_path / "presentation" / "side-by-side.json")
    assert p.exists()
    data = json.loads(p.read_text())
    assert len(data["columns"]) == len(sbs.columns)
    assert data["recommended_sow_id"] == sbs.recommended_sow_id


def test_from_run_reads_run_candidates():
    # the synthetic run already has sow-candidates.jsonl committed
    sbs = sbs_mod.from_run("synthetic-client-a")
    assert 2 <= len(sbs.columns) <= 3
    artifact = ROOT / "runs" / "synthetic-client-a" / "presentation" / "side-by-side.json"
    assert artifact.exists()


# ── decision report ───────────────────────────────────────────────────────────

def test_report_renders_each_sow():
    b = _baseline()
    firm = _firm()
    sows = _sows(b)
    md = report_mod.render_sow_report(firm, sows, b)
    assert firm["firm_name"] in md
    for s in sows:
        assert s.title in md
    assert "Side-by-side" in md
    assert "EBITDA lift" in md
    assert "Payback" in md


def test_report_marks_one_recommendation():
    b = _baseline()
    md = report_mod.render_sow_report(_firm(), _sows(b), b)
    assert md.count("our recommendation") == 1


def test_report_passes_quality_judge_gate():
    """Run the REAL quality_judge gate over the rendered report (offline-
    deterministic mode so it is reproducible without a live LLM)."""
    b = _baseline()
    md = report_mod.render_sow_report(_firm(), _sows(b), b)
    env = dict(os.environ, NSOS_JUDGE_OFFLINE_DETERMINISTIC="1")
    r = subprocess.run(
        [sys.executable, str(ROOT / "engine" / "gauntlets" / "quality_judge.py"),
         "--gate", "--text", md[:3000]],
        capture_output=True, text=True, env=env,
    )
    assert r.returncode == 0, f"quality_judge gated the report: {r.stdout}\n{r.stderr}"
