"""CEO decision report: the 2-3 scored SOW candidates, side by side.

Run the whole pipeline with `python scripts/run_synthetic.py` to produce one.
"""
from __future__ import annotations
import importlib.util
from pathlib import Path
from typing import Sequence


def _load_sbs_module():
    """Load the side-by-side renderer (hyphenated package dir -> load by path)."""
    repo = Path(__file__).resolve().parents[2]
    sbs_path = repo / "presentation" / "side-by-side" / "sbs.py"
    import sys
    if "nsos_sbs" in sys.modules:
        return sys.modules["nsos_sbs"]
    spec = importlib.util.spec_from_file_location("nsos_sbs", str(sbs_path))
    mod = importlib.util.module_from_spec(spec)
    sys.modules["nsos_sbs"] = mod  # required so @dataclass resolves cls.__module__
    if str(repo) not in sys.path:
        sys.path.insert(0, str(repo))
    spec.loader.exec_module(mod)
    return mod


def render_sow_report(
    firm: dict,
    sows: Sequence,
    baseline: dict,
    *,
    output_path: Path | str | None = None,
    engagement_cost_usd: float | None = None,
    pending: Sequence[dict] = (),
) -> str:
    """CEO-language report rendering the 2-3 scored SOW candidates side-by-side (P4.T1).

    Unlike `render_executive_report` (a list of findings), this is the *decision*
    report: each SOW carries its quantified metrics (EBITDA lift, payback, hours),
    its WWOD consultant-conviction score, and its 5-pillar deployability grade —
    then a side-by-side comparison matrix and a single honest recommendation.

    No new numbers are minted: every dollar/hour traces to the SOW's `source[]`,
    so the grounded-numbers contract holds and the quality_judge gate sees a
    grounded, action-bearing, confidence-tagged client-facing output.

    `pending` are findings the review gate held for a human; they are listed by
    name and kept out of every SOW and total.
    """
    sbs_mod = _load_sbs_module()
    fmt = sbs_mod._metrics  # fmt_payback / fmt_ebitda: one formatter for every surface
    sbs = sbs_mod.build_side_by_side(
        sows, baseline, engagement_cost_usd=engagement_cost_usd
    )

    lines: list[str] = []
    lines.append(f"# {firm['firm_name']} — Growth Options")
    lines.append("")
    lines.append(
        f"*Prepared by Vinny · A Null Systems product · "
        f"{firm.get('engagement_arrived_at', '')}*"
    )
    lines.append("\n---\n")
    lines.append("## Executive summary\n")
    lines.append(
        f"From your data we assembled **{len(sbs.columns)} coherent growth options**. "
        f"Each is a Statement of Work you can choose between by where you want the "
        f"business to go — the numbers below all trace back to your own books.\n"
    )
    lines.append("---\n")

    for i, col in enumerate(sbs.columns, start=1):
        rec_mark = " — **our recommendation**" if col.sow_id == sbs.recommended_sow_id else ""
        lines.append(f"## Option {i} — {col.title}{rec_mark}")
        lines.append("")
        lines.append(f"{col.objective}\n")
        lines.append(f"- **Annual impact**: based on your QuickBooks data, ${col.impact_usd:,.0f}/year")
        if col.exposure_usd:
            lines.append(f"- **At risk**: ${col.exposure_usd:,.0f} (exposure, not counted in annual impact, EBITDA or payback)")
        lines.append(f"- **EBITDA lift**: {fmt.fmt_ebitda(col.ebitda_uplift_pct)}")
        if col.impact_hours:
            lines.append(f"- **Leadership hours freed**: {col.impact_hours:.0f} hours/year")
        lines.append(f"- **Payback**: {fmt.fmt_payback(col.payback_months)}")
        lines.append(f"- **Consultant conviction**: {col.wwod_score:.0%} (how hard we'd push this)")
        grade_note = f"{col.grade}" + (" — has a deployability flag, see below" if col.blockers else "")
        lines.append(f"- **Deployability grade**: {grade_note}")
        lines.append(
            f"- **Evidence confidence**: {col.confidence:.0%}, based on "
            f"{len(col.source)} source lines from your accounting"
        )
        if col.gaps:
            lines.append(f"- **Before committing, we recommend you confirm**: {col.gaps[0]}")
        lines.append("\n---\n")

    lines.append("## Side-by-side\n")
    lines.append(sbs_mod.render_markdown(sbs))
    lines.append("\n---\n")

    if pending:
        lines.append("## Pending review\n")
        lines.append("A person checks these before they count. They are not in any option or total above.\n")
        for f in pending:
            lines.append(f"- {f.get('headline', f.get('id'))} (confidence {float(f.get('confidence', 0)):.0%})")
        lines.append("\n---\n")

    lines.append("## How to choose\n")
    lines.append(
        "Pick the option that matches where you want the business to go. "
        "Reply to confirm scope or schedule a 30-min scope call; the chosen "
        "option exports directly as an FDE engagement packet.\n"
    )

    md = "\n".join(lines)
    if output_path:
        Path(output_path).write_text(md)
    return md
