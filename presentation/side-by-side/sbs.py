"""Side-by-side SOW comparison renderer (P4.T1).

A CEO does not buy a list of findings; they pick between 2-3 coherent growth
thrusts (the SOW candidates from `engine.sow.assembly`). This module renders
those candidates *next to each other* in CEO language so the choice is an
intuition call about direction, not an arithmetic exercise.

Design (deterministic, offline, source-traced):

  1. Each SOW candidate is enriched with its three scoring layers — WWOD push
     score (`engine.sow.wwod_score`), 5-pillar deployability grade
     (`engine.sow.pillar_grade`), and quantified metrics
     (`engine.sow.metrics`). No new dollar numbers are minted here; this layer
     only *arranges* numbers that already carry a `source[]` + confidence, so the
     grounded-numbers contract is preserved end-to-end.
  2. A comparison matrix is built — one column per SOW, one row per decision
     dimension a CEO weighs (annual impact, EBITDA lift, payback, hours freed,
     consultant conviction, deployability grade, key risk/gap).
  3. The matrix renders to a markdown table the report generator embeds, plus a
     machine-readable dict the web SOW-review UI (P4.T2) consumes.

The recommendation pointer ("our pick") is the highest WWOD-pushed candidate that
clears the deployability block threshold — the consultant's honest lead, with the
gaps shown alongside so it is never a blind push (Karpathy human-in-loop).
"""
from __future__ import annotations

import importlib
import json
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Any, Sequence

_wwod = importlib.import_module("engine.sow.wwod_score")
_grade = importlib.import_module("engine.sow.pillar_grade")
_metrics = importlib.import_module("engine.sow.metrics")

# decision dimensions, in the order a CEO weighs them.
ROWS: list[tuple[str, str]] = [
    ("title", "Growth thrust"),
    ("impact_usd", "Annual impact"),
    ("ebitda_uplift_pct", "EBITDA lift"),
    ("payback_months", "Payback"),
    ("impact_hours", "Leadership hours freed / yr"),
    ("wwod_score", "Consultant conviction"),
    ("grade", "Deployability grade"),
    ("confidence", "Evidence confidence"),
    ("key_gap", "Key thing to firm up"),
]


def _attr(obj: Any, name: str, default=None):
    if isinstance(obj, dict):
        return obj.get(name, default)
    return getattr(obj, name, default)


@dataclass
class SBSColumn:
    """One SOW's column in the side-by-side comparison."""
    sow_id: str
    title: str
    objective: str
    impact_usd: float
    impact_hours: float
    confidence: float
    ebitda_uplift_pct: float
    payback_months: float
    wwod_score: float
    wwod_confidence: float
    grade: str
    pillar_aggregate: float
    blockers: list[str] = field(default_factory=list)
    gaps: list[str] = field(default_factory=list)
    key_gap: str = ""
    source: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class SideBySide:
    columns: list[SBSColumn]
    recommended_sow_id: str | None
    rows: list[tuple[str, str]] = field(default_factory=lambda: list(ROWS))

    def to_dict(self) -> dict:
        return {
            "columns": [c.to_dict() for c in self.columns],
            "recommended_sow_id": self.recommended_sow_id,
            "rows": [{"key": k, "label": lbl} for k, lbl in self.rows],
        }


def _format_cell(key: str, col: SBSColumn) -> str:
    """CEO-language formatting per dimension."""
    if key == "title":
        return col.title
    if key == "impact_usd":
        return f"${col.impact_usd:,.0f}/yr"
    if key == "ebitda_uplift_pct":
        return f"+{col.ebitda_uplift_pct:.0f}% EBITDA"
    if key == "payback_months":
        return "—" if col.payback_months in (None, float("inf")) else f"{col.payback_months:.0f} mo"
    if key == "impact_hours":
        return f"{col.impact_hours:.0f} hrs/yr" if col.impact_hours else "—"
    if key == "wwod_score":
        return f"{col.wwod_score:.0%}"
    if key == "grade":
        return col.grade + (" ⚠" if col.blockers else "")
    if key == "confidence":
        return f"{col.confidence:.0%}"
    if key == "key_gap":
        return col.key_gap or "—"
    return str(getattr(col, key, "—"))


def build_columns(
    sows: Sequence[Any],
    baseline: dict,
    *,
    engagement_cost_usd: float | None = None,
) -> list[SBSColumn]:
    """Enrich each SOW candidate with WWOD + pillar grade + metrics -> a column."""
    cost_kw = {} if engagement_cost_usd is None else {"engagement_cost_usd": engagement_cost_usd}
    cols: list[SBSColumn] = []
    for s in sows:
        w = _wwod.score_sow(s)
        g = _grade.grade_sow(s)
        m = _metrics.metrics_for(s, baseline, **cost_kw)
        gaps = list(w.gaps)
        key_gap = (g.blockers[0] if g.blockers else (gaps[0] if gaps else ""))
        cols.append(
            SBSColumn(
                sow_id=_attr(s, "id", "unknown"),
                title=_attr(s, "title", ""),
                objective=_attr(s, "objective", ""),
                impact_usd=float(_attr(s, "impact_usd", 0.0) or 0.0),
                impact_hours=float(_attr(s, "impact_hours", 0.0) or 0.0),
                confidence=float(_attr(s, "confidence", 0.0) or 0.0),
                ebitda_uplift_pct=m.ebitda_uplift_pct,
                payback_months=m.payback_months,
                wwod_score=w.wwod_score,
                wwod_confidence=w.confidence,
                grade=g.grade,
                pillar_aggregate=g.aggregate,
                blockers=list(g.blockers),
                gaps=gaps,
                key_gap=key_gap,
                source=list(_attr(s, "source", []) or []),
            )
        )
    return cols


def _recommend(columns: Sequence[SBSColumn]) -> str | None:
    """The consultant's honest lead: highest WWOD push among deployable (no
    blocking pillar) candidates; falls back to highest WWOD overall if every
    candidate carries a blocker (so we always name a pick, never hide)."""
    if not columns:
        return None
    deployable = [c for c in columns if not c.blockers]
    pool = deployable or list(columns)
    return max(pool, key=lambda c: (c.wwod_score, c.impact_usd)).sow_id


def build_side_by_side(
    sows: Sequence[Any],
    baseline: dict,
    *,
    engagement_cost_usd: float | None = None,
) -> SideBySide:
    cols = build_columns(sows, baseline, engagement_cost_usd=engagement_cost_usd)
    return SideBySide(columns=cols, recommended_sow_id=_recommend(cols))


def render_markdown(sbs: SideBySide) -> str:
    """Render the comparison as a markdown table (embedded by the report)."""
    if not sbs.columns:
        return "_No SOW candidates to compare._"
    header = "| Dimension | " + " | ".join(
        c.title for c in sbs.columns
    ) + " |"
    sep = "|---|" + "|".join(["---"] * len(sbs.columns)) + "|"
    lines = [header, sep]
    for key, label in sbs.rows:
        if key == "title":
            continue  # title is already the column header
        cells = " | ".join(_format_cell(key, c) for c in sbs.columns)
        lines.append(f"| **{label}** | {cells} |")
    out = "\n".join(lines)
    if sbs.recommended_sow_id:
        rec = next((c for c in sbs.columns if c.sow_id == sbs.recommended_sow_id), None)
        if rec:
            out += (
                f"\n\n**Our recommendation: {rec.title}** — strongest consultant "
                f"conviction ({rec.wwod_score:.0%}) at a deployability grade of "
                f"{rec.grade}."
            )
            if rec.gaps:
                out += f" Before committing, confirm: {rec.gaps[0]}"
    return out


def write_artifact(sbs: SideBySide, path: Path | str) -> Path:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(sbs.to_dict(), indent=2, default=str))
    return p


def from_run(
    run_id: str,
    *,
    runs_root: Path | None = None,
    baseline_path: Path | None = None,
) -> SideBySide:
    """End-to-end: load a run's SOW candidates + the tenant baseline -> side-by-side,
    written to runs/{run_id}/presentation/side-by-side.json."""
    repo = Path(__file__).resolve().parents[2]
    runs = runs_root or (repo / "runs")
    cand_path = runs / run_id / "sow" / "sow-candidates.jsonl"
    cands = [json.loads(l) for l in cand_path.read_text().splitlines() if l.strip()]
    if baseline_path is None:
        # default tenant baseline for the synthetic run
        baseline_path = repo / "client" / "snapshots" / "synth-acme-services" / "baseline.json"
    baseline = json.loads(Path(baseline_path).read_text())
    sbs = build_side_by_side(cands, baseline)
    write_artifact(sbs, runs / run_id / "presentation" / "side-by-side.json")
    return sbs


def _main() -> int:
    import argparse

    ap = argparse.ArgumentParser(description="Render a side-by-side SOW comparison for a run")
    ap.add_argument("--run-id", required=True)
    args = ap.parse_args()
    sbs = from_run(args.run_id)
    print(render_markdown(sbs))
    return 0 if sbs.columns else 1


if __name__ == "__main__":
    raise SystemExit(_main())
