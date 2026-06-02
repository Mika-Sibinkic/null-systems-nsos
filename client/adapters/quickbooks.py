"""QuickBooks read-only adapter.

Maps a QuickBooks Online export (Reports + Invoice + Purchase entities) into the
provider-neutral accounting view of schemas/baseline.json, then writes the full
baseline snapshot to client/snapshots/{tenant_id}/baseline.json.

Read-only by contract: the adapter accepts an already-exported JSON blob (or a path
to one). It never calls a mutating QB API. In production the export is fetched by a
server-side connector holding the QB OAuth token (see client/onboarding/auth.py); the
web surface never sees that token. Here we accept the export directly so the mapping
logic is unit-testable offline.

CLI:
  python3 -m client.adapters.quickbooks \
      --export examples/synthetic-client-a/quickbooks_export.json \
      --tenant synth-acme-services \
      --firm examples/synthetic-client-a/firm.json
"""
from __future__ import annotations

import hashlib
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

ROOT = Path(__file__).resolve().parents[2]
SCHEMA_PATH = ROOT / "schemas" / "baseline.json"
ADAPTER_VERSION = "1.0.0"
SCHEMA_VERSION = 1


class QuickBooksAdapter:
    """Read-only mapper from a QBO export dict to the baseline accounting view."""

    def __init__(self, export: dict[str, Any]):
        if not isinstance(export, dict):
            raise TypeError("QuickBooks export must be a dict")
        self.export = export

    @classmethod
    def from_path(cls, path: str | os.PathLike) -> "QuickBooksAdapter":
        with open(path) as f:
            return cls(json.load(f))

    # ── mapping ──────────────────────────────────────────────────────────────

    def _map_pnl(self) -> dict[str, float]:
        pnl = self.export.get("ProfitAndLoss", {}) or {}
        lines = dict(pnl.get("lines", {}) or {})
        for k in ("TotalIncome", "GrossProfit", "TotalExpenses", "NetIncome",
                  "TotalCostOfGoodsSold"):
            if k in pnl:
                lines[k] = pnl[k]
        return {k: float(v) for k, v in lines.items()}

    def _map_vendors(self) -> list[dict[str, Any]]:
        out = []
        for p in self.export.get("Purchases", []) or []:
            out.append({
                "vendor": p.get("vendor", "unknown"),
                "amount_usd": float(p.get("total", 0)),
                "category": p.get("account", ""),
                "txn_count": int(p.get("txn_count", 0)),
            })
        return out

    @staticmethod
    def _status(inv: dict[str, Any]) -> str:
        bal = inv.get("Balance", 0)
        if bal and bal > 0:
            due = inv.get("DueDate")
            if due:
                try:
                    if datetime.fromisoformat(due).date() < datetime.now(timezone.utc).date():
                        return "overdue"
                except ValueError:
                    pass
            return "sent"
        return "paid"

    def _map_invoices(self) -> list[dict[str, Any]]:
        out = []
        for inv in self.export.get("Invoices", []) or []:
            out.append({
                "invoice_id": inv.get("Id", ""),
                "customer": inv.get("CustomerRef", ""),
                "amount_usd": float(inv.get("TotalAmt", 0)),
                "issued_at": inv.get("TxnDate"),
                "paid_at": inv.get("TxnDate") if self._status(inv) == "paid" else None,
                "first_contact_at": inv.get("MetaData_FirstContact"),
                "scope_sent_at": inv.get("MetaData_ScopeSent"),
                "status": self._status(inv),
            })
        return out

    def accounting_view(self) -> dict[str, Any]:
        period = self.export.get("report_period", {}) or {}
        return {
            "currency": self.export.get("currency", "USD"),
            "period_start": period.get("start_date"),
            "period_end": period.get("end_date"),
            "profit_and_loss": self._map_pnl(),
            "expenses_by_vendor": self._map_vendors(),
            "invoices": self._map_invoices(),
        }

    def source_descriptor(self) -> dict[str, Any]:
        period = self.export.get("report_period", {}) or {}
        n = (len(self.export.get("Invoices", []) or [])
             + len(self.export.get("Purchases", []) or []))
        return {
            "type": "accounting",
            "system": "QuickBooks",
            "snapshot_at": (period.get("end_date") or
                            datetime.now(timezone.utc).date().isoformat()) + "T00:00:00Z",
            "record_count": n,
        }


def _export_sha256(export: dict[str, Any]) -> str:
    blob = json.dumps(export, sort_keys=True).encode()
    return hashlib.sha256(blob).hexdigest()


def build_baseline(
    export: dict[str, Any],
    tenant_id: str,
    *,
    firm: Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
    """Assemble a full baseline snapshot dict from a QB export (+ optional firm context)."""
    adapter = QuickBooksAdapter(export)
    baseline: dict[str, Any] = {
        "tenant_id": tenant_id,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "schema_version": SCHEMA_VERSION,
        "sources": [adapter.source_descriptor()],
        "accounting": adapter.accounting_view(),
        "provenance": {
            "adapter": "quickbooks",
            "adapter_version": ADAPTER_VERSION,
            "source_export_sha256": _export_sha256(export),
        },
    }
    if firm:
        baseline["firm"] = {
            "firm_name": firm.get("firm_name"),
            "industry": firm.get("industry"),
            "employees": firm.get("employees"),
            "annual_revenue_usd": firm.get("annual_revenue_usd"),
            "stated_objectives": firm.get("stated_objectives", []),
            "known_baseline": firm.get("known_baseline", []),
        }
    return baseline


def write_baseline(baseline: dict[str, Any], *, snapshots_root: Optional[Path] = None) -> Path:
    """Write baseline.json to client/snapshots/{tenant_id}/baseline.json. Returns the path."""
    root = snapshots_root or (ROOT / "client" / "snapshots")
    out_dir = root / baseline["tenant_id"]
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / "baseline.json"
    out_path.write_text(json.dumps(baseline, indent=2))
    return out_path


def validate_baseline(baseline: dict[str, Any]) -> list[str]:
    """Validate a baseline against schemas/baseline.json. Returns [] if valid, else errors.

    Uses jsonschema if available; otherwise a minimal required-keys check so the
    adapter never hard-depends on an un-lifted package (import_sweep stays green).
    """
    try:
        import jsonschema  # type: ignore
        with open(SCHEMA_PATH) as f:
            schema = json.load(f)
        validator = jsonschema.Draft7Validator(schema)
        return [f"{'/'.join(map(str, e.path))}: {e.message}"
                for e in validator.iter_errors(baseline)]
    except ImportError:
        errs = []
        for k in ("tenant_id", "generated_at", "schema_version", "sources"):
            if k not in baseline:
                errs.append(f"missing required key: {k}")
        if not isinstance(baseline.get("sources"), list) or not baseline["sources"]:
            errs.append("sources must be a non-empty array")
        return errs


def _main() -> int:
    import argparse
    p = argparse.ArgumentParser(description="QuickBooks read-only adapter -> baseline.json")
    p.add_argument("--export", required=True, help="Path to a QuickBooks export JSON")
    p.add_argument("--tenant", required=True, help="tenant_id")
    p.add_argument("--firm", help="Optional firm.json for firm-level context")
    p.add_argument("--out-root", help="Override snapshots root (default client/snapshots)")
    args = p.parse_args()

    with open(args.export) as f:
        export = json.load(f)
    firm = None
    if args.firm:
        with open(args.firm) as f:
            firm = json.load(f)
    baseline = build_baseline(export, args.tenant, firm=firm)
    errs = validate_baseline(baseline)
    if errs:
        print("baseline INVALID:")
        for e in errs:
            print(f"  ! {e}")
        return 1
    out = write_baseline(baseline, snapshots_root=Path(args.out_root) if args.out_root else None)
    print(f"baseline written + valid: {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(_main())
