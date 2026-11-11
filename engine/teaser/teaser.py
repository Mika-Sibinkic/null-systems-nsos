"""Teaser: one quick finding from baseline.json, for the web onboarding demo.

No LLM call, pure arithmetic over the snapshot, so it returns in milliseconds.
It is the full engine's own `findings.ANALYTICS["scope_cycle_time"]` with the
same confidence, so the number on the web page is the number in the report.
Deterministic and offline.
"""
from __future__ import annotations
import json
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Any, Optional

import engine.meta_levels.financial.findings as _findings


@dataclass
class TeaserResult:
    id: str
    headline: str
    impact_usd: float
    impact_hours: float
    evidence: list[str]
    confidence: float
    method: str

    def to_finding(self) -> dict[str, Any]:
        d = asdict(self)
        d["team"] = "teaser"
        return d


def _scope_cycle_leak(baseline: dict[str, Any]) -> Optional[TeaserResult]:
    a = _findings.ANALYTICS["scope_cycle_time"](baseline)
    if not a or a["impact_usd"] <= 0:
        return None
    return TeaserResult(
        id="teaser-cycle-001",
        headline=(f"Proposal scoping runs ~{a['avg_days']:.0f} days vs a {a['target_days']:.0f}-day "
                  f"target — ~${a['impact_usd']:,.0f}{a['per']} of partner time"),
        impact_usd=a["impact_usd"],
        impact_hours=a["leaked_hours"],
        evidence=a["source"],
        confidence=_findings.CONFIDENCE_BY_METHOD["scope_cycle_time"],
        method="scope_cycle_time_leak",
    )


def teaser_finding(baseline: dict[str, Any]) -> TeaserResult:
    """Return the teaser finding for a baseline snapshot.

    Raises ValueError if the baseline has no accounting view to read.
    """
    acct = baseline.get("accounting")
    if not acct:
        raise ValueError("baseline has no accounting view — cannot produce a teaser")
    leak = _scope_cycle_leak(baseline)
    if leak is None:
        # Always return SOMETHING grounded rather than failing silently.
        revenue = (baseline.get("firm", {}) or {}).get("annual_revenue_usd", 0)
        return TeaserResult(
            id="teaser-fallback-001",
            headline="No quick finding in this export. The full run reads the rest.",
            impact_usd=0.0,
            impact_hours=0.0,
            evidence=[f"Baseline accepted; annual revenue context ${revenue:,.0f}" if revenue else "Baseline accepted"],
            confidence=0.5,
            method="no_cheap_signal_found",
        )
    return leak


def from_snapshot(tenant_id: str, *, snapshots_root: Optional[Path] = None) -> TeaserResult:
    """Convenience: load a tenant's baseline.json and produce its teaser."""
    root = snapshots_root or (Path(__file__).resolve().parents[2] / "client" / "snapshots")
    baseline = json.loads((root / tenant_id / "baseline.json").read_text())
    return teaser_finding(baseline)
