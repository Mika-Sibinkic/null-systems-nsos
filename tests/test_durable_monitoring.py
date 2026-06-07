"""Tests for durable execution + monitoring/recurring tier (P5.T2)."""
import importlib.util
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def _load(name: str, rel: str):
    spec = importlib.util.spec_from_file_location(name, str(ROOT / rel))
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


durable = _load("nsos_durable", "engine/run/durable.py")
monitoring = _load("nsos_monitoring", "learning/feedback/monitoring.py")


# ── durable execution ─────────────────────────────────────────────────────────

def test_run_once_idempotent_on_run_id(tmp_path):
    j = tmp_path / "journal.jsonl"
    calls = {"n": 0}

    def fn():
        calls["n"] += 1
        return {"sows": 3}

    r1 = durable.run_once("run-x", fn, journal=j)
    r2 = durable.run_once("run-x", fn, journal=j)
    assert r1.status == "completed"
    assert r2.status == "replayed"
    assert r2.result == {"sows": 3}
    assert calls["n"] == 1, "fn must run at most once per run_id"


def test_with_retry_succeeds_after_transient_failures(tmp_path):
    j = tmp_path / "journal.jsonl"
    flap = {"n": 0}

    def flaky():
        flap["n"] += 1
        if flap["n"] < 3:
            raise RuntimeError("transient")
        return "ok"

    result, attempts = durable.with_retry(flaky, run_id="r", journal=j, sleep=lambda s: None)
    assert result == "ok"
    assert attempts == 3


def test_with_retry_raises_after_exhaustion(tmp_path):
    j = tmp_path / "journal.jsonl"

    def always_fails():
        raise RuntimeError("nope")

    try:
        durable.with_retry(always_fails, run_id="r", journal=j, sleep=lambda s: None)
    except durable.RetryExhausted:
        rows = [json.loads(l) for l in j.read_text().splitlines() if l.strip()]
        # no silent failure: exhaustion is journaled
        assert any(r["event"] == "retry_exhausted" for r in rows)
        return
    assert False, "expected RetryExhausted"


def test_backoff_schedule_matches_manifest():
    manifest = json.loads((ROOT / "build" / "manifest.json").read_text())
    cascade = manifest["recursive_context"]["cascade"]
    assert durable.BACKOFF_SECONDS == cascade["backoff_seconds"]
    assert durable.MAX_ATTEMPTS == cascade["max_retries"]


def test_journal_records_attempts(tmp_path):
    j = tmp_path / "journal.jsonl"
    durable.run_once("run-y", lambda: 42, journal=j)
    rows = [json.loads(l) for l in j.read_text().splitlines() if l.strip()]
    assert any(r["event"] == "start" for r in rows)
    assert any(r["event"] == "completed" and r["result"] == 42 for r in rows)


# ── monitoring / recurring tier ───────────────────────────────────────────────

def test_next_run_due_adds_cadence():
    assert monitoring.next_run_due("2026-01-01T00:00:00Z", 90) == "2026-04-01T00:00:00Z"


def test_is_due_true_after_cadence():
    e = monitoring.MonitoringEntry(tenant_id="t1", last_run_at="2026-01-01T00:00:00Z", cadence_days=90)
    assert monitoring.is_due(e, now="2026-06-07T00:00:00Z") is True
    assert monitoring.is_due(e, now="2026-02-01T00:00:00Z") is False


def test_registry_latest_per_tenant(tmp_path):
    reg = tmp_path / "registry.jsonl"
    monitoring.register_tenant(
        monitoring.MonitoringEntry(tenant_id="t1", last_run_at="2026-01-01T00:00:00Z"),
        registry=reg,
    )
    monitoring.register_tenant(
        monitoring.MonitoringEntry(tenant_id="t1", last_run_at="2026-04-01T00:00:00Z"),
        registry=reg,
    )
    entries = monitoring.load_registry(reg)
    assert len(entries) == 1
    assert entries[0].last_run_at == "2026-04-01T00:00:00Z"


def test_due_tenants_filters(tmp_path):
    reg = tmp_path / "registry.jsonl"
    monitoring.register_tenant(
        monitoring.MonitoringEntry(tenant_id="due", last_run_at="2026-01-01T00:00:00Z", cadence_days=90),
        registry=reg,
    )
    monitoring.register_tenant(
        monitoring.MonitoringEntry(tenant_id="fresh", last_run_at="2026-06-01T00:00:00Z", cadence_days=90),
        registry=reg,
    )
    due = monitoring.due_tenants(now="2026-06-07T00:00:00Z", registry=reg)
    assert {e.tenant_id for e in due} == {"due"}


def test_record_realized_impact_writes_realization(tmp_path):
    led = tmp_path / "ledger.jsonl"
    row = monitoring.record_realized_impact(
        run_id="r1", sow_id="sow-a", tenant_id="t1",
        impact_usd=750_000, source=["re-snapshot diff"], ledger=led,
        observed_at="2026-06-07T00:00:00Z",
    )
    assert row["record_type"] == "realization"
    assert row["realized"]["impact_usd"] == 750_000
    assert led.exists()
