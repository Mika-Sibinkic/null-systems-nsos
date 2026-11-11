"""CEO decision report: the 2-3 scored SOW candidates, side by side.

Run the whole pipeline with `python scripts/run_synthetic.py` to produce one.
"""
from __future__ import annotations
from pathlib import Path
from typing import Sequence

import engine.sow.metrics as fmt  # fmt_payback / fmt_ebitda: one formatter for every surface
import engine.sow.wwod_score as wwod
import presentation.side_by_side.sbs as sbs_mod


def render_sow_report(
    firm: dict,
    sows: Sequence,
    baseline: dict,
    *,
    output_path: Path | str | None = None,
    engagement_cost_usd: float | None = None,
    pending: Sequence[dict] = (),
) -> str:
    """Owner-facing report rendering the 2-3 scored SOW candidates side by side.

    This is the *decision* report: each SOW carries its quantified metrics (EBITDA lift, payback, hours),
    its WWOD consultant-conviction score, and its 5-pillar deployability grade —
    then a side-by-side comparison matrix and a single honest recommendation.

    No new numbers are minted: every dollar/hour traces to the SOW's `source[]`,
    so the grounded-numbers contract holds and the quality_judge gate sees a
    grounded, action-bearing, confidence-tagged client-facing output.

    `pending` are findings the review gate held for a human; they are listed by
    name and kept out of every SOW and total.
    """
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
        f"From your data we assembled **{len(sbs.columns)} growth options**, each a "
        f"statement of work (SOW) you can pick. Every number below comes from your "
        f"books or from an assumption we name next to it.\n"
    )
    lines.append("How to read the scores:\n")
    base, _, base_label = fmt.ebitda_base(baseline)
    if base > 0:
        lines.append(
            f"- **EBITDA lift**: annual impact divided by your {base_label} (${base:,.0f}), "
            f"which stands in for EBITDA. Real EBITDA is higher, so the real lift is lower."
        )
    cost = engagement_cost_usd if engagement_cost_usd is not None else fmt.DEFAULT_ENGAGEMENT_COST_USD
    lines.append(f"- **Payback**: assumes the work costs ${cost:,.0f} per option.")
    lines.append(
        "- **Deployability grade**: a placeholder. Three of its five checks are fixed today, so the "
        "letter mostly reflects annual impact and how many findings back the option. ⚠ marks an "
        f"option under ${fmt.MIN_WORTHWHILE_IMPACT_USD:,.0f}/yr, the size we assume an option needs "
        "to be worth an engagement."
    )
    if any(wwod.COLD_START_GAP in col.gaps for col in sbs.columns):
        lines.append(f"- **Consultant conviction**: {wwod.COLD_START_GAP}.")
    lines.append("- **Evidence confidence**: set per type of finding, not measured for each number.")
    solo = [str(i) for i, col in enumerate(sbs.columns, start=1) if wwod.SINGLE_FINDING_GAP in col.gaps]
    if solo:
        if len(solo) == 1:
            which, them = f"Option {solo[0]} rests", "it"
        else:
            which, them = f"Options {', '.join(solo[:-1])} and {solo[-1]} each rest", "them"
        lines.append(f"- **One finding**: {which} on one finding. A second, independent finding would make {them} firmer.")
    lines.append("\n---\n")

    for i, col in enumerate(sbs.columns, start=1):
        rec_mark = " — **our recommendation**" if col.sow_id == sbs.recommended_sow_id else ""
        assumed = sbs_mod.assumptions(col.source)
        lines.append(f"## Option {i} — {col.title}{rec_mark}")
        lines.append("")
        lines.append(f"{col.objective}\n")
        lines.append(f"- **Annual impact**: ${col.impact_usd:,.0f}/year")
        for a in assumed:
            lines.append(f"- **Assumes**: {a}")
        if col.exposure_usd:
            lines.append(f"- **At risk**: ${col.exposure_usd:,.0f} (exposure, not counted in annual impact, EBITDA or payback)")
        lines.append(f"- **EBITDA lift**: {fmt.fmt_ebitda(col.ebitda_uplift_pct, col.ebitda_base_label)}")
        if col.impact_hours:
            lines.append(f"- **Leadership hours freed**: {col.impact_hours:.0f} hours/year")
        lines.append(f"- **Payback**: {fmt.fmt_payback(col.payback_months)}")
        lines.append(f"- **Consultant conviction**: {col.wwod_score:.0%} (how hard we'd push this)")
        grade_note = col.grade + (f" ⚠ {col.blockers[0]}" if col.blockers else "")
        lines.append(f"- **Deployability grade**: {grade_note}")
        lines.append(
            f"- **Evidence confidence**: {col.confidence:.0%}, from "
            f"{len(col.source) - len(assumed)} lines of your accounting"
        )
        specific = sbs_mod.owner_gaps(col.gaps)
        if specific:
            lines.append(f"- **Before committing, we recommend you confirm**: {specific[0]}")
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
        "Reply with the option you want, or book a 30-minute scope call. The option "
        "you pick becomes the brief for the engineer who does the work.\n"
    )

    md = "\n".join(lines)
    if output_path:
        Path(output_path).write_text(md)
    return md
