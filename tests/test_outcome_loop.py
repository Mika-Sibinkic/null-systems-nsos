"""Tests for the outcome flywheel — predicted vs realized (P5.T1)."""
import importlib
import importlib.util
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

assembly = importlib.import_module("engine.sow.assembly")
findings_mod = importlib.import_module("engine.meta-levels.financial.findings")


def _load(name: str, rel: str):
    spec = importlib.util.spec_from_file_location(name, str(ROOT / rel))
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


ol = _load("nsos_outcome_loop", "learning/feedback/outcome_loop.py")
sbs_mod = _load("nsos_sbs_ol", "presentation/side-by-side/sbs.py")
packet_mod = _load("nsos_packet_ol", "presentation/handoff/packet.py")


def _baseline():
    return json.loads(
        (ROOT / "client" / "snapshots" / "synth-acme-services" / "baseline.json").read_text()
    )


def _firm():
    return json.loads((ROOT / "examples" / "synthetic-client-a" / "firm.json").read_text())


def _real_packet():
    b = _baseline()
    sbs = sbs_mod.build_side_by_side(assembly.assemble_sows(findings_mod.run_findings(b)), b).to_dict()
    return packet_mod.build_packet(run_id="r-test", tenant_id="t-test", firm=_firm(), side_by_side=sbs)


def test_schema_is_valid_json():
    schema = json.loads((ROOT / "learning" / "feedback" / "schema.json").read_text())
    assert schema["title"] == "Outcome Flywheel Record"
    assert "prediction" in schema["properties"]["record_type"]["enum"]
    assert "realization" in schema["properties"]["record_type"]["enum"]


def test_prediction_row_lifts_from_handoff_packet(tmp_path):
    led = tmp_path / "ledger.jsonl"
    p = _real_packet()
    row = ol.record_prediction(p, ledger=led, ts="2026-06-07T00:00:00Z")
    assert row["record_type"] == "prediction"
    assert row["sow_id"] == p.selected_sow_id
    assert row["predicted"]["impact_usd"] == p.impact_usd
    assert row["source"], "prediction must carry the packet's source trace"


def test_ledger_is_append_only(tmp_path):
    led = tmp_path / "ledger.jsonl"
    p = _real_packet()
    ol.record_prediction(p, ledger=led, ts="2026-06-07T00:00:00Z")
    ol.record_realization(
        run_id="r-test", sow_id=p.selected_sow_id, tenant_id="t-test",
        impact_usd=p.impact_usd * 0.9, source=["actuals"], ledger=led, ts="2026-06-08T00:00:00Z",
    )
    rows = ol.load_ledger(led)
    assert len(rows) == 2
    assert [r["record_type"] for r in rows] == ["prediction", "realization"]


def test_pair_outcomes_computes_delta_and_ratio(tmp_path):
    led = tmp_path / "ledger.jsonl"
    ol.record_prediction(
        {"run_id": "r1", "selected_sow_id": "sow-a", "tenant_id": "t1",
         "impact_usd": 1_000_000, "ebitda_uplift_pct": 30, "payback_months": 6,
         "confidence": 0.8, "source": ["p&l"]},
        ledger=led, ts="2026-06-07T00:00:00Z",
    )
    ol.record_realization(
        run_id="r1", sow_id="sow-a", tenant_id="t1",
        impact_usd=800_000, ebitda_uplift_pct=24, source=["actuals"],
        ledger=led, ts="2026-06-08T00:00:00Z",
    )
    deltas = ol.pair_outcomes(led)
    assert len(deltas) == 1
    d = deltas[0]
    assert d.delta_usd == -200_000.0
    assert d.accuracy_ratio == 0.8


def test_open_predictions_are_not_paired(tmp_path):
    led = tmp_path / "ledger.jsonl"
    ol.record_prediction(
        {"run_id": "r2", "selected_sow_id": "sow-b", "tenant_id": "t1",
         "impact_usd": 500_000, "source": ["x"]},
        ledger=led, ts="2026-06-07T00:00:00Z",
    )
    assert ol.pair_outcomes(led) == []
    summary = ol.calibration_summary(led)
    assert summary["paired"] == 0
    assert summary["open_predictions"] == 1


def test_export_evalset_writes_paired_deltas(tmp_path):
    led = tmp_path / "ledger.jsonl"
    evalset = tmp_path / "evalset.jsonl"
    ol.record_prediction(
        {"run_id": "r3", "selected_sow_id": "sow-c", "tenant_id": "t1",
         "impact_usd": 2_000_000, "source": ["p&l"]},
        ledger=led, ts="2026-06-07T00:00:00Z",
    )
    ol.record_realization(
        run_id="r3", sow_id="sow-c", tenant_id="t1",
        impact_usd=2_200_000, source=["actuals"], ledger=led, ts="2026-06-08T00:00:00Z",
    )
    out = ol.export_evalset(ledger=led, evalset=evalset)
    assert out.exists()
    rows = [json.loads(l) for l in out.read_text().splitlines() if l.strip()]
    assert len(rows) == 1
    # realized > predicted, but ratio clamps at 2.0 max (here 1.1)
    assert rows[0]["accuracy_ratio"] == 1.1


def test_accuracy_ratio_clamped(tmp_path):
    led = tmp_path / "ledger.jsonl"
    ol.record_prediction(
        {"run_id": "r4", "selected_sow_id": "sow-d", "tenant_id": "t1",
         "impact_usd": 100_000, "source": ["p&l"]},
        ledger=led, ts="2026-06-07T00:00:00Z",
    )
    # realized 5x predicted -> ratio clamps to 2.0 (a 5x beat is suspect, not real signal)
    ol.record_realization(
        run_id="r4", sow_id="sow-d", tenant_id="t1",
        impact_usd=500_000, source=["actuals"], ledger=led, ts="2026-06-08T00:00:00Z",
    )
    assert ol.pair_outcomes(led)[0].accuracy_ratio == 2.0
