"""engine/api/app.py -- the HTTP boundary the Next.js web surface calls.

The web layer (web/lib/engine.ts) holds only a scoped, short-lived token and talks
to this service over HTTP. This service enforces per-tenant authz with the same
`client.onboarding.auth.authorize` check the onboarding flow uses, then calls the
same engine code the tests call. No engine behavior is defined here; this module
only routes, authorizes, and shapes errors as JSON.

Endpoints
  GET  /health              liveness + which mode the engine is in
  POST /dev/scoped-token    dev-only: mint a read-scoped token for a tenant.
                            Enabled only while VINNY_TOKEN_SECRET is unset (the
                            dev signing secret is in use). With a production
                            secret configured this endpoint does not exist (404).
  GET  /teaser?tenant=ID    the <1h teaser finding for one tenant snapshot.
                            Requires `Authorization: Bearer <scoped token>` whose
                            tenant matches and whose scopes include snapshot:read.

Model mode
  NIM_API_KEY set     -> "live"
  NIM_API_KEY unset   -> "offline-deterministic"
  The teaser is pure arithmetic over the snapshot and works in both modes.
  Any route that needs a live model declares `Depends(require_live_model)` and
  fails closed with a 503 JSON error instead of fabricating a result.

Run:  python -m engine.api      (host/port from NSOS_API_HOST / NSOS_API_PORT)
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import Optional

from fastapi import Depends, FastAPI, HTTPException, Query, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from client.onboarding.auth import (
    DEFAULT_TTL_SECONDS,
    AuthError,
    authorize,
    issue_token,
)
from engine.teaser.teaser import from_snapshot

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_SNAPSHOTS_ROOT = ROOT / "client" / "snapshots"
TEASER_SCOPE = "snapshot:read"
DEV_TOKEN_SCOPES = ["onboarding:read", "snapshot:read"]  # what onboarding grants the web layer
_TOKEN_SECRET_ENV = "VINNY_TOKEN_SECRET"
_MODEL_KEY_ENV = "NIM_API_KEY"


# ── mode helpers ──────────────────────────────────────────────────────────────

def model_mode() -> str:
    """'live' when a model key is configured, else 'offline-deterministic'."""
    return "live" if os.environ.get(_MODEL_KEY_ENV) else "offline-deterministic"


def token_secret_mode() -> str:
    """'configured' when VINNY_TOKEN_SECRET is set, else 'dev-only'."""
    return "configured" if os.environ.get(_TOKEN_SECRET_ENV) else "dev-only"


def require_live_model() -> None:
    """Dependency for routes that need a real model. Fails closed, never fabricates."""
    if model_mode() != "live":
        raise HTTPException(
            status_code=503,
            detail=f"live model required but {_MODEL_KEY_ENV} is not configured",
        )


# ── response models ───────────────────────────────────────────────────────────

class Health(BaseModel):
    status: str = "ok"
    service: str = "nsos-engine"
    model_mode: str
    token_secret: str


class TeaserFinding(BaseModel):
    """Mirror of web/lib/engine.ts `TeaserFinding`."""
    id: str
    headline: str
    impact_usd: float
    impact_hours: float
    evidence: list[str]
    confidence: float
    method: str
    team: str


class DevTokenRequest(BaseModel):
    tenant_id: str = Field(min_length=1)


class DevToken(BaseModel):
    token: str
    tenant_id: str
    scopes: list[str]
    expires_in: int


# ── app factory ───────────────────────────────────────────────────────────────

def _bearer(request: Request) -> str:
    auth = request.headers.get("authorization", "")
    scheme, _, token = auth.partition(" ")
    return token.strip() if scheme.lower() == "bearer" else ""


def create_app(snapshots_root: Optional[Path] = None) -> FastAPI:
    root = Path(snapshots_root or os.environ.get("NSOS_SNAPSHOTS_ROOT") or DEFAULT_SNAPSHOTS_ROOT)
    app = FastAPI(title="NSOS engine API", version="0.1.0", docs_url=None, redoc_url=None)
    app.state.snapshots_root = root

    @app.exception_handler(HTTPException)
    async def _json_errors(_: Request, exc: HTTPException) -> JSONResponse:
        # One error shape for every failure: {"error": "<reason>"}.
        return JSONResponse(status_code=exc.status_code, content={"error": str(exc.detail)})

    @app.get("/health", response_model=Health)
    def health() -> Health:
        return Health(model_mode=model_mode(), token_secret=token_secret_mode())

    @app.post("/dev/scoped-token", response_model=DevToken)
    def dev_scoped_token(body: DevTokenRequest) -> DevToken:
        if token_secret_mode() != "dev-only":
            # Production signing secret in use: this affordance must not exist.
            raise HTTPException(status_code=404, detail="not found")
        token = issue_token(body.tenant_id, DEV_TOKEN_SCOPES)
        return DevToken(
            token=token,
            tenant_id=body.tenant_id,
            scopes=list(DEV_TOKEN_SCOPES),
            expires_in=DEFAULT_TTL_SECONDS,
        )

    @app.get("/teaser", response_model=TeaserFinding)
    def teaser(request: Request, tenant: str = Query(min_length=1)) -> TeaserFinding:
        try:
            authorize(_bearer(request), tenant_id=tenant, scope=TEASER_SCOPE)
        except AuthError:
            raise HTTPException(status_code=401, detail="unauthorized")
        try:
            result = from_snapshot(tenant, snapshots_root=app.state.snapshots_root)
        except FileNotFoundError:
            raise HTTPException(status_code=404, detail=f"no snapshot for tenant {tenant!r}")
        except ValueError as e:
            raise HTTPException(status_code=422, detail=str(e))
        return TeaserFinding(**result.to_finding())

    return app


app = create_app()
