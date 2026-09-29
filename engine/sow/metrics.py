"""Quantified success metrics per SOW (P3.T4).

Each SOW candidate carries CEO-language success metrics, every number traced to a
baseline line + carrying a confidence band so the grounded-numbers gate
(`scripts/probes/grounded_numbers.py`) passes over the SOW metrics exactly as it
does over findings:

  - **EBITDA uplift %/yr** — the SOW's annual impact as a percent of the tenant's
    current EBITDA base (so a $1.9M thrust on a $3.08M EBITDA base reads as a
    +62% EBITDA lift — the multiple a CEO actually cares about).
  - **hrs/yr reclaimed** — partner/staff hours the SOW frees, summed from its
    findings' `impact_hours`.
  - **payback months** — months for the SOW's annualized impact to recover the
    declared FDE engagement cost.

EBITDA base is read from the baseline P&L (NetIncome as the conservative EBITDA
proxy when no explicit D&A/interest lines are present — source-traced). The
engagement cost is a declared, source-tagged assumption ([LIKELY]) so payback is
honest rather than magic.

Output records carry `impact_usd`/`impact_hours` + `source[]` + `confidence`, so
they are valid grounded-numbers records when written to a findings.jsonl-shaped
artifact.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Any, Sequence

# ── declared assumptions (source-tagged so payback is honest) ──────────────────
DEFAULT_ENGAGEMENT_COST_USD = 180_000.0   # blended FDE engagement cost / thrust [LIKELY]
EBITDA_FLOOR_USD = 1.0                     # guard against divide-by-zero


def _attr(obj: Any, name: str, default=None):
    if isinstance(obj, dict):
        return obj.get(name, default)
    return getattr(obj, name, default)


@dataclass
class SOWMetrics:
    sow_id: str
    impact_usd: float
    impact_hours: float
    ebitda_base_usd: float
    ebitda_uplift_pct: float          # annual impact as % of EBITDA base
    hours_reclaimed_per_year: float
    engagement_cost_usd: float
    payback_months: float
    confidence: float
    source: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)

    def to_grounded_record(self) -> dict:
        """Shape that the grounded_numbers probe validates (impact + source + confidence)."""
        return {
            "id": f"metric-{self.sow_id}",
            "sow_id": self.sow_id,
            "impact_usd": self.impact_usd,
            "impact_hours": self.impact_hours,
            "ebitda_uplift_pct": self.ebitda_uplift_pct,
            "payback_months": self.payback_months,
            "confidence": self.confidence,
            "source": self.source,
            "evidence": self.source,
        }


def ebitda_base(baseline: dict) -> tuple[float, str]:
    """Conservative EBITDA proxy from the P&L + its source line."""
    pnl = (baseline.get("accounting", {}) or {}).get("profit_and_loss", {}) or {}
    net = float(pnl.get("NetIncome", 0.0) or 0.0)
    if net > 0:
        return net, f"accounting.profit_and_loss.NetIncome={net:.0f} (EBITDA proxy)"
    # fallback: GrossProfit - operating expenses
    gross = float(pnl.get("GrossProfit", 0.0) or 0.0)
    opex = float(pnl.get("TotalExpenses", 0.0) or 0.0)
    ebitda = gross - opex
    return (max(ebitda, EBITDA_FLOOR_USD),
            f"accounting.profit_and_loss.GrossProfit={gross:.0f} - TotalExpenses={opex:.0f}")


def metrics_for(
    sow: Any,
    baseline: dict,
    *,
    engagement_cost_usd: float = DEFAULT_ENGAGEMENT_COST_USD,
) -> SOWMetrics:
    impact = float(_attr(sow, "impact_usd", 0.0) or 0.0)
    hours = float(_attr(sow, "impact_hours", 0.0) or 0.0)
    conf = float(_attr(sow, "confidence", 0.0) or 0.0)
    base, base_src = ebitda_base(baseline)

    ebitda_uplift_pct = round(100.0 * impact / max(base, EBITDA_FLOOR_USD), 2)
    payback_months = round(12.0 * engagement_cost_usd / impact, 2) if impact > 0 else float("inf")

    # union the SOW's source lines + the EBITDA base + the cost assumption so
    # every metric number is traceable.
    source = list(_attr(sow, "source", []) or [])
    source.append(base_src)
    source.append(f"engagement_cost=${engagement_cost_usd:,.0f}/thrust [LIKELY]")

    return SOWMetrics(
        sow_id=_attr(sow, "id", "unknown"),
        impact_usd=round(impact, 2),
        impact_hours=round(hours, 1),
        ebitda_base_usd=round(base, 2),
        ebitda_uplift_pct=ebitda_uplift_pct,
        hours_reclaimed_per_year=round(hours, 1),
        engagement_cost_usd=engagement_cost_usd,
        payback_months=payback_months,
        confidence=conf,
        source=source,
    )


def metrics_for_all(
    sows: Sequence[Any],
    baseline: dict,
    *,
    engagement_cost_usd: float = DEFAULT_ENGAGEMENT_COST_USD,
    artifacts_dir: Path | str | None = None,
) -> list[SOWMetrics]:
    out = [metrics_for(s, baseline, engagement_cost_usd=engagement_cost_usd) for s in sows]
    if artifacts_dir:
        d = Path(artifacts_dir)
        d.mkdir(parents=True, exist_ok=True)
        body = "\n".join(json.dumps(m.to_grounded_record()) for m in out) + ("\n" if out else "")
        # human-named artifact
        (d / "metrics.jsonl").write_text(body)
        # findings.jsonl-named copy so the standing grounded_numbers probe
        # (globs runs/**/findings.jsonl) validates SOW metric numbers too —
        # every metric record is impact + source[] + confidence shaped.
        (d / "findings.jsonl").write_text(body)
    return out


def attach_metrics(
    sows: Sequence[Any],
    baseline: dict,
    *,
    engagement_cost_usd: float = DEFAULT_ENGAGEMENT_COST_USD,
) -> list[dict]:
    out: list[dict] = []
    for s in sows:
        d = s.to_dict() if hasattr(s, "to_dict") else dict(s)
        d["metrics"] = metrics_for(s, baseline, engagement_cost_usd=engagement_cost_usd).to_dict()
        out.append(d)
    return out
