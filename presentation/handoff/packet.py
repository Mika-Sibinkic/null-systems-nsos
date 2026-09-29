"""FDE handoff packet export — selected SOW -> engagement brief (P4.T3).

When the operator selects one of the 2-3 scored SOW candidates (P4.T2), that
choice becomes a real FDE engagement, not a PDF. This module exports the chosen
SOW as a structured handoff packet the Field Deployment Engineer picks up: the
scope, the quantified target, the source-traced evidence, the deployability
flags to clear, and the success metrics the outcome flywheel (P5) will later
measure predicted-vs-realized against.

Design (deterministic, offline, source-traced):

  - The packet is assembled from the run's committed artifacts — the side-by-side
    columns (already carry WWOD push, pillar grade, metrics, gaps, source[]) and
    the firm profile. No new dollar number is minted; every figure in the packet
    traces to a `source[]` line, so the grounded-numbers contract holds at the
    handoff boundary too.
  - `gaps` from WWOD + pillar `blockers` become the FDE's *validation checklist*
    (the honest "confirm before deploying" list — Karpathy human-in-loop carried
    all the way to the engagement).
  - The packet exports as both machine-readable JSON (engine/flywheel consumption)
    and a markdown engagement brief (the FDE reads).

This is the FDE *engagement* handoff (pre-deployment scope), distinct from the
post-delivery handoff in `schemas/handoff-package.json` (that one validates a
finished build's delivery completeness; this one kicks the engagement off).
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Any, Sequence


def _attr(obj: Any, name: str, default=None):
    if isinstance(obj, dict):
        return obj.get(name, default)
    return getattr(obj, name, default)


@dataclass
class HandoffPacket:
    run_id: str
    tenant_id: str
    firm_name: str
    selected_sow_id: str
    title: str
    objective: str
    # quantified target (all source-traced)
    impact_usd: float
    impact_hours: float
    ebitda_uplift_pct: float
    payback_months: float
    confidence: float
    # scoring carried into the engagement
    wwod_score: float
    deployability_grade: str
    # the FDE's honest pre-deploy checklist
    validation_checklist: list[str] = field(default_factory=list)
    deployability_blockers: list[str] = field(default_factory=list)
    # full source trace — every number above descends from these lines
    source: list[str] = field(default_factory=list)
    # success metrics the flywheel measures realized-vs-predicted on
    success_metrics: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return asdict(self)


def _column_for(side_by_side: dict, sow_id: str | None) -> dict:
    """Resolve the selected column; default to the recommendation, then first."""
    cols = side_by_side.get("columns", []) or []
    if not cols:
        raise ValueError("side-by-side payload has no columns to hand off")
    if sow_id:
        for c in cols:
            if c.get("sow_id") == sow_id:
                return c
        raise ValueError(f"selected sow_id {sow_id!r} not present in run candidates")
    rec = side_by_side.get("recommended_sow_id")
    if rec:
        for c in cols:
            if c.get("sow_id") == rec:
                return c
    return cols[0]


def build_packet(
    *,
    run_id: str,
    tenant_id: str,
    firm: dict,
    side_by_side: dict,
    selected_sow_id: str | None = None,
) -> HandoffPacket:
    """Assemble the FDE handoff packet for the selected SOW from a run's artifacts."""
    col = _column_for(side_by_side, selected_sow_id)
    gaps = list(col.get("gaps", []) or [])
    blockers = list(col.get("blockers", []) or [])
    # the validation checklist is gaps + blockers, deduped, order-stable
    seen: set[str] = set()
    checklist: list[str] = []
    for item in [*blockers, *gaps]:
        if item and item not in seen:
            seen.add(item)
            checklist.append(item)

    success_metrics = {
        "impact_usd": float(col.get("impact_usd", 0.0) or 0.0),
        "impact_hours": float(col.get("impact_hours", 0.0) or 0.0),
        "ebitda_uplift_pct": float(col.get("ebitda_uplift_pct", 0.0) or 0.0),
        "payback_months": col.get("payback_months"),
        "confidence": float(col.get("confidence", 0.0) or 0.0),
    }

    return HandoffPacket(
        run_id=run_id,
        tenant_id=tenant_id,
        firm_name=firm.get("firm_name", tenant_id),
        selected_sow_id=col.get("sow_id", "unknown"),
        title=col.get("title", ""),
        objective=col.get("objective", ""),
        impact_usd=float(col.get("impact_usd", 0.0) or 0.0),
        impact_hours=float(col.get("impact_hours", 0.0) or 0.0),
        ebitda_uplift_pct=float(col.get("ebitda_uplift_pct", 0.0) or 0.0),
        payback_months=col.get("payback_months"),
        confidence=float(col.get("confidence", 0.0) or 0.0),
        wwod_score=float(col.get("wwod_score", 0.0) or 0.0),
        deployability_grade=col.get("grade", "?"),
        validation_checklist=checklist,
        deployability_blockers=blockers,
        source=list(col.get("source", []) or []),
        success_metrics=success_metrics,
    )


def render_markdown(p: HandoffPacket) -> str:
    """The engagement brief the FDE reads."""
    payback = (
        "—"
        if p.payback_months in (None, float("inf"))
        else f"{float(p.payback_months):.0f} months"
    )
    lines: list[str] = []
    lines.append(f"# FDE Engagement Packet — {p.firm_name}")
    lines.append("")
    lines.append(f"*Run `{p.run_id}` · tenant `{p.tenant_id}` · SOW `{p.selected_sow_id}`*")
    lines.append("\n---\n")
    lines.append(f"## Scope — {p.title}\n")
    lines.append(f"{p.objective}\n")
    lines.append("## Quantified target (source-traced)\n")
    lines.append(f"- **Annual impact**: ${p.impact_usd:,.0f}/year")
    lines.append(f"- **EBITDA lift**: +{p.ebitda_uplift_pct:.0f}%")
    if p.impact_hours:
        lines.append(f"- **Leadership hours freed**: {p.impact_hours:.0f} hours/year")
    lines.append(f"- **Payback**: {payback}")
    lines.append(f"- **Evidence confidence**: {p.confidence:.0%}")
    lines.append(f"- **Consultant conviction (WWOD)**: {p.wwod_score:.0%}")
    lines.append(f"- **Deployability grade**: {p.deployability_grade}")
    lines.append("")
    lines.append("## Validation checklist (confirm before deploying)\n")
    if p.validation_checklist:
        for item in p.validation_checklist:
            lines.append(f"- [ ] {item}")
    else:
        lines.append("- [ ] No outstanding gaps flagged — proceed to scope confirmation.")
    lines.append("")
    lines.append("## Evidence trace\n")
    for s in p.source:
        lines.append(f"- {s}")
    lines.append("\n---\n")
    lines.append(
        "The outcome flywheel will track realized-vs-predicted against the "
        "quantified target above once the engagement ships.\n"
    )
    return "\n".join(lines)


def export_packet(
    p: HandoffPacket, out_dir: Path | str
) -> tuple[Path, Path]:
    """Write the packet as JSON + a markdown engagement brief. Returns both paths."""
    d = Path(out_dir)
    d.mkdir(parents=True, exist_ok=True)
    json_path = d / "fde-handoff-packet.json"
    md_path = d / "fde-handoff-packet.md"
    json_path.write_text(json.dumps(p.to_dict(), indent=2, default=str))
    md_path.write_text(render_markdown(p))
    return json_path, md_path


def from_run(
    run_id: str,
    *,
    selected_sow_id: str | None = None,
    runs_root: Path | None = None,
    firm_path: Path | None = None,
    tenant_id: str | None = None,
) -> HandoffPacket:
    """End-to-end: read a run's side-by-side + firm -> packet, exported under
    runs/{run_id}/handoff/."""
    repo = Path(__file__).resolve().parents[2]
    runs = runs_root or (repo / "runs")
    sbs_path = runs / run_id / "presentation" / "side-by-side.json"
    side_by_side = json.loads(sbs_path.read_text())
    if firm_path is None:
        firm_path = repo / "examples" / "synthetic-client-a" / "firm.json"
    firm = json.loads(Path(firm_path).read_text())
    packet = build_packet(
        run_id=run_id,
        tenant_id=tenant_id or firm.get("tenant_id", "synth-acme-services"),
        firm=firm,
        side_by_side=side_by_side,
        selected_sow_id=selected_sow_id,
    )
    export_packet(packet, runs / run_id / "handoff")
    return packet


def _main() -> int:
    import argparse

    ap = argparse.ArgumentParser(description="Export an FDE handoff packet for a selected SOW")
    ap.add_argument("--run-id", required=True)
    ap.add_argument("--sow-id", default=None, help="selected SOW id (default: recommendation)")
    args = ap.parse_args()
    p = from_run(args.run_id, selected_sow_id=args.sow_id)
    print(render_markdown(p))
    return 0


if __name__ == "__main__":
    raise SystemExit(_main())
