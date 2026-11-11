"""End-to-end real pipe on synthetic-client-a (P5.T3).

Runs the WHOLE diagnostic, not fixtures, through `scripts/run_synthetic.py`:
QuickBooks export -> baseline -> findings -> review gate -> SOWs ->
side-by-side -> CEO report -> FDE packet -> flywheel prediction row. Then it
checks the money flow with the real grounded_numbers and quality_judge probes.

Every artifact lands under pytest's tmp_path, so the suite never depends on a
previous run having left files in runs/.
"""
import os
import subprocess
import sys
from pathlib import Path

import pytest

import client.adapters.quickbooks as qb
import scripts.run_synthetic as pipe
import engine.sow.metrics as metrics

ROOT = Path(__file__).resolve().parents[1]


EXPOSURE_METHODS = {"vendor_concentration", "customer_concentration", "ar_overdue"}


@pytest.fixture(scope="module")
def run(tmp_path_factory):
    out = tmp_path_factory.mktemp("runs") / pipe.RUN_ID
    art = pipe.run(out)
    art["out"] = out
    return art


def test_e2e_baseline_is_schema_valid_and_token_minted(run):
    assert run["web_token"], "onboarding must mint a scoped web token"
    assert qb.validate_baseline(run["baseline"]) == []


def test_e2e_pipe_produces_scored_sows(run):
    sbs = run["sbs"]
    assert 2 <= len(sbs.columns) <= 3
    for c in sbs.columns:
        assert c.impact_usd > 0 or c.exposure_usd > 0
        assert c.grade in ("A", "B", "C", "D", "F")
        assert 0.0 <= c.wwod_score <= 1.0
        assert c.source
    assert sbs.recommended_sow_id in {c.sow_id for c in sbs.columns}


def test_e2e_findings_trace_to_real_accounting(run):
    for f in run["findings"]:
        assert f.get("impact_usd", 0) >= 0
        assert f.get("source") or f.get("evidence"), f"{f['id']} ungrounded"


def test_e2e_run_artifacts_written(run):
    out = run["out"]
    for rel in ("sow/sow-candidates.jsonl", "presentation/side-by-side.json",
                "presentation/report.md", "handoff/fde-handoff-packet.json",
                "review/fde_queue.jsonl"):
        assert (out / rel).exists(), rel


def test_e2e_held_findings_are_not_priced(run):
    """fin-fin-004 (opex_benchmark, confidence 0.60) sits below the review floor."""
    held_ids = {f["id"] for f in run["held"]}
    assert "fin-fin-004" in held_ids
    for s in run["sows"]:
        assert not held_ids & set(s.finding_ids), f"{s.id} prices a held finding"
    assert "## Pending review" in run["report"]


def test_e2e_metrics_artifact_passes_grounded_numbers_probe(run):
    """Run the REAL grounded_numbers probe over the run's SOW metrics."""
    sow_dir = run["out"] / "sow"
    metrics.metrics_for_all(run["sows"], run["baseline"], artifacts_dir=sow_dir)
    r = subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "probes" / "grounded_numbers.py"),
         str(sow_dir / "metrics.jsonl")],
        capture_output=True, text=True,
    )
    assert r.returncode == 0, f"grounded_numbers failed on e2e metrics: {r.stdout}\n{r.stderr}"


def test_e2e_report_passes_quality_judge_gate(run):
    """Run the REAL quality_judge gate over the e2e decision report."""
    env = dict(os.environ, NSOS_JUDGE_OFFLINE_DETERMINISTIC="1")
    r = subprocess.run(
        [sys.executable, str(ROOT / "engine" / "gauntlets" / "quality_judge.py"),
         "--gate", "--text", run["report"][:3000]],
        capture_output=True, text=True, env=env,
    )
    assert r.returncode == 0, f"quality_judge gated the e2e report: {r.stdout}\n{r.stderr}"


def test_e2e_flywheel_prediction_recorded(run):
    rows = pipe.outcome_loop.load_ledger(run["ledger"])
    assert len(rows) == 1
    assert rows[0]["record_type"] == "prediction"
    assert rows[0]["run_id"] == pipe.RUN_ID
    assert rows[0]["predicted"]["impact_usd"] > 0


def test_e2e_exposure_never_counts_as_annual_impact(run):
    """Risk exposure (concentration, one-time AR) is not a yearly saving: it must
    stay out of every SOW impact_usd, so EBITDA lift stays a sane number."""
    for s in run["sows"]:
        for f in s.findings:
            if f["method"] in EXPOSURE_METHODS:
                assert f["impact_usd"] == 0, f"{f['id']} books exposure as impact"
        assert s.impact_usd == sum(f["impact_usd"] for f in s.findings)
        m = metrics.metrics_for(s, run["baseline"])
        assert m.ebitda_uplift_pct is None or m.ebitda_uplift_pct < 100, (s.id, m.ebitda_uplift_pct)


def test_e2e_objective_names_only_contained_work(run):
    """A SOW objective must not promise work its findings do not contain."""
    clauses = pipe.assembly.OBJECTIVE_CLAUSES
    for s in run["sows"]:
        named = {m for m, clause in clauses.items() if clause in s.objective.lower()}
        assert named == {f["method"] for f in s.findings}, (s.id, s.objective)


def test_e2e_every_assumed_rate_is_declared_in_source(run):
    """The margin dollars are an assumed recovery rate, so the finding says so."""
    margin = [f for f in run["findings"] if f["method"] == "margin_structure"]
    assert margin, "synthetic-client-a should flag its 60% gross margin"
    assert any(s.endswith("[LIKELY]") for s in margin[0]["source"]), margin[0]["source"]
