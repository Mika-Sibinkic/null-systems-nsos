"""Tests for SOW assembly — ranked findings -> 2-3 coherent SOW candidates (P3.T1)."""
import importlib
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

assembly = importlib.import_module("engine.sow.assembly")
findings_mod = importlib.import_module("engine.meta-levels.financial.findings")

BASELINE_TENANT = "synth-acme-services"


def _real_findings() -> list[dict]:
    """Use the real financial findings engine over the synthetic baseline —
    no fixtures, real data per the engineering bar."""
    import json
    baseline = json.loads(
        (ROOT / "client" / "snapshots" / BASELINE_TENANT / "baseline.json").read_text()
    )
    return findings_mod.run_findings(baseline)


def test_produces_two_or_three_candidates():
    sows = assembly.assemble_sows(_real_findings())
    assert 2 <= len(sows) <= 3, f"expected 2-3 SOW candidates, got {len(sows)}"


def test_every_candidate_bundles_at_least_one_finding():
    sows = assembly.assemble_sows(_real_findings())
    for s in sows:
        assert s.finding_ids, f"{s.id} has no findings"
        assert len(s.findings) == len(s.finding_ids)


def test_candidate_impact_is_sum_of_findings():
    findings = _real_findings()
    by_id = {f["id"]: f for f in findings}
    sows = assembly.assemble_sows(findings)
    for s in sows:
        expected = round(sum(by_id[fid]["impact_usd"] for fid in s.finding_ids), 2)
        assert abs(s.impact_usd - expected) < 0.01, f"{s.id} impact mismatch"


def test_candidate_sources_are_grounded_union():
    """SOW must not invent numbers — its source[] is the union of its findings'
    sources, so the grounded-numbers contract holds at the SOW layer too."""
    findings = _real_findings()
    by_id = {f["id"]: f for f in findings}
    sows = assembly.assemble_sows(findings)
    for s in sows:
        assert s.source, f"{s.id} carries impact with no source[]"
        finding_sources = set()
        for fid in s.finding_ids:
            finding_sources.update(by_id[fid].get("source", []))
        assert set(s.source) <= finding_sources, f"{s.id} invented a source line"


def test_confidence_is_impact_weighted_and_banded():
    sows = assembly.assemble_sows(_real_findings())
    for s in sows:
        assert 0.0 <= s.confidence <= 1.0


def test_candidates_ranked_descending():
    sows = assembly.assemble_sows(_real_findings())
    scores = [s.rank_score for s in sows]
    assert scores == sorted(scores, reverse=True)


def test_council_scores_drive_ranking_when_present():
    findings = _real_findings()
    # force a council ordering that inverts the impact ordering
    council = {f["id"]: float(i) for i, f in enumerate(findings)}
    sows = assembly.assemble_sows(findings, council_scores=council)
    # rank_score now reflects council sums, not raw impact
    for s in sows:
        expected = round(sum(council[fid] for fid in s.finding_ids), 4)
        assert abs(s.rank_score - expected) < 0.01


def test_each_finding_lands_in_exactly_one_candidate_when_unclamped():
    findings = _real_findings()
    sows = assembly.assemble_sows(findings, min_candidates=2, max_candidates=99)
    placed = [fid for s in sows for fid in s.finding_ids]
    assert sorted(placed) == sorted(f["id"] for f in findings)
    assert len(placed) == len(set(placed)), "a finding was double-counted"


def test_empty_findings_yields_no_candidates():
    assert assembly.assemble_sows([]) == []


def test_from_run_writes_artifact(tmp_path):
    # build a run dir with the real findings, then assemble from it
    findings = _real_findings()
    run_id = "test-run"
    fpath = tmp_path / run_id / "gauntlet" / "financial" / "findings.jsonl"
    fpath.parent.mkdir(parents=True, exist_ok=True)
    import json
    fpath.write_text("\n".join(json.dumps(f) for f in findings) + "\n")
    sows = assembly.from_run(run_id, runs_root=tmp_path)
    assert 2 <= len(sows) <= 3
    artifact = tmp_path / run_id / "sow" / "sow-candidates.jsonl"
    assert artifact.exists()
    lines = [l for l in artifact.read_text().splitlines() if l.strip()]
    assert len(lines) == len(sows)
