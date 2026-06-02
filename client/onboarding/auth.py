"""Scoped-token auth for the onboarding surface (Vinnie auth/tool-auth pattern).

Engineering-bar pillar 1 (Security) hard rules enforced here:
  - No secrets in the frontend. The web surface never holds a connector OAuth token.
    It holds a server-issued, scoped, short-lived bearer token and nothing else.
  - No direct frontend <-> source-system. A first-party backend (this module + the
    connector) sits in between; the scoped token only authorizes engine reads for ONE
    tenant.
  - Authentication != Authorization. Every check verifies BOTH a valid (unexpired,
    untampered) token AND that the token's tenant_id matches the resource's tenant_id
    (per-resource policy, not just per-route).

Tokens are HMAC-signed (stdlib hmac/hashlib — no external dep) over a compact claims
payload. The signing secret lives server-side only (env VINNY_TOKEN_SECRET). Connector
secrets (QB OAuth tokens, etc.) are held by ConnectorSecretStore, which NEVER returns a
secret to any caller that isn't the server-side connector — it returns only a presence
flag and the scoped access token the web app is allowed to see.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import time
from dataclasses import dataclass, field
from typing import Optional

DEFAULT_TTL_SECONDS = 900  # 15 min — short-lived by contract
_SECRET_ENV = "VINNY_TOKEN_SECRET"
# Dev-only fallback secret. In production VINNY_TOKEN_SECRET MUST be set server-side;
# this constant is NOT a credential to any real system and is flagged by pillar5 as dev-only.
_DEV_SECRET = "dev-only-unsigned-not-for-production"


class AuthError(Exception):
    """Raised on any auth/authz failure. Never leaks why beyond a coarse reason."""


def _secret() -> bytes:
    return os.environ.get(_SECRET_ENV, _DEV_SECRET).encode()


def _b64u(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


def _b64u_dec(s: str) -> bytes:
    pad = "=" * (-len(s) % 4)
    return base64.urlsafe_b64decode(s + pad)


@dataclass
class ScopedToken:
    """A scoped, short-lived token the web surface is allowed to hold."""
    tenant_id: str
    scopes: tuple[str, ...]
    issued_at: int
    expires_at: int

    def to_claims(self) -> dict:
        return {
            "tenant_id": self.tenant_id,
            "scopes": list(self.scopes),
            "iat": self.issued_at,
            "exp": self.expires_at,
        }


# Read-tier scopes the web app may be granted. Connector-secret access is NOT here —
# the frontend can never be scoped to read a raw connector secret.
READ_SCOPES = frozenset({
    "onboarding:read",
    "snapshot:read",
    "diagnostic:read",
    "sow:read",
    "sow:select",
})


def issue_token(
    tenant_id: str,
    scopes: list[str] | tuple[str, ...],
    *,
    ttl_seconds: int = DEFAULT_TTL_SECONDS,
    now: Optional[int] = None,
) -> str:
    """Issue a signed, scoped, short-lived token for ONE tenant. Server-side only.

    Rejects any scope that isn't in READ_SCOPES — the web surface cannot be granted a
    scope that would expose a connector secret or mutate another tenant's data.
    """
    if not tenant_id:
        raise AuthError("tenant_id required")
    bad = set(scopes) - READ_SCOPES
    if bad:
        raise AuthError(f"refusing to issue non-read scope(s): {sorted(bad)}")
    now = int(now if now is not None else time.time())
    tok = ScopedToken(
        tenant_id=tenant_id,
        scopes=tuple(scopes),
        issued_at=now,
        expires_at=now + ttl_seconds,
    )
    payload = _b64u(json.dumps(tok.to_claims(), separators=(",", ":")).encode())
    sig = _b64u(hmac.new(_secret(), payload.encode(), hashlib.sha256).digest())
    return f"{payload}.{sig}"


def verify_token(token: str, *, now: Optional[int] = None) -> ScopedToken:
    """Verify signature + expiry. Returns the ScopedToken or raises AuthError.

    This is AUTHENTICATION only. Authorization (tenant + scope match) is a separate
    explicit check — see authorize().
    """
    if not token or "." not in token:
        raise AuthError("malformed token")
    payload, sig = token.rsplit(".", 1)
    expected = _b64u(hmac.new(_secret(), payload.encode(), hashlib.sha256).digest())
    if not hmac.compare_digest(sig, expected):
        raise AuthError("bad signature")
    try:
        claims = json.loads(_b64u_dec(payload))
    except Exception:
        raise AuthError("unparseable claims")
    now = int(now if now is not None else time.time())
    if int(claims.get("exp", 0)) < now:
        raise AuthError("token expired")
    return ScopedToken(
        tenant_id=claims["tenant_id"],
        scopes=tuple(claims.get("scopes", [])),
        issued_at=int(claims.get("iat", 0)),
        expires_at=int(claims.get("exp", 0)),
    )


def authorize(token: str, *, tenant_id: str, scope: str, now: Optional[int] = None) -> ScopedToken:
    """AUTHENTICATION + AUTHORIZATION in one check (per-resource policy).

    Verifies the token, then asserts BOTH:
      - the token's tenant_id matches the resource's tenant_id (no cross-tenant access)
      - the requested scope is present in the token
    Raises AuthError on any mismatch.
    """
    tok = verify_token(token, now=now)
    if tok.tenant_id != tenant_id:
        raise AuthError("tenant mismatch")  # the authz check that route-only auth misses
    if scope not in tok.scopes:
        raise AuthError(f"scope '{scope}' not granted")
    return tok


@dataclass
class ConnectorSecretStore:
    """Server-side-only store for connector secrets (QB OAuth tokens, etc.).

    The web surface NEVER calls store()/_get_secret(). It only ever calls
    issue_scoped_token(), which returns a token with read scopes — never the secret.
    In production this is backed by a secrets manager; here it's an in-memory map so
    the contract is testable. The secret value never appears in any return value
    exposed to a frontend caller.
    """
    _secrets: dict[tuple[str, str], str] = field(default_factory=dict)

    def store(self, tenant_id: str, source: str, secret: str) -> None:
        """Server-side connector stores a source secret for a tenant."""
        if not secret:
            raise AuthError("empty secret")
        self._secrets[(tenant_id, source)] = secret

    def has_secret(self, tenant_id: str, source: str) -> bool:
        """Presence flag the web app may see — never the secret itself."""
        return (tenant_id, source) in self._secrets

    def get_secret_server_side(self, tenant_id: str, source: str, *, caller: str) -> str:
        """Return the raw secret ONLY to a server-side connector caller.

        `caller` must be 'connector'. Any other caller (a frontend-origin request)
        is refused — this is the wall that keeps secrets out of the frontend.
        """
        if caller != "connector":
            raise AuthError("connector secrets are server-side only")
        try:
            return self._secrets[(tenant_id, source)]
        except KeyError:
            raise AuthError("no secret for tenant/source")

    def issue_scoped_token(
        self, tenant_id: str, scopes: list[str], *, ttl_seconds: int = DEFAULT_TTL_SECONDS
    ) -> str:
        """The ONLY thing the web app receives: a scoped short-lived token, not a secret."""
        return issue_token(tenant_id, scopes, ttl_seconds=ttl_seconds)
