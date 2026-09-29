"""Tests for quantified SOW success metrics (P3.T4)."""
import importlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

metrics = importlib.import_module("engine.sow.metrics")
assembly = importlib.import_module("engine.sow.assembly")
findings_mod = importlib.import_module("engine.meta-levels.financial.findings")

BASELINE_TENANT = "synth-acme-services"


def _baseline():
    return json.loads(
        (ROOT / "client" / "snapshots" / BASELINE_TENANT / "baseline.json").read_text()
    )


def _real_sows(baseline):
    return assembly.assemble_sows(findings_mod.run_findings(baseline))


def test_every_sow_gets_the_three_metrics():
    b = _baseline()
    for m in metrics.metrics_for_all(_real_sows(b), b):
        assert m.ebitda_uplift_pct >= 0.0
        assert m.hours_reclaimed_per_year >= 0.0
        assert m.payback_months >= 0.0


def test_ebitda_base_traces_to_net_income():
    b = _baseline()
    base, src = metrics.ebitda_base(b)
    expected = b["accounting"]["profit_and_loss"]["NetIncome"]
    assert abs(base - expected) < 0.01
    assert "NetIncome" in src


def test_ebitda_uplift_is_impact_over_base():
    b = _baseline()
    base, _ = metrics.ebitda_base(b)
    for m in metrics.metrics_for_all(_real_sows(b), b):
        expected = round(100.0 * m.impact_usd / base, 2)
        assert abs(m.ebitda_uplift_pct - expected) < 0.01


def test_payback_months_inverse_to_impact():
    b = _baseline()
    sows = _real_sows(b)
    ms = {m.sow_id: m for m in metrics.metrics_for_all(sows, b)}
    # bigger impact => shorter payback
    by_impact = sorted(ms.values(), key=lambda m: -m.impact_usd)
    paybacks = [m.payback_months for m in by_impact]
    assert paybacks == sorted(paybacks), "payback should rise as impact falls"


def test_every_metric_is_source_traced_and_confident():
    """The grounded-numbers contract at the metrics layer."""
    b = _baseline()
    for m in metrics.metrics_for_all(_real_sows(b), b):
        rec = m.to_grounded_record()
        assert rec["source"], f"{m.sow_id} metric has no source[]"
        assert rec["confidence"] not in (None, ""), f"{m.sow_id} metric has no confidence"
        # impact + ebitda base + cost assumption all named
        assert any("NetIncome" in s for s in rec["source"])
        assert any("engagement_cost" in s for s in rec["source"])


def test_metrics_artifact_passes_grounded_numbers_probe(tmp_path):
    """Write the metrics.jsonl artifact and run the real grounded_numbers probe
    over it — verification, not assertion."""
    import subprocess
    b = _baseline()
    out_dir = tmp_path / "sow"
    metrics.metrics_for_all(_real_sows(b), b, artifacts_dir=out_dir)
    artifact = out_dir / "metrics.jsonl"
    assert artifact.exists()
    r = subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "probes" / "grounded_numbers.py"), str(artifact)],
        capture_output=True, text=True,
    )
    assert r.returncode == 0, f"grounded_numbers probe failed on metrics: {r.stdout}\n{r.stderr}"


def test_attach_metrics_embeds_block():
    b = _baseline()
    sows = _real_sows(b)
    enriched = metrics.attach_metrics(sows, b)
    assert len(enriched) == len(sows)
    for d in enriched:
        assert "metrics" in d
        assert "ebitda_uplift_pct" in d["metrics"]
        assert "payback_months" in d["metrics"]
