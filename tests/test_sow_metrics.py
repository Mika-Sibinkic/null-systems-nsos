"""Tests for quantified SOW success metrics (P3.T4)."""
import json
import sys
from pathlib import Path

import engine.sow.metrics as metrics
import engine.sow.assembly as assembly
import engine.meta_levels.financial.findings as findings_mod

ROOT = Path(__file__).resolve().parents[1]


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
        assert m.payback_months is None or m.payback_months >= 0.0  # None = no $ impact


def test_ebitda_base_traces_to_net_income():
    b = _baseline()
    base, src, label = metrics.ebitda_base(b)
    expected = b["accounting"]["profit_and_loss"]["NetIncome"]
    assert abs(base - expected) < 0.01
    assert "NetIncome" in src
    assert label == "net income"


def test_ebitda_uplift_is_impact_over_base():
    b = _baseline()
    base, _, _ = metrics.ebitda_base(b)
    for m in metrics.metrics_for_all(_real_sows(b), b):
        expected = round(100.0 * m.impact_usd / base, 2)
        assert abs(m.ebitda_uplift_pct - expected) < 0.01


def test_payback_months_inverse_to_impact():
    b = _baseline()
    sows = _real_sows(b)
    ms = {m.sow_id: m for m in metrics.metrics_for_all(sows, b)}
    # bigger impact => shorter payback
    by_impact = sorted((m for m in ms.values() if m.impact_usd > 0), key=lambda m: -m.impact_usd)
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


def test_grounded_numbers_probe_rejects_ungrounded_exposure(tmp_path):
    """Exposure is a dollar the owner reads, so the probe holds it to the same rule
    as impact (assert_grounded in findings.py already does)."""
    import subprocess
    artifact = tmp_path / "findings.jsonl"
    artifact.write_text(json.dumps({"id": "x", "exposure_usd": 8400000}) + "\n")
    r = subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "probes" / "grounded_numbers.py"), str(artifact)],
        capture_output=True, text=True,
    )
    assert r.returncode == 1, r.stdout


def test_attach_metrics_embeds_block():
    b = _baseline()
    sows = _real_sows(b)
    enriched = metrics.attach_metrics(sows, b)
    assert len(enriched) == len(sows)
    for d in enriched:
        assert "metrics" in d
        assert "ebitda_uplift_pct" in d["metrics"]
        assert "payback_months" in d["metrics"]


# ── undefined metrics are None, never Infinity ────────────────────────────────

def _strict_loads(text):
    def _reject(c):
        raise ValueError(f"non-JSON constant {c}")
    return json.loads(text, parse_constant=_reject)


def test_loss_firm_has_no_ebitda_uplift():
    loss = {"accounting": {"profit_and_loss": {"NetIncome": -200000}}}
    m = metrics.metrics_for({"id": "s", "impact_usd": 50000, "confidence": 0.7}, loss)
    assert m.ebitda_uplift_pct is None


def test_hours_only_sow_serializes_without_infinity(tmp_path):
    sow = {"id": "hours-only", "impact_usd": 0, "impact_hours": 40, "confidence": 0.7, "source": ["x=1"]}
    m = metrics.metrics_for(sow, _baseline())
    assert m.payback_months is None
    metrics.metrics_for_all([sow], _baseline(), artifacts_dir=tmp_path)
    rec = _strict_loads((tmp_path / "metrics.jsonl").read_text())
    assert rec["payback_months"] is None


def test_payback_and_ebitda_formatting():
    assert metrics.fmt_payback(0.26) == "<1 month"
    assert metrics.fmt_payback(1.14) == "1 month"
    assert metrics.fmt_payback(3.32) == "3 months"
    assert metrics.fmt_payback(None) == "—"
    assert metrics.fmt_ebitda(61.56, "net income") == "+62% of net income"
    assert metrics.fmt_ebitda(None, "net income") == "— (EBITDA base not positive)"
