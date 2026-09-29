"""End-to-end real pipe on synthetic-client-a (P5.T3).

Runs the WHOLE diagnostic — not fixtures — from the QuickBooks export through to
the web-renderable SOW comparison + FDE packet, and verifies the money flow with
the real grounded_numbers + quality_judge probes:

  onboarding (scoped token, secrets server-side)
    -> QuickBooks adapter -> baseline.json (schema-valid)
      -> financial meta-team -> grounded findings
        -> council (recursive-weight rank + debate)
          -> SOW assembly -> 2-3 candidates
            -> WWMD + pillar grade + metrics -> side-by-side
              -> CEO decision report (quality_judge-gated)
                -> FDE handoff packet
                  -> outcome flywheel prediction row

Artifacts land under runs/synthetic-client-a/ so the run is inspectable. This is
the MVP slice's acceptance test: real data in, scored choices + packet out.
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

qb = importlib.import_module("client.adapters.quickbooks")
onboarding = importlib.import_module("client.onboarding.onboarding")
findings_mod = importlib.import_module("engine.meta-levels.financial.findings")
council_mod = importlib.import_module("engine.council.council")
assembly = importlib.import_module("engine.sow.assembly")

EXPORT = ROOT / "examples" / "synthetic-client-a" / "quickbooks_export.json"
FIRM = ROOT / "examples" / "synthetic-client-a" / "firm.json"
RUN_ID = "synthetic-client-a"
RUN_DIR = ROOT / "runs" / RUN_ID


def _load(name: str, rel: str):
    spec = importlib.util.spec_from_file_location(name, str(ROOT / rel))
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


sbs_mod = _load("nsos_sbs_e2e", "presentation/side-by-side/sbs.py")
report_mod = _load("nsos_report_e2e", "presentation/exec-report/report_generator.py")
packet_mod = _load("nsos_packet_e2e", "presentation/handoff/packet.py")
ol = _load("nsos_ol_e2e", "learning/feedback/outcome_loop.py")


def _run_full_pipe(tmp_path):
    """Execute the real chain; return the assembled artifacts dict."""
    export = json.loads(EXPORT.read_text())
    firm = json.loads(FIRM.read_text())
    tenant_id = "synth-acme-services"

    # 1. onboarding -> baseline (scoped token returned, secret stays server-side)
    snapshots_root = tmp_path / "snapshots"
    secret_store = onboarding.ConnectorSecretStore()
    baseline_path, web_token = onboarding.onboard_quickbooks(
        tenant_id, "qb-oauth-secret-xyz", export,
        firm=firm, secret_store=secret_store, snapshots_root=snapshots_root,
    )
    assert web_token, "onboarding must mint a scoped web token"
    baseline = json.loads(Path(baseline_path).read_text())
    assert qb.validate_baseline(baseline) == [], "baseline must be schema-valid"

    # 2. financial meta-team -> grounded findings (assert_grounded fail-closed inside)
    findings = findings_mod.run_findings(baseline)
    assert findings, "financial team produced no findings from real data"

    # 3. council rank
    ceo_priorities = [
        {"text": p["text"], "embedding": [0.6, 0.4, 0.1, 0.2], "weight": p["weight"]}
        for p in firm.get("stated_objectives", [])
    ]
    known_baseline = [
        {"text": k["text"], "embedding": [0.2, 0.1, 0.8, 0.1]}
        for k in firm.get("known_baseline", [])
    ]
    ranked = council_mod.run_council(findings, ceo_priorities, known_baseline)
    council_scores = {r.finding_id: r.final for r in ranked}

    # 4. SOW assembly -> 2-3 candidates, written under the run dir
    sow_dir = RUN_DIR / "sow"
    sows = assembly.assemble_sows(findings, council_scores=council_scores, artifacts_dir=sow_dir)
    assert 2 <= len(sows) <= 3

    # 5. side-by-side (WWMD + pillar grade + metrics) -> web-renderable artifact
    sbs = sbs_mod.build_side_by_side(sows, baseline)
    sbs_mod.write_artifact(sbs, RUN_DIR / "presentation" / "side-by-side.json")

    # 6. CEO decision report
    report = report_mod.render_sow_report(
        firm, sows, baseline, output_path=RUN_DIR / "presentation" / "report.md"
    )

    # 7. FDE handoff packet for the recommended SOW
    packet = packet_mod.build_packet(
        run_id=RUN_ID, tenant_id=tenant_id, firm=firm,
        side_by_side=sbs.to_dict(),
    )
    packet_mod.export_packet(packet, RUN_DIR / "handoff")

    # 8. outcome flywheel prediction row (the moat's first datapoint)
    ledger = RUN_DIR / "flywheel" / "outcome-ledger.jsonl"
    if ledger.exists():
        ledger.unlink()  # idempotent test artifact
    ol.record_prediction(packet, ledger=ledger, ts="2026-06-07T00:00:00Z")

    return {
        "baseline": baseline,
        "findings": findings,
        "ranked": ranked,
        "sows": sows,
        "sbs": sbs,
        "report": report,
        "packet": packet,
        "ledger": ledger,
    }


def test_e2e_pipe_produces_scored_sows(tmp_path):
    art = _run_full_pipe(tmp_path)
    sbs = art["sbs"]
    # every SOW is scored on all three layers, real not fixture
    for c in sbs.columns:
        assert c.impact_usd > 0
        assert c.grade in ("A", "B", "C", "D", "F")
        assert 0.0 <= c.wwmd_score <= 1.0
        assert c.source
    assert sbs.recommended_sow_id in {c.sow_id for c in sbs.columns}


def test_e2e_findings_trace_to_real_accounting(tmp_path):
    art = _run_full_pipe(tmp_path)
    # findings descend from the real QB-derived accounting view, with source[]
    for f in art["findings"]:
        assert f.get("impact_usd", 0) >= 0
        assert f.get("source") or f.get("evidence"), f"{f['id']} ungrounded"


def test_e2e_run_artifacts_written():
    # artifacts from the pipe are inspectable on disk under runs/
    assert (RUN_DIR / "sow" / "sow-candidates.jsonl").exists()
    assert (RUN_DIR / "presentation" / "side-by-side.json").exists()
    assert (RUN_DIR / "presentation" / "report.md").exists()
    assert (RUN_DIR / "handoff" / "fde-handoff-packet.json").exists()


def test_e2e_metrics_artifact_passes_grounded_numbers_probe(tmp_path):
    """Run the REAL grounded_numbers probe over the run's SOW metrics — verification."""
    art = _run_full_pipe(tmp_path)
    # write the metrics artifact for the run's SOWs
    metrics = importlib.import_module("engine.sow.metrics")
    metrics.metrics_for_all(art["sows"], art["baseline"], artifacts_dir=RUN_DIR / "sow")
    artifact = RUN_DIR / "sow" / "metrics.jsonl"
    r = subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "probes" / "grounded_numbers.py"), str(artifact)],
        capture_output=True, text=True,
    )
    assert r.returncode == 0, f"grounded_numbers failed on e2e metrics: {r.stdout}\n{r.stderr}"


def test_e2e_report_passes_quality_judge_gate(tmp_path):
    """Run the REAL quality_judge gate over the e2e decision report."""
    art = _run_full_pipe(tmp_path)
    env = dict(os.environ, NSOS_JUDGE_OFFLINE_DETERMINISTIC="1")
    r = subprocess.run(
        [sys.executable, str(ROOT / "engine" / "gauntlets" / "quality_judge.py"),
         "--gate", "--text", art["report"][:3000]],
        capture_output=True, text=True, env=env,
    )
    assert r.returncode == 0, f"quality_judge gated the e2e report: {r.stdout}\n{r.stderr}"


def test_e2e_flywheel_prediction_recorded(tmp_path):
    art = _run_full_pipe(tmp_path)
    rows = ol.load_ledger(art["ledger"])
    assert len(rows) == 1
    assert rows[0]["record_type"] == "prediction"
    assert rows[0]["run_id"] == RUN_ID
    assert rows[0]["predicted"]["impact_usd"] > 0
