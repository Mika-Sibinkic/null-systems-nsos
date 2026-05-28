"""Executive report generator — fills template.md from council output + firm data.

Skeleton. Wire to a real template engine (Jinja2) and PDF renderer (Pandoc).
"""
from __future__ import annotations
import json
from pathlib import Path
from typing import Sequence


def render_executive_report(
    firm: dict,
    ranked_findings: Sequence[dict],
    *,
    template_path: Path | str | None = None,
    output_path: Path | str | None = None,
    side_by_side: dict | None = None,
    top_n: int = 3,
) -> str:
    """Produce a markdown executive report.

    Args:
        firm: dict from `examples/<tenant>/firm.json`
        ranked_findings: list of finding dicts (post-council, in rank order)
        side_by_side: optional dict for the side-by-side section
        top_n: number of opportunities to include in main body
    """
    top = list(ranked_findings)[:top_n]
    total_usd = sum(f.get("impact_usd", 0) for f in top)
    total_hours = sum(f.get("impact_hours", 0) for f in top)

    lines = []
    lines.append(f"# {firm['firm_name']} — Diagnostic Summary")
    lines.append("")
    lines.append(f"*Prepared by Vinny · A Null Systems product · {firm.get('engagement_arrived_at', '')}*")
    lines.append("\n---\n")
    lines.append("## Executive summary\n")
    lines.append(
        f"We reviewed your data and identified **{len(top)} opportunities**. "
        f"Together they represent **${total_usd:,.0f}/year** "
        f"and **{int(total_hours)} hours** of leadership time per year.\n"
    )
    lines.append("---\n")

    for i, f in enumerate(top, start=1):
        lines.append(f"## Opportunity {i} — {f.get('headline', '')}")
        lines.append("")
        lines.append(_what_we_found(f))
        lines.append("")
        lines.append(_cost_today(f))
        lines.append(_savings(f))
        lines.append(_confidence_sentence(f))
        lines.append(_next_step(f))
        lines.append("\n---\n")

    if side_by_side:
        lines.append("## Side-by-side — your idea vs. leaner alternative\n")
        lines.append("| | Your scope | Leaner alternative |")
        lines.append("|---|---|---|")
        for label, (yours, alt) in side_by_side.items():
            lines.append(f"| {label} | {yours} | {alt} |")
        lines.append("")
        lines.append("---\n")

    if firm.get("known_baseline"):
        lines.append("## Things you already know that we agree with\n")
        for k in firm["known_baseline"]:
            lines.append(f"- {k['text']}")
        lines.append("\n---\n")

    lines.append("## How to confirm scope\n")
    lines.append("Reply to this email or schedule a 30-min scope call.\n")

    md = "\n".join(lines)
    if output_path:
        Path(output_path).write_text(md)
    return md


def _what_we_found(f: dict) -> str:
    ev = f.get("evidence", [])
    if not ev:
        return f.get("headline", "")
    summary = " ".join(ev[:2])
    return summary


def _cost_today(f: dict) -> str:
    parts = []
    if f.get("impact_usd"):
        parts.append(f"${f['impact_usd']:,.0f}/year")
    if f.get("impact_hours"):
        parts.append(f"{f['impact_hours']} hours/year")
    return f"- **Costing you today**: {' and '.join(parts) if parts else 'N/A'}"


def _savings(f: dict) -> str:
    parts = []
    if f.get("impact_usd"):
        parts.append(f"${f['impact_usd']:,.0f}/year recovered")
    if f.get("impact_hours"):
        parts.append(f"{f['impact_hours']} hours/year freed")
    return f"- **What changing would save**: {' and '.join(parts) if parts else 'See evidence'}"


def _confidence_sentence(f: dict) -> str:
    c = f.get("confidence", 0.0)
    if c >= 0.85:
        word = "highly"
    elif c >= 0.6:
        word = "moderately"
    else:
        word = "suggestively"
    return f"- **Confidence**: We're {word} confident based on {len(f.get('evidence', []))} evidence sources."


def _next_step(f: dict) -> str:
    return "- **Suggested next step**: Scope a 2-week FDE engagement to confirm and execute."


if __name__ == "__main__":
    # Smoke test against synthetic-client-a
    base = Path(__file__).resolve().parents[2] / "examples" / "synthetic-client-a"
    firm = json.loads((base / "firm.json").read_text())
    findings = [json.loads(line) for line in (base / "findings.jsonl").read_text().splitlines() if line.strip()]
    # Run council
    import sys
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
    from engine.council import run_council
    ranked = run_council(
        findings,
        ceo_priorities=[{"text": p["text"], "embedding": [0.6, 0.4, 0.1, 0.2], "weight": p["weight"]} for p in firm.get("stated_objectives", [])],
        known_baseline=[{"text": k["text"], "embedding": [0.2, 0.1, 0.8, 0.1]} for k in firm.get("known_baseline", [])],
    )
    by_id = {f["id"]: f for f in findings}
    ranked_dicts = [by_id[r.finding_id] for r in ranked]
    report = render_executive_report(
        firm,
        ranked_dicts,
        output_path=base / "report.md",
    )
    print(report[:1200])
    print(f"\n... [{len(report)} chars total]")
    print(f"\n✓ Wrote {base / 'report.md'}")
