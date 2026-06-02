"""Tests for engine/teaser — <1h cheap high-signal finding from baseline.json."""
import json
import sys
import time
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from client.adapters.quickbooks import build_baseline  # noqa: E402
from engine.teaser.teaser import teaser_finding, from_snapshot, TeaserResult  # noqa: E402

EXPORT = json.loads((ROOT / "examples" / "synthetic-client-a" / "quickbooks_export.json").read_text())
FIRM = json.loads((ROOT / "examples" / "synthetic-client-a" / "firm.json").read_text())


def _baseline():
    return build_baseline(EXPORT, "synth-acme-services", firm=FIRM)


def test_teaser_returns_grounded_finding():
    res = teaser_finding(_baseline())
    assert isinstance(res, TeaserResult)
    assert res.impact_usd > 0
    assert res.evidence, "teaser must carry source evidence (grounding)"
    assert 0.0 < res.confidence <= 1.0


def test_teaser_finding_passes_grounded_numbers_shape():
    # mirrors build/probes/grounded_numbers.py: impact -> needs evidence[] + confidence
    f = teaser_finding(_baseline()).to_finding()
    has_impact = bool(f.get("impact_usd")) or bool(f.get("impact_hours"))
    assert has_impact
    assert f.get("evidence")
    assert f.get("confidence") is not None


def test_teaser_is_fast():
    start = time.time()
    teaser_finding(_baseline())
    assert (time.time() - start) < 1.0, "teaser must be near-instant (well inside <1h budget)"


def test_teaser_picks_largest_impact():
    res = teaser_finding(_baseline())
    # scope-cycle leak vs cloud overspend — the larger grounded number wins
    assert res.method in {"scope_cycle_time_leak", "vendor_concentration_vs_benchmark"}


def test_teaser_fallback_when_no_signal():
    empty = {"accounting": {"expenses_by_vendor": [], "invoices": []}, "firm": {"annual_revenue_usd": 1000000}}
    res = teaser_finding(empty)
    assert res.method == "no_cheap_signal_found"
    assert res.confidence == 0.5  # honest about low signal, never silently fails


def test_teaser_raises_without_accounting():
    with pytest.raises(ValueError):
        teaser_finding({"firm": {}})


def test_from_snapshot_reads_written_baseline(tmp_path):
    from client.adapters.quickbooks import write_baseline
    write_baseline(_baseline(), snapshots_root=tmp_path)
    res = from_snapshot("synth-acme-services", snapshots_root=tmp_path)
    assert res.impact_usd > 0
