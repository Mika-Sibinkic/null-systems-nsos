"""
take — natural-language wrapper for `take_care`.

The router parses the first whitespace-delimited token as the verb. The
operator naturally types "take care of <project>" — first token is "take" —
so we land here. If the body starts with "care", we delegate to take_care.
Otherwise we return a usage hint pointing at the canonical verbs.

This is a thin shim. All real logic lives in handlers/take_care.py.
"""

from __future__ import annotations

import sys
from pathlib import Path

SKIP_JUDGE = True

NSOS_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(NSOS_DIR))


def handle(envelope: dict) -> str:
    text = (envelope.get("text") or "").strip()
    parts = text.split(None, 1)
    body = (parts[1] if len(parts) > 1 else "").strip().lower()

    # "take care …" or "take_care …" → delegate to take_care handler.
    if body.startswith("care of ") or body.startswith("care ") or body == "care":
        from handlers import take_care
        # Reconstruct envelope text in canonical form for the inner handler.
        new_envelope = dict(envelope)
        new_envelope["text"] = "take_care " + body[len("care"):].lstrip()
        return take_care.handle(new_envelope)

    return ("usage:\n"
            "  take care of <project>   — PM-tier dispatch\n"
            "  take_care <project>      — same, no 'of'\n"
            "  tc <project>             — short form")
