"""
verbs — list registered router verbs.

    nsos verbs

Handy when you can't remember what's available.
"""

from pathlib import Path

# Pure metadata output — skip judge.
SKIP_JUDGE = True

HANDLERS_DIR = Path(__file__).resolve().parent


def handle(envelope: dict) -> str:
    names = sorted(
        p.stem for p in HANDLERS_DIR.glob("*.py") if not p.name.startswith("_")
    )
    if not names:
        return "(no verbs registered)"
    return "registered verbs:\n  " + "\n  ".join(names)
