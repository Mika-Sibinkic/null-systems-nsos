"""Data -> findings engine for the financial meta-team.

Turns a tenant `baseline.json` (QuickBooks-derived) into client-facing findings,
each carrying a quantified, **source-traced, confidence-banded** impact so it
survives the same gates the rest of the pipeline enforces:

  - `impact_usd` / `impact_hours` — the dollars/time the finding moves
  - `bottleneck`   — the one-line "what is actually constraining the business"
  - `evidence[]`   — every number traces to a baseline line (LeCun grounding;
                     `build/probes/grounded_numbers.py` enforces this)
  - `confidence`   — honest band reflecting how defensible the number is
  - `source[]`     — machine-checkable refs into the baseline (accounting.<path>)

Pure arithmetic over the snapshot. No LLM, deterministic, offline — so the
financial findings are reproducible and the grounded-numbers gate is meaningful.

The same analytic functions back `team.py`'s question battery (one implementation,
two consumers): each `ANALYTICS[method]` returns a normalized analytic dict, and
`finding_from_analytic` lifts it into a finding record. `run_findings` is the
end-to-end entry the integrator/E2E test call.
"""
from __future__ import annotations

import json
from datetime import date
from pathlib import Path
from typing import Any, Callable, Optional

# ── declared assumptions (so confidence bands are honest, not magic) ──────────
BLENDED_PARTNER_RATE_USD_PER_HR = 250.0  # mid-market prof-services blended rate [LIKELY]
HOURS_PER_SCOPE_DELAY_DAY = 0.5          # partner hours leaked per excess scoping day [LIKELY]
SCOPE_TARGET_DAYS = 5.0                  # PRODUCT objective: 5-day proposal turnaround
VENDOR_CONCENTRATION_FLAG = 0.25         # > 25% of cost base on one vendor = risk
CUSTOMER_CONCENTRATION_FLAG = 0.15       # > 15% of revenue from one customer = risk
PRO_SERVICES_BENCHMARK_PCT = 0.10        # advisory spend > 10% of OPEX is reducible [LIKELY]
PRO_SERVICES_REDUCIBLE_PCT = 0.30        # share of outsized advisory plausibly insourced [LIKELY]
AR_RECOVERY_PCT = 0.80                   # share of overdue AR realistically collectable [LIKELY]


# ── helpers ───────────────────────────────────────────────────────────────────
def _acct(baseline: dict) -> dict:
    acct = baseline.get("accounting")
    if not acct:
        raise ValueError("baseline has no accounting view")
    return acct


def _total_opex(acct: dict) -> float:
    """OPEX = operating expenses (exclude COGS). Prefer explicit P&L lines."""
    pnl = acct.get("profit_and_loss", {}) or {}
    expense_lines = [v for k, v in pnl.items() if k.startswith("Expense:")]
    if expense_lines:
        return float(sum(expense_lines))
    # fallback: vendor rows in Expense:* categories
    return float(sum(
        v.get("amount_usd", 0) for v in acct.get("expenses_by_vendor", [])
        if v.get("category", "").startswith("Expense:")
    ))


# ── analytics (each returns a normalized dict, or None when no signal) ─────────
def a_vendor_concentration(baseline: dict) -> Optional[dict]:
    acct = _acct(baseline)
    vendors = acct.get("expenses_by_vendor", []) or []
    if not vendors:
        return None
    total = sum(v.get("amount_usd", 0) for v in vendors)
    if total <= 0:
        return None
    top = max(vendors, key=lambda v: v.get("amount_usd", 0))
    share = top["amount_usd"] / total
    top3 = sorted(vendors, key=lambda v: -v.get("amount_usd", 0))[:3]
    top3_share = sum(v["amount_usd"] for v in top3) / total
    flagged = share > VENDOR_CONCENTRATION_FLAG
    return {
        "summary": f"Top vendor {top['vendor']} is {share:.0%} of vendor spend; top-3 = {top3_share:.0%}",
        "flagged": flagged,
        "top_vendor": top["vendor"],
        "top_vendor_share": round(share, 4),
        "top_vendor_usd": float(top["amount_usd"]),
        "top3_share": round(top3_share, 4),
        "total_vendor_spend": float(total),
        "source": [f"accounting.expenses_by_vendor[{top['vendor']}]={top['amount_usd']:.0f}",
                   f"accounting.expenses_by_vendor total={total:.0f}"],
    }


def a_customer_concentration(baseline: dict) -> Optional[dict]:
    acct = _acct(baseline)
    invoices = acct.get("invoices", []) or []
    if not invoices:
        return None
    by_cust: dict[str, float] = {}
    for inv in invoices:
        by_cust[inv["customer"]] = by_cust.get(inv["customer"], 0.0) + float(inv.get("amount_usd", 0))
    total = sum(by_cust.values())
    if total <= 0:
        return None
    top_cust, top_amt = max(by_cust.items(), key=lambda kv: kv[1])
    share = top_amt / total
    flagged = share > CUSTOMER_CONCENTRATION_FLAG
    return {
        "summary": f"Top customer {top_cust} is {share:.0%} of booked revenue across {len(invoices)} invoices",
        "flagged": flagged,
        "top_customer": top_cust,
        "top_customer_share": round(share, 4),
        "top_customer_usd": float(top_amt),
        "booked_revenue": float(total),
        "source": [f"accounting.invoices[customer={top_cust}]={top_amt:.0f}",
                   f"accounting.invoices booked_total={total:.0f}"],
    }


def a_ar_overdue(baseline: dict) -> Optional[dict]:
    acct = _acct(baseline)
    invoices = acct.get("invoices", []) or []
    overdue = [i for i in invoices if i.get("status") == "overdue" or (i.get("paid_at") is None and i.get("status") != "paid")]
    exposure = sum(float(i.get("amount_usd", 0)) for i in overdue)
    if exposure <= 0:
        return None
    recoverable = exposure * AR_RECOVERY_PCT
    ids = [i.get("invoice_id") for i in overdue]
    return {
        "summary": f"{len(overdue)} overdue invoices = ${exposure:,.0f} AR exposure; ~${recoverable:,.0f} recoverable",
        "flagged": True,
        "overdue_count": len(overdue),
        "exposure_usd": float(exposure),
        "recoverable_usd": float(recoverable),
        "source": [f"accounting.invoices[status=overdue ids={ids}] sum={exposure:.0f}",
                   f"recovery assumption {AR_RECOVERY_PCT:.0%} [LIKELY]"],
    }


def a_opex_benchmark(baseline: dict) -> Optional[dict]:
    acct = _acct(baseline)
    vendors = acct.get("expenses_by_vendor", []) or []
    opex = _total_opex(acct)
    if opex <= 0:
        return None
    advisory = sum(v.get("amount_usd", 0) for v in vendors
                   if "professional" in v.get("category", "").lower()
                   or "advisory" in v.get("vendor", "").lower())
    if advisory <= 0:
        return None
    share = advisory / opex
    if share <= PRO_SERVICES_BENCHMARK_PCT:
        return {
            "summary": f"Advisory spend is {share:.0%} of OPEX — within benchmark",
            "flagged": False,
            "advisory_usd": float(advisory),
            "opex_usd": float(opex),
            "advisory_share": round(share, 4),
            "reducible_usd": 0.0,
            "source": [f"advisory={advisory:.0f}", f"opex={opex:.0f}"],
        }
    excess = advisory - PRO_SERVICES_BENCHMARK_PCT * opex
    reducible = excess * PRO_SERVICES_REDUCIBLE_PCT
    return {
        "summary": f"Advisory spend is {share:.0%} of OPEX (benchmark {PRO_SERVICES_BENCHMARK_PCT:.0%}); ~${reducible:,.0f}/yr reducible",
        "flagged": True,
        "advisory_usd": float(advisory),
        "opex_usd": float(opex),
        "advisory_share": round(share, 4),
        "excess_usd": float(excess),
        "reducible_usd": float(reducible),
        "source": [f"accounting advisory spend={advisory:.0f}",
                   f"accounting OPEX={opex:.0f}",
                   f"benchmark {PRO_SERVICES_BENCHMARK_PCT:.0%}, insourceable {PRO_SERVICES_REDUCIBLE_PCT:.0%} [LIKELY]"],
    }


def a_scope_cycle_time(baseline: dict) -> Optional[dict]:
    acct = _acct(baseline)
    invoices = acct.get("invoices", []) or []
    delays = []
    for inv in invoices:
        fc, ss = inv.get("first_contact_at"), inv.get("scope_sent_at")
        if not fc or not ss:
            continue
        try:
            d = (date.fromisoformat(ss) - date.fromisoformat(fc)).days
        except ValueError:
            continue
        if d >= 0:
            delays.append(d)
    if not delays:
        return None
    n = len(delays)
    avg = sum(delays) / n
    excess = max(0.0, avg - SCOPE_TARGET_DAYS)
    leaked_hours = excess * HOURS_PER_SCOPE_DELAY_DAY * n
    impact = leaked_hours * BLENDED_PARTNER_RATE_USD_PER_HR
    return {
        "summary": f"Avg scoping {avg:.1f} days vs {SCOPE_TARGET_DAYS:.0f}-day target across {n} deals; ~${impact:,.0f}/yr partner time",
        "flagged": excess > 0,
        "avg_days": round(avg, 1),
        "target_days": SCOPE_TARGET_DAYS,
        "leaked_hours": round(leaked_hours, 1),
        "impact_usd": float(round(impact)),
        "source": [f"accounting.invoices[{n}] avg first_contact->scope_sent={avg:.1f}d",
                   f"excess over {SCOPE_TARGET_DAYS:.0f}d @ {HOURS_PER_SCOPE_DELAY_DAY}hr/day @ ${BLENDED_PARTNER_RATE_USD_PER_HR:.0f}/hr [LIKELY]"],
    }


def a_margin_structure(baseline: dict) -> Optional[dict]:
    acct = _acct(baseline)
    pnl = acct.get("profit_and_loss", {}) or {}
    revenue = float(pnl.get("TotalIncome", 0))
    cogs = float(pnl.get("TotalCostOfGoodsSold", 0))
    net = float(pnl.get("NetIncome", 0))
    gross = float(pnl.get("GrossProfit", revenue - cogs))
    if revenue <= 0:
        return None
    gm = gross / revenue
    nm = net / revenue
    cogs_share = cogs / revenue
    return {
        "summary": f"Gross margin {gm:.0%}, net margin {nm:.0%}; COGS {cogs_share:.0%} of revenue",
        "flagged": gm < 0.65,
        "gross_margin": round(gm, 4),
        "net_margin": round(nm, 4),
        "cogs_share": round(cogs_share, 4),
        "revenue_usd": revenue,
        "net_income_usd": net,
        "source": [f"accounting.profit_and_loss.TotalIncome={revenue:.0f}",
                   f"accounting.profit_and_loss.GrossProfit={gross:.0f}",
                   f"accounting.profit_and_loss.NetIncome={net:.0f}"],
    }


ANALYTICS: dict[str, Callable[[dict], Optional[dict]]] = {
    "vendor_concentration": a_vendor_concentration,
    "customer_concentration": a_customer_concentration,
    "ar_overdue": a_ar_overdue,
    "opex_benchmark": a_opex_benchmark,
    "scope_cycle_time": a_scope_cycle_time,
    "margin_structure": a_margin_structure,
}


# ── finding construction ──────────────────────────────────────────────────────
def _emb_for(method: str) -> list[float]:
    """Stable 4-d embedding stub per finding theme so council scoring is
    deterministic offline (production swaps to real embeddings)."""
    table = {
        "scope_cycle_time": [0.6, 0.4, 0.1, 0.2],
        "vendor_concentration": [0.1, 0.7, 0.2, 0.0],
        "customer_concentration": [0.3, 0.6, 0.2, 0.1],
        "ar_overdue": [0.2, 0.7, 0.3, 0.0],
        "opex_benchmark": [0.2, 0.6, 0.1, 0.3],
        "margin_structure": [0.4, 0.5, 0.1, 0.2],
    }
    return table.get(method, [0.3, 0.3, 0.3, 0.3])


def finding_from_analytic(method: str, analytic: dict, idx: int) -> Optional[dict]:
    """Lift a normalized analytic into a client-facing finding record.

    Returns None when the analytic carries no actionable impact (so unflagged,
    zero-impact analytics don't become noise findings).
    """
    impact_usd = 0.0
    impact_hours = 0.0
    headline = analytic.get("summary", "")
    bottleneck = ""

    if method == "scope_cycle_time":
        impact_usd = float(analytic.get("impact_usd", 0))
        impact_hours = float(analytic.get("leaked_hours", 0))
        bottleneck = "Proposal scoping cycle time"
        headline = f"Proposal scoping runs {analytic['avg_days']:.0f} days vs a {int(analytic['target_days'])}-day target"
    elif method == "vendor_concentration" and analytic.get("flagged"):
        # Concentration risk: impact is the at-risk dependency dollar exposure.
        impact_usd = float(analytic.get("top_vendor_usd", 0))
        bottleneck = "Single-vendor dependency / cost concentration"
        headline = f"{analytic['top_vendor']} is {analytic['top_vendor_share']:.0%} of vendor spend — concentration risk"
    elif method == "customer_concentration" and analytic.get("flagged"):
        impact_usd = float(analytic.get("top_customer_usd", 0))
        bottleneck = "Revenue concentration in one customer"
        headline = f"{analytic['top_customer']} is {analytic['top_customer_share']:.0%} of revenue — concentration risk"
    elif method == "ar_overdue":
        impact_usd = float(analytic.get("recoverable_usd", 0))
        bottleneck = "Working capital trapped in overdue AR"
        headline = f"${analytic['exposure_usd']:,.0f} in overdue AR; ~${analytic['recoverable_usd']:,.0f} recoverable"
    elif method == "opex_benchmark" and analytic.get("flagged"):
        impact_usd = float(analytic.get("reducible_usd", 0))
        bottleneck = "Outsized advisory/professional-services spend"
        headline = f"Advisory spend {analytic['advisory_share']:.0%} of OPEX — ~${impact_usd:,.0f}/yr reducible"
    elif method == "margin_structure" and analytic.get("flagged"):
        # Margin finding: 5pt gross-margin recovery target on revenue.
        impact_usd = round(analytic.get("revenue_usd", 0) * 0.05)
        bottleneck = "Gross margin below services benchmark"
        headline = f"Gross margin {analytic['gross_margin']:.0%}; 5pt recovery ≈ ${impact_usd:,.0f}/yr"

    if impact_usd <= 0 and impact_hours <= 0:
        return None

    # confidence: derive an honest band from how directly the number is measured
    conf_table = {
        "ar_overdue": 0.85, "vendor_concentration": 0.8, "customer_concentration": 0.8,
        "scope_cycle_time": 0.7, "margin_structure": 0.7, "opex_benchmark": 0.6,
    }
    return {
        "id": f"fin-fin-{idx:03d}",
        "team": "financial",
        "method": method,
        "headline": headline,
        "bottleneck": bottleneck,
        "impact_usd": float(round(impact_usd)),
        "impact_hours": float(round(impact_hours, 1)),
        "evidence": analytic.get("source", []),
        "source": analytic.get("source", []),
        "confidence": conf_table.get(method, 0.6),
        "embedding": _emb_for(method),
        "cluster": [],
    }


class UngroundedFindingError(ValueError):
    """Raised when a finding asserts a dollar/hours impact with no source[] +
    confidence band. This is the LeCun grounding gate wired *into* the producer
    so an ungrounded number can never leave findings.py — not merely caught
    downstream by build/probes/grounded_numbers.py."""


def assert_grounded(finding: dict) -> dict:
    """In-engine grounding gate (mirrors build/probes/grounded_numbers.py).

    Every impact number MUST trace to a non-empty source/evidence list AND carry
    a confidence band. Returns the finding if grounded; raises otherwise. This is
    the wired-in enforcement point: `run_findings` calls it on every emitted
    finding, so the producer itself fails closed on an ungrounded number.
    """
    has_impact = (finding.get("impact_usd") or 0) > 0 or (finding.get("impact_hours") or 0) > 0
    if not has_impact:
        return finding
    src = finding.get("evidence") or finding.get("source")
    if not src:
        raise UngroundedFindingError(
            f"{finding.get('id')} asserts impact with no evidence/source[]"
        )
    if finding.get("confidence") in (None, ""):
        raise UngroundedFindingError(
            f"{finding.get('id')} asserts impact with no confidence band"
        )
    return finding


def run_findings(baseline: dict, *, out_path: Path | str | None = None) -> list[dict]:
    """Produce the financial findings list from a baseline; optionally write JSONL.

    Every emitted finding passes through `assert_grounded` (the LeCun gate wired
    into the producer) before it is returned or written — fail-closed.
    """
    findings: list[dict] = []
    idx = 1
    for method, fn in ANALYTICS.items():
        analytic = fn(baseline)
        if not analytic:
            continue
        f = finding_from_analytic(method, analytic, idx)
        if f:
            findings.append(assert_grounded(f))
            idx += 1
    findings.sort(key=lambda f: -(f.get("impact_usd", 0)))
    if out_path:
        p = Path(out_path)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text("\n".join(json.dumps(f) for f in findings) + ("\n" if findings else ""))
    return findings


def from_snapshot(tenant_id: str, *, run_id: str | None = None,
                  snapshots_root: Path | None = None,
                  runs_root: Path | None = None) -> list[dict]:
    """Load a tenant baseline, run findings, write to runs/{run_id}/gauntlet/financial/findings.jsonl."""
    repo = Path(__file__).resolve().parents[3]
    root = snapshots_root or (repo / "client" / "snapshots")
    baseline = json.loads((root / tenant_id / "baseline.json").read_text())
    rid = run_id or tenant_id
    runs = runs_root or (repo / "runs")
    out = runs / rid / "gauntlet" / "financial" / "findings.jsonl"
    return run_findings(baseline, out_path=out)


def _main() -> int:
    import argparse

    p = argparse.ArgumentParser(description="Emit financial findings from a tenant baseline")
    p.add_argument("--tenant", required=True)
    p.add_argument("--run-id", default=None)
    args = p.parse_args()
    findings = from_snapshot(args.tenant, run_id=args.run_id)
    print(json.dumps(findings, indent=2))
    return 0 if findings else 1


if __name__ == "__main__":
    raise SystemExit(_main())
