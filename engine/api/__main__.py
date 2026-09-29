"""`python -m engine.api` -- serve the engine HTTP boundary with uvicorn.

Run from the repo root so `client.*` and `engine.*` import. Host and port come
from NSOS_API_HOST (default 127.0.0.1) and NSOS_API_PORT (default 8000).
"""
from __future__ import annotations

import os

import uvicorn


def main() -> None:
    uvicorn.run(
        "engine.api.app:app",
        host=os.environ.get("NSOS_API_HOST", "127.0.0.1"),
        port=int(os.environ.get("NSOS_API_PORT", "8000")),
        log_level="info",
    )


if __name__ == "__main__":
    main()
