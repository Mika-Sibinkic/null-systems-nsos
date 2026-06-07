"""Monitoring + recurring-diagnostic tier hook (P5.T2, land-and-expand).

The diagnostic is not a one-shot. After a tenant's first run, NSOS re-runs the
diagnostic on a cadence and tracks realized impact against the shipped SOW's
prediction — the recurring tier that turns a one-time diagnostic into a
land-and-expand subscription (the Throughput-pillar "designed for year-1, not
day-1" stance applied to the product, not just the infra).

This module is the cadence + realized-impact-tracking hook that sits on top of the
outcome flywheel (`learning/feedback/outcome_loop.py`):

  - **Re-run cadence** — `next_run_due(last_run_at, cadence_days)` computes when a
    tenant's next diagnostic is due. `due_tenants(...)` returns the tenants whose
    next run has come up, so a scheduler (cron/Inngest, post-MVP) can fire them.
  - **Realized-impact tracking stub** — `record_realized_impact(...)` is the seam
    where an actuals feed (a later QuickBooks re-snapshot diff) writes a
    realization row into the flywheel ledger, closing the predicted-vs-realized
    loop without the operator typing numbers.

Deterministic, offline, dependency-light. The scheduler backend and the actuals
feed are stubbed at the interface — wiring a real durable scheduler in is a config
change, not a rewrite.
"""
from __future__ import annotations

import importlib.util
import json
from dataclasses import dataclass, field, asdict
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Iterable

REPO = Path(__file__).resolve().parents[2]
DEFAULT_REGISTRY = REPO / "learning" / "feedback" / "monitoring-registry.jsonl"
DEFAULT_CADENCE_DAYS = 90  # quarterly re-diagnostic by default


def _load_outcome_loop():
    spec = importlib.util.spec_from_file_location(
        "nsos_outcome_loop_mon", str(REPO / "learning" / "feedback" / "outcome_loop.py")
    )
    mod = importlib.util.module_from_spec(spec)
    import sys
    sys.modules["nsos_outcome_loop_mon"] = mod
    spec.loader.exec_module(mod)
    return mod


def _parse(ts: str) -> datetime:
    return datetime.fromisoformat(ts.replace("Z", "+00:00"))


def _fmt(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


@dataclass
class MonitoringEntry:
    tenant_id: str
    last_run_at: str
    cadence_days: int = DEFAULT_CADENCE_DAYS
    last_run_id: str = ""
    shipped_sow_id: str = ""

    def to_dict(self) -> dict:
        return asdict(self)


def next_run_due(last_run_at: str, cadence_days: int = DEFAULT_CADENCE_DAYS) -> str:
    """ISO timestamp when the next diagnostic is due."""
    return _fmt(_parse(last_run_at) + timedelta(days=cadence_days))


def is_due(entry: MonitoringEntry, *, now: str | None = None) -> bool:
    now_dt = _parse(now) if now else datetime.now(timezone.utc)
    return now_dt >= _parse(next_run_due(entry.last_run_at, entry.cadence_days))


def register_tenant(
    entry: MonitoringEntry, *, registry: Path | None = None
) -> dict:
    """Append a monitoring registration for a tenant (append-only)."""
    r = registry or DEFAULT_REGISTRY
    r.parent.mkdir(parents=True, exist_ok=True)
    row = entry.to_dict()
    with open(r, "a") as f:
        f.write(json.dumps(row, default=str) + "\n")
    return row


def load_registry(registry: Path | None = None) -> list[MonitoringEntry]:
    """Latest entry per tenant (append-only -> last write wins)."""
    r = registry or DEFAULT_REGISTRY
    if not r.exists():
        return []
    latest: dict[str, dict] = {}
    for line in r.read_text().splitlines():
        if line.strip():
            row = json.loads(line)
            latest[row["tenant_id"]] = row
    return [MonitoringEntry(**row) for row in latest.values()]


def due_tenants(
    *, now: str | None = None, registry: Path | None = None
) -> list[MonitoringEntry]:
    """Tenants whose next diagnostic run has come due (for a scheduler to fire)."""
    return [e for e in load_registry(registry) if is_due(e, now=now)]


def record_realized_impact(
    *,
    run_id: str,
    sow_id: str,
    tenant_id: str,
    impact_usd: float,
    impact_hours: float = 0.0,
    ebitda_uplift_pct: float = 0.0,
    source: Iterable[str] | None = None,
    ledger: Path | None = None,
    observed_at: str | None = None,
) -> dict:
    """Realized-impact tracking stub: write a realization row into the flywheel.

    This is the seam where a re-snapshot actuals diff (future) feeds the closed
    loop. For now it forwards to the outcome flywheel's `record_realization` so the
    predicted-vs-realized pairing works end-to-end."""
    ol = _load_outcome_loop()
    return ol.record_realization(
        run_id=run_id,
        sow_id=sow_id,
        tenant_id=tenant_id,
        impact_usd=impact_usd,
        impact_hours=impact_hours,
        ebitda_uplift_pct=ebitda_uplift_pct,
        source=list(source or ["recurring-diagnostic re-snapshot (stub)"]),
        observed_at=observed_at,
        ledger=ledger,
    )


def _main() -> int:
    import argparse

    ap = argparse.ArgumentParser(description="Monitoring / recurring-diagnostic tier")
    ap.add_argument("--due", action="store_true", help="list tenants due for re-run")
    args = ap.parse_args()
    if args.due:
        print(json.dumps([e.to_dict() for e in due_tenants()], indent=2, default=str))
    else:
        print(json.dumps([e.to_dict() for e in load_registry()], indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(_main())
