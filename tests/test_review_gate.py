"""Tests for the financial review_gate (P2.T4) + quality_judge offline mode."""
import importlib
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

# Enable offline-deterministic judge for the whole module so the gate is testable
# without a live LLM key (the build pipeline sets this env too).
os.environ["NSOS_JUDGE_OFFLINE_DETERMINISTIC"] = "1"

review_gate = importlib.import_module("engine.meta-levels.financial.review_gate")
findings_mod = importlib.import_module("engine.meta-levels.financial.findings")

BASELINE = json.loads(
    (ROOT / "client" / "snapshots" / "synth-acme-services" / "baseline.json").read_text()
)


def test_high_confidence_grounded_finding_auto_clears():
    f = {
        "id": "hi-1",
        "headline": "Subcontractor Group is 67% of vendor spend — concentration risk",
        "evidence": ["accounting.expenses_by_vendor[Subcontractor Group]=8400000"],
        "source": ["accounting.expenses_by_vendor[Subcontractor Group]=8400000"],
        "impact_usd": 8400000,
        "confidence": 0.8,
    }
    d = review_gate.review_finding(f)
    assert d["auto_cleared"] is True
    assert d["queued_for_review"] is False


def test_low_confidence_finding_queued_for_review():
    f = {
        "id": "lo-1",
        "headline": "Possible savings somewhere",
        "evidence": ["accounting hint"],
        "impact_usd": 1000,
        "confidence": 0.4,  # below CONF_FLOOR
    }
    d = review_gate.review_finding(f)
    assert d["queued_for_review"] is True
    assert any("confidence" in r for r in d["reasons"])


def test_review_findings_writes_queue(tmp_path):
    findings = findings_mod.run_findings(BASELINE)
    # force one low-confidence finding into the set
    findings.append({"id": "lo-x", "headline": "weak", "evidence": ["x"], "impact_usd": 500, "confidence": 0.3})
    out = review_gate.review_findings(findings, run_id="t", runs_root=tmp_path)
    assert out["total"] == len(findings)
    assert out["queued"] >= 1
    qp = Path(out["queue_path"])
    assert qp.exists()
    queued = [json.loads(l) for l in qp.read_text().splitlines() if l.strip()]
    assert all(d["queued_for_review"] for d in queued)


def test_real_findings_mostly_clear():
    findings = findings_mod.run_findings(BASELINE)
    out = review_gate.review_findings(findings)
    # the financial engine's real findings are grounded; most should auto-clear
    assert out["auto_cleared"] >= 1
    assert out["total"] == len(findings)


def test_quality_judge_offline_deterministic_scores():
    sys.path.insert(0, str(ROOT / "engine" / "gauntlets"))
    qj = importlib.import_module("quality_judge")
    importlib.reload(qj)  # pick up the env var
    s = qj.score(
        "Switching primary cloud supplier saves $42,000/year. Evidence: QuickBooks $84k/yr to Provider X. "
        "Recommend re-platform. Confidence: HIGH."
    )
    assert s["status"] == "ok"
    assert s["confidence"] is not None
    assert not qj.gate_decision(s)  # strong grounded output should NOT gate
