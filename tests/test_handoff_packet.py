"""Tests for the FDE handoff packet export (P4.T3).

Covers `presentation/handoff/packet.py`. Builds REAL SOW candidates from the
synthetic tenant baseline -> side-by-side -> selected-SOW packet, and verifies
the packet exports as JSON + markdown with every number source-traced.
"""
import importlib
import importlib.util
import json
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
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


sbs_mod = _load("nsos_sbs_ho", "presentation/side-by-side/sbs.py")
packet_mod = _load("nsos_packet", "presentation/handoff/packet.py")


def _baseline():
    return json.loads(
        (ROOT / "client" / "snapshots" / BASELINE_TENANT / "baseline.json").read_text()
    )


def _firm():
    return json.loads((ROOT / "examples" / "synthetic-client-a" / "firm.json").read_text())


def _sbs_dict():
    b = _baseline()
    sbs = sbs_mod.build_side_by_side(assembly.assemble_sows(findings_mod.run_findings(b)), b)
    return sbs.to_dict()


def test_packet_defaults_to_recommendation():
    sbs = _sbs_dict()
    p = packet_mod.build_packet(
        run_id="r1", tenant_id="t1", firm=_firm(), side_by_side=sbs
    )
    assert p.selected_sow_id == sbs["recommended_sow_id"]


def test_packet_honors_explicit_selection():
    sbs = _sbs_dict()
    target = sbs["columns"][-1]["sow_id"]  # not necessarily the recommendation
    p = packet_mod.build_packet(
        run_id="r1", tenant_id="t1", firm=_firm(),
        side_by_side=sbs, selected_sow_id=target,
    )
    assert p.selected_sow_id == target


def test_unknown_selection_raises():
    sbs = _sbs_dict()
    try:
        packet_mod.build_packet(
            run_id="r1", tenant_id="t1", firm=_firm(),
            side_by_side=sbs, selected_sow_id="sow-does-not-exist",
        )
    except ValueError:
        return
    assert False, "expected ValueError for unknown sow_id"


def test_packet_carries_quantified_target_and_source():
    sbs = _sbs_dict()
    p = packet_mod.build_packet(run_id="r1", tenant_id="t1", firm=_firm(), side_by_side=sbs)
    assert p.impact_usd > 0
    assert p.ebitda_uplift_pct >= 0
    assert p.source, "packet must carry the SOW's source trace"
    # success metrics mirror the quantified target the flywheel will measure
    assert p.success_metrics["impact_usd"] == p.impact_usd
    assert "confidence" in p.success_metrics


def test_validation_checklist_is_gaps_plus_blockers():
    sbs = _sbs_dict()
    col = next(c for c in sbs["columns"] if c["sow_id"] == sbs["recommended_sow_id"])
    p = packet_mod.build_packet(run_id="r1", tenant_id="t1", firm=_firm(), side_by_side=sbs)
    for b in col.get("blockers", []):
        assert b in p.validation_checklist
    for g in col.get("gaps", []):
        assert g in p.validation_checklist


def test_markdown_brief_renders_scope_and_target():
    sbs = _sbs_dict()
    p = packet_mod.build_packet(run_id="r1", tenant_id="t1", firm=_firm(), side_by_side=sbs)
    md = packet_mod.render_markdown(p)
    assert p.title in md
    assert "Quantified target" in md
    assert "Validation checklist" in md
    assert "Evidence trace" in md


def test_export_writes_json_and_markdown(tmp_path):
    sbs = _sbs_dict()
    p = packet_mod.build_packet(run_id="r1", tenant_id="t1", firm=_firm(), side_by_side=sbs)
    json_path, md_path = packet_mod.export_packet(p, tmp_path / "handoff")
    assert json_path.exists() and md_path.exists()
    data = json.loads(json_path.read_text())
    assert data["selected_sow_id"] == p.selected_sow_id
    assert data["source"]


def test_from_run_exports_under_run_dir():
    # the synthetic run has side-by-side.json committed (written in P4.T1)
    p = packet_mod.from_run("synthetic-client-a")
    artifact = ROOT / "runs" / "synthetic-client-a" / "handoff" / "fde-handoff-packet.json"
    assert artifact.exists()
    data = json.loads(artifact.read_text())
    assert data["run_id"] == "synthetic-client-a"
    assert data["impact_usd"] > 0
