"""Adapter for a QuickBooks-like export.

Maps the export into the provider-neutral accounting view of schemas/baseline.json,
then writes the full baseline snapshot to client/snapshots/{tenant_id}/baseline.json.

The input is a QuickBooks-like JSON shape defined by
examples/synthetic-client-a/quickbooks_export.json: flat ProfitAndLoss totals,
Purchases already summed per vendor, and invoices carrying MetaData_FirstContact and
MetaData_ScopeSent. No real QuickBooks file or API response is parsed yet. The
first-contact and scope-sent dates are not QuickBooks fields; they would come from a
CRM. The adapter reads a JSON blob (or a path to one) and calls no API.
scripts/run_synthetic.py is how it runs end to end.
"""
from __future__ import annotations

import hashlib
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

import jsonschema

ROOT = Path(__file__).resolve().parents[2]
SCHEMA_PATH = ROOT / "schemas" / "baseline.json"
ADAPTER_VERSION = "1.0.0"
SCHEMA_VERSION = 1


class QuickBooksAdapter:
    """Read-only mapper from an export dict to the baseline accounting view."""

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
    def _status(inv: dict[str, Any], as_of: str) -> str:
        """Status as of the export's end date, so one export maps the same way every day."""
        if not inv.get("Balance"):
            return "paid"
        due = inv.get("DueDate")
        if due and due < as_of:  # ISO dates compare as strings
            return "overdue"
        return "sent"

    def as_of(self) -> str:
        """The export's end date; today when the export does not name one."""
        period = self.export.get("report_period", {}) or {}
        return period.get("end_date") or datetime.now(timezone.utc).date().isoformat()

    def _map_invoices(self) -> list[dict[str, Any]]:
        as_of = self.as_of()
        out = []
        for inv in self.export.get("Invoices", []) or []:
            out.append({
                "invoice_id": inv.get("Id", ""),
                "customer": inv.get("CustomerRef", ""),
                "amount_usd": float(inv.get("TotalAmt", 0)),
                "balance_usd": float(inv.get("Balance", 0)),
                "issued_at": inv.get("TxnDate"),
                "paid_at": None,  # QBO invoices carry no payment date; it lives on Payment entities
                "first_contact_at": inv.get("MetaData_FirstContact"),
                "scope_sent_at": inv.get("MetaData_ScopeSent"),
                "status": self._status(inv, as_of),
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
        n = (len(self.export.get("Invoices", []) or [])
             + len(self.export.get("Purchases", []) or []))
        return {
            "type": "accounting",
            "system": "QuickBooks",
            "snapshot_at": self.as_of() + "T00:00:00Z",
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
    """Write baseline.json to client/snapshots/{tenant_id}/baseline.json. Returns the path.

    Validates first: tenant_id becomes a directory name, so a bad one must never reach disk.
    """
    errs = validate_baseline(baseline)
    if errs:
        raise ValueError("baseline invalid: " + "; ".join(errs))
    root = snapshots_root or (ROOT / "client" / "snapshots")
    out_dir = root / baseline["tenant_id"]
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / "baseline.json"
    out_path.write_text(json.dumps(baseline, indent=2))
    return out_path


def validate_baseline(baseline: dict[str, Any]) -> list[str]:
    """Validate a baseline against schemas/baseline.json. Returns [] if valid, else errors."""
    with open(SCHEMA_PATH) as f:
        schema = json.load(f)
    validator = jsonschema.Draft7Validator(schema)
    return [f"{'/'.join(map(str, e.path))}: {e.message}"
            for e in validator.iter_errors(baseline)]
