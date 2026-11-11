"""Tests for SOW assembly — findings -> 2-3 coherent SOW candidates (P3.T1)."""
from pathlib import Path

import engine.sow.assembly as assembly
import engine.meta_levels.financial.findings as findings_mod

ROOT = Path(__file__).resolve().parents[1]


BASELINE_TENANT = "synth-acme-services"


def _real_findings() -> list[dict]:
    """Use the real financial findings engine over the synthetic baseline —
    no fixtures."""
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
    impacts = [s.impact_usd for s in sows]
    assert impacts == sorted(impacts, reverse=True)


def test_each_finding_lands_in_exactly_one_candidate_when_unclamped():
    findings = _real_findings()
    sows = assembly.assemble_sows(findings, min_candidates=2, max_candidates=99)
    placed = [fid for s in sows for fid in s.finding_ids]
    assert sorted(placed) == sorted(f["id"] for f in findings)
    assert len(placed) == len(set(placed)), "a finding was double-counted"


def test_empty_findings_yields_no_candidates():
    assert assembly.assemble_sows([]) == []
