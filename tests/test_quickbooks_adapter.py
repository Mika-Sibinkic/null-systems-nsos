"""Tests for client/adapters/quickbooks.py — read-only QB export -> baseline.json."""
import json
from pathlib import Path

from client.adapters.quickbooks import (
    QuickBooksAdapter,
    build_baseline,
    validate_baseline,
    write_baseline,
)

ROOT = Path(__file__).resolve().parents[1]


EXPORT_PATH = ROOT / "examples" / "synthetic-client-a" / "quickbooks_export.json"
FIRM_PATH = ROOT / "examples" / "synthetic-client-a" / "firm.json"


def _export():
    with open(EXPORT_PATH) as f:
        return json.load(f)


def _firm():
    with open(FIRM_PATH) as f:
        return json.load(f)


def test_export_fixture_exists():
    assert EXPORT_PATH.exists(), "synthetic QB export fixture missing"


def test_accounting_view_maps_pnl_and_vendors():
    adapter = QuickBooksAdapter(_export())
    view = adapter.accounting_view()
    assert view["currency"] == "USD"
    # P&L lines carried through
    assert view["profit_and_loss"]["Expense:CloudInfra"] == 84000.0
    assert view["profit_and_loss"]["TotalIncome"] == 28000000.0
    # vendors mapped with provenance
    vendors = {v["vendor"]: v for v in view["expenses_by_vendor"]}
    assert "CloudProvider X" in vendors
    assert vendors["CloudProvider X"]["amount_usd"] == 84000.0
    assert vendors["CloudProvider X"]["txn_count"] == 12


def test_invoice_cycle_time_provenance_preserved():
    adapter = QuickBooksAdapter(_export())
    invoices = adapter.accounting_view()["invoices"]
    assert len(invoices) == 7
    inv = {i["invoice_id"]: i for i in invoices}["INV-1001"]
    # first_contact -> scope_sent provenance preserved for time-leak findings
    assert inv["first_contact_at"] == "2025-05-12"
    assert inv["scope_sent_at"] == "2025-05-30"
    assert inv["amount_usd"] == 240000.0


def test_invoice_status_derived_from_balance():
    adapter = QuickBooksAdapter(_export())
    inv = {i["invoice_id"]: i for i in adapter.accounting_view()["invoices"]}
    assert inv["INV-1001"]["status"] == "paid"   # Balance 0
    # INV-1003 has an open balance with a 2025 due date -> overdue
    assert inv["INV-1003"]["status"] == "overdue"
    assert inv["INV-1003"]["paid_at"] is None


def test_build_baseline_is_valid_against_schema():
    baseline = build_baseline(_export(), "synth-acme-services", firm=_firm())
    errs = validate_baseline(baseline)
    assert errs == [], f"baseline failed schema validation: {errs}"
    assert baseline["tenant_id"] == "synth-acme-services"
    assert baseline["schema_version"] == 1
    assert baseline["sources"][0]["system"] == "QuickBooks"
    assert baseline["sources"][0]["record_count"] == 12  # 7 invoices + 5 purchases
    assert baseline["firm"]["firm_name"] == "Acme Services"


def test_provenance_sha_is_deterministic():
    b1 = build_baseline(_export(), "t", firm=None)
    b2 = build_baseline(_export(), "t", firm=None)
    assert b1["provenance"]["source_export_sha256"] == b2["provenance"]["source_export_sha256"]
    assert b1["provenance"]["adapter"] == "quickbooks"


def test_write_baseline_roundtrips(tmp_path):
    baseline = build_baseline(_export(), "synth-acme-services", firm=_firm())
    out = write_baseline(baseline, snapshots_root=tmp_path)
    assert out.exists()
    loaded = json.loads(out.read_text())
    assert loaded["tenant_id"] == "synth-acme-services"


def test_adapter_rejects_non_dict_export():
    import pytest
    with pytest.raises(TypeError):
        QuickBooksAdapter([1, 2, 3])


# ── overdue AR is computed as of the export, from open balances ───────────────

def _lens_export():
    """One invoice not yet due (2099) and one past due with a $1,000 open balance."""
    return {
        "report_period": {"start_date": "2025-05-01", "end_date": "2026-04-30"},
        "Invoices": [
            {"Id": "A", "CustomerRef": "Future Co", "TotalAmt": 50000, "Balance": 50000,
             "TxnDate": "2026-04-01", "DueDate": "2099-01-01"},
            {"Id": "B", "CustomerRef": "Past Co", "TotalAmt": 100000, "Balance": 1000,
             "TxnDate": "2025-12-01", "DueDate": "2026-01-01"},
        ],
    }


def test_ar_overdue_counts_only_overdue_open_balance():
    import engine.meta_levels.financial.findings as findings_mod
    a = findings_mod.a_ar_overdue(build_baseline(_lens_export(), "lens"))
    assert a["overdue_count"] == 1
    assert a["exposure_usd"] == 1000.0


def test_status_is_as_of_export_end_date_not_today():
    export = _lens_export()
    export["Invoices"][0]["DueDate"] = "2026-06-01"  # after the export, before today
    inv = {i["invoice_id"]: i for i in QuickBooksAdapter(export).accounting_view()["invoices"]}
    assert inv["A"]["status"] == "sent"
    assert inv["B"]["status"] == "overdue"
    assert inv["B"]["balance_usd"] == 1000.0


def test_paid_invoice_has_no_invented_paid_date():
    inv = {i["invoice_id"]: i for i in QuickBooksAdapter(_export()).accounting_view()["invoices"]}
    assert inv["INV-1001"]["status"] == "paid"
    assert inv["INV-1001"]["paid_at"] is None  # the export carries no payment date


def test_write_baseline_rejects_path_traversal_tenant(tmp_path):
    import pytest
    for bad in ("../escaped", "synth\n"):
        baseline = build_baseline(_export(), bad)
        with pytest.raises(ValueError):
            write_baseline(baseline, snapshots_root=tmp_path / "snapshots")
    assert not (tmp_path / "escaped").exists()
    assert not (tmp_path / "snapshots").exists()
