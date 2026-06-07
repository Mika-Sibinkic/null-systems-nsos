"""Outcome flywheel — predicted vs realized per shipped SOW (P5.T1).

The moat. When a SOW ships as an FDE engagement, NSOS records what it *predicted*
(the quantified target from the handoff packet). When the outcome lands, it
records what was *realized*. The delta between the two is the signal that
compounds diagnostic accuracy over time — it feeds the eval set so the next
diagnostic is calibrated against real outcomes, not just internal scoring.

Design (deterministic, offline, append-only):

  - **Append-only ledger** (`learning/feedback/outcome-ledger.jsonl`) — one row
    per event: a `prediction` row at ship, a `realization` row when the outcome
    is observed. Both carry `run_id` + `sow_id` so they pair up. Append-only is
    the compliance-pillar contract: who predicted/realized what, when, with what
    source — answerable from the ledger alone, no code change.
  - **Prediction is lifted from the handoff packet** — no new number minted; the
    predicted target descends from the same source[]-traced figures the operator
    chose on. The grounded-numbers contract holds at the flywheel boundary too.
  - **Delta + accuracy** are computed from a paired prediction+realization. The
    accuracy ratio (realized / predicted, clamped) becomes an eval-set datapoint:
    a calibration signal the eval harness can score future diagnostics against.

No LLM. Reproducible. The flywheel is the closed loop's measurement layer; the RL
update that consumes these deltas is downstream (post-MVP).
"""
from __future__ import annotations

import json
import subprocess
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Any, Iterable

REPO = Path(__file__).resolve().parents[2]
DEFAULT_LEDGER = REPO / "learning" / "feedback" / "outcome-ledger.jsonl"
DEFAULT_EVALSET = REPO / "learning" / "feedback" / "outcome-evalset.jsonl"


def _utc_now() -> str:
    return subprocess.check_output(["date", "-u", "+%FT%TZ"]).decode().strip()


def _attr(obj: Any, name: str, default=None):
    if isinstance(obj, dict):
        return obj.get(name, default)
    return getattr(obj, name, default)


def _append(path: Path, obj: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "a") as f:
        f.write(json.dumps(obj, default=str) + "\n")


def record_prediction(
    packet: Any,
    *,
    ledger: Path | None = None,
    ts: str | None = None,
) -> dict:
    """Write a prediction row from an FDE handoff packet (or an equivalent dict).

    `packet` may be a `presentation.handoff.packet.HandoffPacket` or any object/dict
    exposing run_id, sow_id (selected_sow_id), tenant_id, the predicted metrics, and
    source[]."""
    sow_id = _attr(packet, "selected_sow_id", None) or _attr(packet, "sow_id", "unknown")
    predicted = {
        "impact_usd": float(_attr(packet, "impact_usd", 0.0) or 0.0),
        "impact_hours": float(_attr(packet, "impact_hours", 0.0) or 0.0),
        "ebitda_uplift_pct": float(_attr(packet, "ebitda_uplift_pct", 0.0) or 0.0),
        "payback_months": _attr(packet, "payback_months", None),
        "confidence": float(_attr(packet, "confidence", 0.0) or 0.0),
    }
    row = {
        "record_type": "prediction",
        "run_id": _attr(packet, "run_id", "unknown"),
        "sow_id": sow_id,
        "tenant_id": _attr(packet, "tenant_id", "unknown"),
        "ts": ts or _utc_now(),
        "predicted": predicted,
        "source": list(_attr(packet, "source", []) or []),
    }
    _append(ledger or DEFAULT_LEDGER, row)
    return row


def record_realization(
    *,
    run_id: str,
    sow_id: str,
    tenant_id: str,
    impact_usd: float,
    impact_hours: float = 0.0,
    ebitda_uplift_pct: float = 0.0,
    source: Iterable[str] | None = None,
    observed_at: str | None = None,
    ledger: Path | None = None,
    ts: str | None = None,
) -> dict:
    """Write a realization row when the outcome of a shipped SOW is observed."""
    row = {
        "record_type": "realization",
        "run_id": run_id,
        "sow_id": sow_id,
        "tenant_id": tenant_id,
        "ts": ts or _utc_now(),
        "realized": {
            "impact_usd": float(impact_usd),
            "impact_hours": float(impact_hours),
            "ebitda_uplift_pct": float(ebitda_uplift_pct),
            "observed_at": observed_at or (ts or _utc_now()),
        },
        "source": list(source or []),
    }
    _append(ledger or DEFAULT_LEDGER, row)
    return row


def load_ledger(ledger: Path | None = None) -> list[dict]:
    p = ledger or DEFAULT_LEDGER
    if not p.exists():
        return []
    return [json.loads(line) for line in p.read_text().splitlines() if line.strip()]


@dataclass
class OutcomeDelta:
    run_id: str
    sow_id: str
    tenant_id: str
    predicted_usd: float
    realized_usd: float
    delta_usd: float                 # realized - predicted
    accuracy_ratio: float            # realized / predicted, clamped to [0, 2]
    predicted_ebitda_pct: float = 0.0
    realized_ebitda_pct: float = 0.0
    source: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)


def _clamp(x: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, x))


def pair_outcomes(ledger: Path | None = None) -> list[OutcomeDelta]:
    """Pair each (run_id, sow_id) prediction with its latest realization -> deltas.

    Predictions without a realization yet are *open* and excluded (they have no
    measurable delta). A prediction with multiple realizations uses the latest."""
    rows = load_ledger(ledger)
    preds: dict[tuple[str, str], dict] = {}
    reals: dict[tuple[str, str], dict] = {}
    for r in rows:
        key = (r.get("run_id"), r.get("sow_id"))
        if r.get("record_type") == "prediction":
            preds[key] = r  # latest prediction wins
        elif r.get("record_type") == "realization":
            reals[key] = r  # latest realization wins

    out: list[OutcomeDelta] = []
    for key, pred in preds.items():
        real = reals.get(key)
        if not real:
            continue
        p_usd = float(pred.get("predicted", {}).get("impact_usd", 0.0) or 0.0)
        r_usd = float(real.get("realized", {}).get("impact_usd", 0.0) or 0.0)
        ratio = _clamp(r_usd / p_usd, 0.0, 2.0) if p_usd > 0 else 0.0
        out.append(
            OutcomeDelta(
                run_id=key[0],
                sow_id=key[1],
                tenant_id=pred.get("tenant_id", "unknown"),
                predicted_usd=round(p_usd, 2),
                realized_usd=round(r_usd, 2),
                delta_usd=round(r_usd - p_usd, 2),
                accuracy_ratio=round(ratio, 4),
                predicted_ebitda_pct=float(pred.get("predicted", {}).get("ebitda_uplift_pct", 0.0) or 0.0),
                realized_ebitda_pct=float(real.get("realized", {}).get("ebitda_uplift_pct", 0.0) or 0.0),
                source=list(pred.get("source", []) or []) + list(real.get("source", []) or []),
            )
        )
    return out


def export_evalset(
    *,
    ledger: Path | None = None,
    evalset: Path | None = None,
) -> Path:
    """Materialize paired outcomes as eval-set datapoints (calibration signal the
    eval harness scores future diagnostics against)."""
    deltas = pair_outcomes(ledger)
    out = evalset or DEFAULT_EVALSET
    out.parent.mkdir(parents=True, exist_ok=True)
    body = "\n".join(json.dumps(d.to_dict(), default=str) for d in deltas)
    out.write_text(body + ("\n" if deltas else ""))
    return out


def calibration_summary(ledger: Path | None = None) -> dict:
    """Aggregate accuracy across all paired outcomes — the flywheel's headline."""
    deltas = pair_outcomes(ledger)
    if not deltas:
        return {"paired": 0, "mean_accuracy_ratio": None, "open_predictions": _open_count(ledger)}
    ratios = [d.accuracy_ratio for d in deltas]
    return {
        "paired": len(deltas),
        "mean_accuracy_ratio": round(sum(ratios) / len(ratios), 4),
        "total_predicted_usd": round(sum(d.predicted_usd for d in deltas), 2),
        "total_realized_usd": round(sum(d.realized_usd for d in deltas), 2),
        "open_predictions": _open_count(ledger),
    }


def _open_count(ledger: Path | None = None) -> int:
    rows = load_ledger(ledger)
    preds = {(r["run_id"], r["sow_id"]) for r in rows if r.get("record_type") == "prediction"}
    reals = {(r["run_id"], r["sow_id"]) for r in rows if r.get("record_type") == "realization"}
    return len(preds - reals)


def _main() -> int:
    import argparse

    ap = argparse.ArgumentParser(description="Outcome flywheel — predicted vs realized")
    ap.add_argument("--summary", action="store_true", help="print calibration summary")
    ap.add_argument("--export-evalset", action="store_true")
    args = ap.parse_args()
    if args.export_evalset:
        p = export_evalset()
        print(f"wrote eval set -> {p}")
    print(json.dumps(calibration_summary(), indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(_main())
