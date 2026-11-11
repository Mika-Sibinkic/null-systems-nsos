"""`python -m engine.api` -- serve the engine HTTP boundary with uvicorn.

Run from the repo root so `client.*` and `engine.*` import. Host and port come
from NSOS_API_HOST (default 127.0.0.1) and NSOS_API_PORT (default 8000).

Without VINNY_TOKEN_SECRET the server signs with the dev secret and serves
/dev/scoped-token, so it refuses to bind anything but loopback in that mode.
"""
from __future__ import annotations

import os
import sys

import uvicorn

from engine.api.app import token_secret_mode

LOOPBACK_HOSTS = {"127.0.0.1", "localhost", "::1"}


def main() -> None:
    host = os.environ.get("NSOS_API_HOST", "127.0.0.1")
    if host not in LOOPBACK_HOSTS and token_secret_mode() == "dev-only":
        sys.exit(f"refusing to serve dev tokens on {host}: set VINNY_TOKEN_SECRET or use NSOS_API_HOST=127.0.0.1")
    uvicorn.run(
        "engine.api.app:app",
        host=host,
        port=int(os.environ.get("NSOS_API_PORT", "8000")),
        log_level="info",
    )


if __name__ == "__main__":
    main()
