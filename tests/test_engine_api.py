"""Tests for engine/api -- the HTTP boundary the web surface calls.

Runs offline with FastAPI's TestClient against the committed synthetic snapshot
(client/snapshots/synth-acme-services). No API keys, no network.
"""
import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from client.onboarding.auth import issue_token
from engine.api.app import create_app

ROOT = Path(__file__).resolve().parents[1]


TENANT = "synth-acme-services"
TEASER_KEYS = {"id", "headline", "impact_usd", "impact_hours", "evidence", "confidence", "method", "team"}


LOCAL = ("127.0.0.1", 50000)  # in dev mode the app only answers loopback callers


@pytest.fixture
def client(monkeypatch):
    monkeypatch.delenv("NIM_API_KEY", raising=False)
    monkeypatch.delenv("VINNY_TOKEN_SECRET", raising=False)
    return TestClient(create_app(), client=LOCAL)


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
    assert f["method"] == "scope_cycle_time_leak"


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
    c = TestClient(create_app(snapshots_root=tmp_path), client=LOCAL)
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


# ── trust boundary: tenant ids, malformed tokens, validation errors ───────────

def _forged_bearer(tenant: str) -> dict:
    """A token signed with the dev secret but carrying a tenant issue_token refuses."""
    import base64, hashlib, hmac
    from client.onboarding.auth import _DEV_SECRET
    claims = {"tenant_id": tenant, "scopes": ["snapshot:read"], "iat": 0, "exp": 2**40}
    payload = base64.urlsafe_b64encode(json.dumps(claims).encode()).rstrip(b"=").decode()
    sig = base64.urlsafe_b64encode(
        hmac.new(_DEV_SECRET.encode(), payload.encode(), hashlib.sha256).digest()
    ).rstrip(b"=").decode()
    return {"authorization": f"Bearer {payload}.{sig}"}


@pytest.mark.parametrize("bad", ["/tmp/x", "../../../../tmp/x"])
def test_path_like_tenant_is_refused_at_mint_and_at_teaser(client, bad):
    r = client.post("/dev/scoped-token", json={"tenant_id": bad})
    assert r.status_code == 422
    assert "error" in r.json()
    r = client.get("/teaser", params={"tenant": bad}, headers=_forged_bearer(bad))
    assert r.status_code == 401
    assert r.json() == {"error": "unauthorized"}


def test_non_ascii_bearer_is_401_json(client):
    r = client.get("/teaser", params={"tenant": TENANT},
                   headers=[(b"authorization", b"Bearer a.\xc3\xa9")])
    assert r.status_code == 401
    assert r.json() == {"error": "unauthorized"}


def test_missing_tenant_query_is_422_json(client):
    r = client.get("/teaser", headers=_bearer(TENANT))
    assert r.status_code == 422
    assert set(r.json()) == {"error"}


def test_json_array_baseline_is_422_json(tmp_path, monkeypatch):
    monkeypatch.delenv("VINNY_TOKEN_SECRET", raising=False)
    (tmp_path / "t1").mkdir()
    (tmp_path / "t1" / "baseline.json").write_text("[]")
    r = TestClient(create_app(snapshots_root=tmp_path), client=LOCAL).get(
        "/teaser", params={"tenant": "t1"}, headers=_bearer("t1"))
    assert r.status_code == 422
    assert set(r.json()) == {"error"}


def test_tenant_path_that_is_a_file_is_404_json(tmp_path, monkeypatch):
    monkeypatch.delenv("VINNY_TOKEN_SECRET", raising=False)
    (tmp_path / "t1").write_text("not a directory")
    r = TestClient(create_app(snapshots_root=tmp_path), client=LOCAL).get(
        "/teaser", params={"tenant": "t1"}, headers=_bearer("t1"))
    assert r.status_code == 404
    assert set(r.json()) == {"error"}


def test_empty_token_secret_is_dev_only_and_signs_with_a_real_key(monkeypatch):
    from client.onboarding import auth
    monkeypatch.setenv("VINNY_TOKEN_SECRET", "")
    c = TestClient(create_app(), client=LOCAL)
    assert c.get("/health").json()["token_secret"] == "dev-only"
    assert auth._secret() == auth._DEV_SECRET.encode()
    assert c.post("/dev/scoped-token", json={"tenant_id": TENANT}).status_code == 200


@pytest.mark.parametrize("caller", [("10.0.0.237", 50000), ("testclient", 50000)])
def test_dev_mode_answers_no_non_loopback_caller(monkeypatch, caller):
    """`uvicorn engine.api.app:app --host 0.0.0.0` skips the launcher check; the app holds.

    The dev secret is public, so a forged token must not reach /teaser either."""
    monkeypatch.delenv("VINNY_TOKEN_SECRET", raising=False)
    c = TestClient(create_app(), client=caller)
    r = c.post("/dev/scoped-token", json={"tenant_id": TENANT})
    assert r.status_code == 404
    assert "token" not in r.json()
    r = c.get("/teaser", params={"tenant": TENANT}, headers=_bearer(TENANT))
    assert r.status_code == 404


def test_configured_secret_serves_non_loopback_callers(monkeypatch):
    monkeypatch.setenv("VINNY_TOKEN_SECRET", "set-for-test-only")
    r = TestClient(create_app(), client=("10.0.0.237", 50000)).get("/health")
    assert r.status_code == 200


# ── python -m engine.api refuses to expose dev tokens on the network ──────────

def test_main_refuses_non_loopback_host_without_token_secret(monkeypatch):
    import engine.api.__main__ as entry
    monkeypatch.setattr(entry.uvicorn, "run", lambda *a, **k: pytest.fail("server started"))
    monkeypatch.setenv("NSOS_API_HOST", "0.0.0.0")
    monkeypatch.delenv("VINNY_TOKEN_SECRET", raising=False)
    with pytest.raises(SystemExit) as exc:
        entry.main()
    assert "VINNY_TOKEN_SECRET" in str(exc.value.code)


@pytest.mark.parametrize("host,secret", [("127.0.0.1", None), ("localhost", None), ("::1", None),
                                         ("0.0.0.0", "set-for-test-only")])
def test_main_starts_on_loopback_or_with_token_secret(monkeypatch, host, secret):
    import engine.api.__main__ as entry
    started = []
    monkeypatch.setattr(entry.uvicorn, "run", lambda *a, **k: started.append(k["host"]))
    monkeypatch.setenv("NSOS_API_HOST", host)
    if secret:
        monkeypatch.setenv("VINNY_TOKEN_SECRET", secret)
    else:
        monkeypatch.delenv("VINNY_TOKEN_SECRET", raising=False)
    entry.main()
    assert started == [host]
