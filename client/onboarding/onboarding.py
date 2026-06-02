"""Onboarding session — the server-side flow that turns a connect into a baseline.

Client-view flow (PRODUCT.md#onboarding):
  1. Operator connects a source (QuickBooks). The OAuth secret is handed to the
     SERVER-SIDE ConnectorSecretStore — it never reaches the web surface.
  2. The web surface receives a scoped, short-lived token (read scopes only).
  3. The server-side connector reads the export (here: a provided export dict),
     the adapter snapshots it to client/snapshots/{tenant_id}/baseline.json.
  4. The web surface, holding only its scoped token, can read the snapshot — and only
     for its own tenant (per-tenant authz).

This module is the first-party backend boundary. No frontend code path can reach a
connector secret or another tenant's snapshot.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional

from .auth import ConnectorSecretStore, authorize
from ..adapters.quickbooks import build_baseline, validate_baseline, write_baseline


@dataclass
class OnboardingSession:
    tenant_id: str
    secret_store: ConnectorSecretStore

    def connect_source(self, source: str, oauth_secret: str) -> None:
        """Operator connects a source. Secret goes server-side ONLY."""
        self.secret_store.store(self.tenant_id, source, oauth_secret)

    def web_token(self, scopes: Optional[list[str]] = None) -> str:
        """Hand the web surface a scoped, short-lived token (read scopes only)."""
        scopes = scopes or ["onboarding:read", "snapshot:read"]
        return self.secret_store.issue_scoped_token(self.tenant_id, scopes)

    def snapshot_quickbooks(
        self,
        export: dict[str, Any],
        *,
        firm: Optional[dict[str, Any]] = None,
        snapshots_root: Optional[Path] = None,
    ) -> Path:
        """Server-side connector reads the QB export and writes a valid baseline.json.

        Requires that a QB secret was stored server-side first (proves the connector,
        not the frontend, is doing the read).
        """
        if not self.secret_store.has_secret(self.tenant_id, "quickbooks"):
            raise PermissionError("no server-side QuickBooks secret for tenant")
        # The connector (server-side caller) is the only thing allowed to touch the secret.
        _ = self.secret_store.get_secret_server_side(
            self.tenant_id, "quickbooks", caller="connector"
        )
        baseline = build_baseline(export, self.tenant_id, firm=firm)
        errs = validate_baseline(baseline)
        if errs:
            raise ValueError(f"baseline invalid: {errs}")
        return write_baseline(baseline, snapshots_root=snapshots_root)

    def read_snapshot_with_token(
        self, token: str, *, snapshots_root: Optional[Path] = None
    ) -> dict[str, Any]:
        """Web-surface read path: requires a valid scoped token for THIS tenant.

        Enforces per-tenant authz — a token for tenant B cannot read tenant A.
        """
        authorize(token, tenant_id=self.tenant_id, scope="snapshot:read")
        root = snapshots_root or (Path(__file__).resolve().parents[2] / "client" / "snapshots")
        path = root / self.tenant_id / "baseline.json"
        import json
        return json.loads(path.read_text())


def onboard_quickbooks(
    tenant_id: str,
    oauth_secret: str,
    export: dict[str, Any],
    *,
    firm: Optional[dict[str, Any]] = None,
    secret_store: Optional[ConnectorSecretStore] = None,
    snapshots_root: Optional[Path] = None,
) -> tuple[Path, str]:
    """One-call onboarding: connect QB -> snapshot -> return (baseline_path, web_token).

    The returned web_token is what the frontend gets; the oauth_secret stays server-side.
    """
    store = secret_store or ConnectorSecretStore()
    session = OnboardingSession(tenant_id=tenant_id, secret_store=store)
    session.connect_source("quickbooks", oauth_secret)
    path = session.snapshot_quickbooks(export, firm=firm, snapshots_root=snapshots_root)
    token = session.web_token()
    return path, token
