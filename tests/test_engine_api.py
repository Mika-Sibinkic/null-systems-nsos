"""Tests for engine/api -- the HTTP boundary the web surface calls.

Runs offline with FastAPI's TestClient against the committed synthetic snapshot
(client/snapshots/synth-acme-services). No API keys, no network.
"""
import json
import sys
from pathlib import Path

import pytest
from fastapi import Depends
from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from client.onboarding.auth import issue_token  # noqa: E402
from engine.api.app import create_app, require_live_model  # noqa: E402

TENANT = "synth-acme-services"
TEASER_KEYS = {"id", "headline", "impact_usd", "impact_hours", "evidence", "confidence", "method", "team"}


@pytest.fixture
def client(monkeypatch):
    monkeypatch.delenv("NIM_API_KEY", raising=False)
    monkeypatch.delenv("VINNY_TOKEN_SECRET", raising=False)
    return TestClient(create_app())


def _bearer(tenant: str, scopes=("snapshot:read",)) -> dict:
    return {"authorization": f"Bearer {issue_token(tenant, list(scopes))}"}


# ── /health ───────────────────────────────────────────────────────────────────

def test_health_reports_offline_mode_with_no_keys(client):
    r = client.get("/health")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok"
    assert body["service"] == "nsos-engine"
    assert body["model_mode"] == "offline-deterministic"
    assert body["token_secret"] == "dev-only"


def test_health_reports_live_mode_when_model_key_set(monkeypatch):
    monkeypatch.setenv("NIM_API_KEY", "set-for-test-only")
    monkeypatch.setenv("VINNY_TOKEN_SECRET", "set-for-test-only")
    r = TestClient(create_app()).get("/health")
    assert r.json()["model_mode"] == "live"
    assert r.json()["token_secret"] == "configured"


# ── /teaser against the synthetic client ──────────────────────────────────────

def test_teaser_returns_engine_finding_for_synthetic_tenant(client):
    r = client.get("/teaser", params={"tenant": TENANT}, headers=_bearer(TENANT))
    assert r.status_code == 200, r.text
    f = r.json()
    assert set(f) == TEASER_KEYS
    assert f["team"] == "teaser"
    assert f["impact_usd"] > 0
    assert f["evidence"]
    assert 0.0 < f["confidence"] <= 1.0
    assert f["method"] in {"scope_cycle_time_leak", "vendor_concentration_vs_benchmark"}


def test_teaser_matches_direct_engine_call(client):
    """The HTTP boundary must not reshape or re-mint any number."""
    from engine.teaser.teaser import from_snapshot
    direct = from_snapshot(TENANT).to_finding()
    via_http = client.get("/teaser", params={"tenant": TENANT}, headers=_bearer(TENANT)).json()
    assert via_http == json.loads(json.dumps(direct))


def test_teaser_without_token_is_401_json(client):
    r = client.get("/teaser", params={"tenant": TENANT})
    assert r.status_code == 401
    assert r.json() == {"error": "unauthorized"}


def test_teaser_rejects_token_for_other_tenant(client):
    r = client.get("/teaser", params={"tenant": TENANT}, headers=_bearer("some-other-tenant"))
    assert r.status_code == 401
    assert r.json() == {"error": "unauthorized"}


def test_teaser_rejects_token_without_snapshot_scope(client):
    r = client.get("/teaser", params={"tenant": TENANT},
                   headers=_bearer(TENANT, scopes=("onboarding:read",)))
    assert r.status_code == 401


def test_teaser_unknown_tenant_is_404_json(client):
    r = client.get("/teaser", params={"tenant": "no-such-tenant"}, headers=_bearer("no-such-tenant"))
    assert r.status_code == 404
    assert "no snapshot" in r.json()["error"]


def test_teaser_snapshot_without_accounting_is_422_json(tmp_path, monkeypatch):
    monkeypatch.delenv("VINNY_TOKEN_SECRET", raising=False)
    (tmp_path / "t1").mkdir()
    (tmp_path / "t1" / "baseline.json").write_text(json.dumps({"firm": {}}))
    c = TestClient(create_app(snapshots_root=tmp_path))
    r = c.get("/teaser", params={"tenant": "t1"}, headers=_bearer("t1"))
    assert r.status_code == 422
    assert "accounting" in r.json()["error"]


# ── /dev/scoped-token ─────────────────────────────────────────────────────────

def test_dev_token_mints_a_token_that_authorizes_teaser(client):
    r = client.post("/dev/scoped-token", json={"tenant_id": TENANT})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["tenant_id"] == TENANT
    assert "snapshot:read" in body["scopes"]
    assert body["expires_in"] == 900
    r2 = client.get("/teaser", params={"tenant": TENANT},
                    headers={"authorization": f"Bearer {body['token']}"})
    assert r2.status_code == 200


def test_dev_token_is_absent_when_production_secret_configured(monkeypatch):
    monkeypatch.setenv("VINNY_TOKEN_SECRET", "set-for-test-only")
    r = TestClient(create_app()).post("/dev/scoped-token", json={"tenant_id": TENANT})
    assert r.status_code == 404
    assert r.json() == {"error": "not found"}


# ── fail-closed when a live model is required ─────────────────────────────────

def _app_with_live_route(app):
    @app.get("/_test/needs-model", dependencies=[Depends(require_live_model)])
    def needs_model():
        return {"ok": True}
    return app


def test_live_model_route_fails_closed_without_key(monkeypatch):
    monkeypatch.delenv("NIM_API_KEY", raising=False)
    c = TestClient(_app_with_live_route(create_app()))
    r = c.get("/_test/needs-model")
    assert r.status_code == 503
    assert r.json() == {"error": "live model required but NIM_API_KEY is not configured"}


def test_live_model_route_passes_with_key(monkeypatch):
    monkeypatch.setenv("NIM_API_KEY", "set-for-test-only")
    c = TestClient(_app_with_live_route(create_app()))
    assert c.get("/_test/needs-model").status_code == 200
