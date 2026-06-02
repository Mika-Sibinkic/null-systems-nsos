"""<1h teaser signal path.

Produces ONE cheap, high-signal finding from baseline.json with no LLM call and no
full gauntlet — pure arithmetic over the snapshot — so it returns in seconds (well
inside the <1h budget) and hooks the operator while the full 24-72h diagnostic runs
async. The number it surfaces is fully source-traced + confidence-banded (LeCun
grounding) so it survives the same grounded_numbers gate the real findings do.

Strategy: scan the accounting view for the single biggest, most-defensible dollar
signal among a few cheap heuristics, return the strongest:
  - vendor concentration vs a benchmark cut (cloud/infra overspend)
  - proposal/scope cycle-time leak (first_contact -> scope_sent) priced at a blended rate
Whichever yields the larger grounded impact_usd wins. Deterministic + offline.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, asdict
from datetime import date
from pathlib import Path
from typing import Any, Optional

# Conservative assumptions, declared so the confidence band is honest.
BLENDED_PARTNER_RATE_USD_PER_HR = 250.0  # mid-market professional-services blended rate [LIKELY]
HOURS_PER_SCOPE_DELAY_DAY = 0.5          # partner hours leaked per excess day of scoping [LIKELY]
CLOUD_BENCHMARK_SAVINGS_PCT = 0.40       # observed commodity-cloud re-platform saving [LIKELY]


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


def _cloud_overspend(acct: dict[str, Any]) -> Optional[TeaserResult]:
    vendors = acct.get("expenses_by_vendor", []) or []
    cloud = [v for v in vendors if "cloud" in (v.get("category", "") + v.get("vendor", "")).lower()]
    if not cloud:
        return None
    top = max(cloud, key=lambda v: v.get("amount_usd", 0))
    spend = float(top.get("amount_usd", 0))
    if spend <= 0:
        return None
    saving = round(spend * CLOUD_BENCHMARK_SAVINGS_PCT)
    return TeaserResult(
        id="teaser-cloud-001",
        headline=f"Cloud spend with {top['vendor']} looks ~${saving:,.0f}/yr re-platformable",
        impact_usd=float(saving),
        impact_hours=0.0,
        evidence=[
            f"QuickBooks: ${spend:,.0f}/yr to {top['vendor']} ({top.get('txn_count', 0)} txns), category {top.get('category','')}",
            f"Benchmark commodity-cloud re-platform saving ~{int(CLOUD_BENCHMARK_SAVINGS_PCT*100)}% [LIKELY]",
        ],
        confidence=0.6,
        method="vendor_concentration_vs_benchmark",
    )


def _scope_cycle_leak(acct: dict[str, Any]) -> Optional[TeaserResult]:
    invoices = acct.get("invoices", []) or []
    delays_days = []
    for inv in invoices:
        fc, ss = inv.get("first_contact_at"), inv.get("scope_sent_at")
        if not fc or not ss:
            continue
        try:
            d = (date.fromisoformat(ss) - date.fromisoformat(fc)).days
        except ValueError:
            continue
        if d > 0:
            delays_days.append(d)
    if not delays_days:
        return None
    n = len(delays_days)
    avg = sum(delays_days) / n
    # Target a 5-day turnaround (PRODUCT objective); price the excess at partner time.
    excess = max(0.0, avg - 5.0)
    # Annualize: observed invoices are a sample; scale leaked hours by the count seen.
    leaked_hours = excess * HOURS_PER_SCOPE_DELAY_DAY * n
    impact = round(leaked_hours * BLENDED_PARTNER_RATE_USD_PER_HR)
    if impact <= 0:
        return None
    return TeaserResult(
        id="teaser-cycle-001",
        headline=f"Proposal scoping runs ~{avg:.0f} days vs a 5-day target — ~${impact:,.0f}/yr of partner time",
        impact_usd=float(impact),
        impact_hours=round(leaked_hours, 1),
        evidence=[
            f"QuickBooks: {n} invoices show avg {avg:.1f} days from first contact to scope sent",
            f"Excess over 5-day target priced at {HOURS_PER_SCOPE_DELAY_DAY} partner-hr/day @ ${BLENDED_PARTNER_RATE_USD_PER_HR:,.0f}/hr [LIKELY]",
        ],
        confidence=0.7,
        method="scope_cycle_time_leak",
    )


def teaser_finding(baseline: dict[str, Any]) -> TeaserResult:
    """Return the single strongest cheap finding from a baseline snapshot.

    Raises ValueError if the baseline has no accounting view to read.
    """
    acct = baseline.get("accounting")
    if not acct:
        raise ValueError("baseline has no accounting view — cannot produce a teaser")
    candidates = [c for c in (_scope_cycle_leak(acct), _cloud_overspend(acct)) if c]
    if not candidates:
        # Always return SOMETHING grounded rather than failing silently.
        revenue = (baseline.get("firm", {}) or {}).get("annual_revenue_usd", 0)
        return TeaserResult(
            id="teaser-fallback-001",
            headline="Connected. Full diagnostic running — first quantified findings within the run window.",
            impact_usd=0.0,
            impact_hours=0.0,
            evidence=[f"Baseline accepted; annual revenue context ${revenue:,.0f}" if revenue else "Baseline accepted"],
            confidence=0.5,
            method="no_cheap_signal_found",
        )
    return max(candidates, key=lambda c: c.impact_usd)


def from_snapshot(tenant_id: str, *, snapshots_root: Optional[Path] = None) -> TeaserResult:
    """Convenience: load a tenant's baseline.json and produce its teaser."""
    root = snapshots_root or (Path(__file__).resolve().parents[2] / "client" / "snapshots")
    baseline = json.loads((root / tenant_id / "baseline.json").read_text())
    return teaser_finding(baseline)


def _main() -> int:
    import argparse
    p = argparse.ArgumentParser(description="<1h teaser from a tenant baseline")
    p.add_argument("--tenant", required=True)
    args = p.parse_args()
    res = from_snapshot(args.tenant)
    print(json.dumps(res.to_finding(), indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(_main())
