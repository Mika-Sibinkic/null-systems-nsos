"""Tests for client/onboarding — scoped-token auth + secrets-server-side contract."""
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from client.onboarding.auth import (  # noqa: E402
    AuthError,
    ConnectorSecretStore,
    authorize,
    issue_token,
    verify_token,
)
from client.onboarding.onboarding import OnboardingSession, onboard_quickbooks  # noqa: E402

EXPORT = json.loads((ROOT / "examples" / "synthetic-client-a" / "quickbooks_export.json").read_text())
FIRM = json.loads((ROOT / "examples" / "synthetic-client-a" / "firm.json").read_text())


# ── token auth ────────────────────────────────────────────────────────────────

def test_issue_and_verify_roundtrip():
    tok = issue_token("tenant-a", ["snapshot:read"])
    claims = verify_token(tok)
    assert claims.tenant_id == "tenant-a"
    assert "snapshot:read" in claims.scopes


def test_tampered_signature_rejected():
    tok = issue_token("tenant-a", ["snapshot:read"])
    payload, _sig = tok.rsplit(".", 1)
    forged = payload + ".AAAAforged"
    with pytest.raises(AuthError):
        verify_token(forged)


def test_expired_token_rejected():
    tok = issue_token("tenant-a", ["snapshot:read"], ttl_seconds=1, now=1000)
    with pytest.raises(AuthError):
        verify_token(tok, now=2000)


@pytest.mark.parametrize("claims", [[], {"scopes": []}, {"tenant_id": "tenant-a", "exp": "soon"}])
def test_signed_token_with_wrong_claims_shape_is_auth_error(claims):
    import base64, hashlib, hmac
    from client.onboarding.auth import _DEV_SECRET
    payload = base64.urlsafe_b64encode(json.dumps(claims).encode()).rstrip(b"=").decode()
    sig = base64.urlsafe_b64encode(
        hmac.new(_DEV_SECRET.encode(), payload.encode(), hashlib.sha256).digest()
    ).rstrip(b"=").decode()
    with pytest.raises(AuthError):
        verify_token(f"{payload}.{sig}")


@pytest.mark.parametrize("bad", ["", "/tmp/x", "../x", "Tenant-A", "-a", "a" * 65, "a\n"])
def test_refuses_to_issue_for_invalid_tenant_id(bad):
    with pytest.raises(AuthError):
        issue_token(bad, ["snapshot:read"])


def test_refuses_to_issue_non_read_scope():
    # The web surface can never be granted a write/secret scope.
    with pytest.raises(AuthError):
        issue_token("tenant-a", ["connector:secret:read"])


def test_authorize_blocks_cross_tenant():
    tok = issue_token("tenant-a", ["snapshot:read"])
    # auth (signature ok) but authz must fail for a different tenant
    with pytest.raises(AuthError):
        authorize(tok, tenant_id="tenant-b", scope="snapshot:read")


def test_authorize_requires_scope():
    tok = issue_token("tenant-a", ["onboarding:read"])
    with pytest.raises(AuthError):
        authorize(tok, tenant_id="tenant-a", scope="snapshot:read")


def test_authorize_happy_path():
    tok = issue_token("tenant-a", ["snapshot:read"])
    claims = authorize(tok, tenant_id="tenant-a", scope="snapshot:read")
    assert claims.tenant_id == "tenant-a"


# ── secret store: secrets never reach the frontend ──────────────────────────────

def test_connector_secret_never_returned_to_frontend():
    store = ConnectorSecretStore()
    store.store("tenant-a", "quickbooks", "qb-oauth-supersecret")
    # web app can see presence...
    assert store.has_secret("tenant-a", "quickbooks") is True
    # ...but a non-connector caller is refused the raw secret
    with pytest.raises(AuthError):
        store.get_secret_server_side("tenant-a", "quickbooks", caller="frontend")
    # only the server-side connector gets it
    assert store.get_secret_server_side("tenant-a", "quickbooks", caller="connector") == "qb-oauth-supersecret"


def test_issued_web_token_is_read_only():
    store = ConnectorSecretStore()
    tok = store.issue_scoped_token("tenant-a", ["snapshot:read"])
    claims = verify_token(tok)
    assert all(s.endswith(":read") or s == "sow:select" for s in claims.scopes)


# ── end-to-end onboarding ───────────────────────────────────────────────────────

def test_onboard_quickbooks_writes_snapshot_and_returns_web_token(tmp_path):
    path, web_token = onboard_quickbooks(
        "synth-acme-services",
        "qb-oauth-secret",
        EXPORT,
        firm=FIRM,
        snapshots_root=tmp_path,
    )
    assert path.exists()
    baseline = json.loads(path.read_text())
    assert baseline["tenant_id"] == "synth-acme-services"
    # the returned token is scoped to the tenant and read-only
    claims = verify_token(web_token)
    assert claims.tenant_id == "synth-acme-services"


def test_snapshot_requires_server_side_secret(tmp_path):
    store = ConnectorSecretStore()
    session = OnboardingSession("tenant-a", store)
    # no secret stored -> connector cannot snapshot
    with pytest.raises(PermissionError):
        session.snapshot_quickbooks(EXPORT, snapshots_root=tmp_path)


def test_web_read_path_enforces_per_tenant_authz(tmp_path):
    path, _ = onboard_quickbooks(
        "tenant-a", "secret", EXPORT, firm=FIRM, snapshots_root=tmp_path
    )
    session = OnboardingSession("tenant-a", ConnectorSecretStore())
    # a token for tenant-b cannot read tenant-a's snapshot
    bad_token = issue_token("tenant-b", ["snapshot:read"])
    with pytest.raises(AuthError):
        session.read_snapshot_with_token(bad_token, snapshots_root=tmp_path)
    # the correct tenant token can
    good_token = issue_token("tenant-a", ["snapshot:read"])
    snap = session.read_snapshot_with_token(good_token, snapshots_root=tmp_path)
    assert snap["tenant_id"] == "tenant-a"


def test_tenant_rule_matches_baseline_schema():
    # The adapter enforces the schema pattern, the token boundary enforces TENANT_ID_RE.
    from client.onboarding.auth import TENANT_ID_RE
    schema = json.loads((ROOT / "schemas" / "baseline.json").read_text())
    assert schema["properties"]["tenant_id"]["pattern"] == TENANT_ID_RE.pattern
