"""
judge — score arbitrary text through the quality judge (diagnostic verb).

    nsos judge "some text to score"

Handy for eyeballing rubric behavior on sample outputs without needing a
full handler round-trip. Returns the raw score JSON. Skips the judge
integration itself (you don't want to score a score).
"""

import json
import sys
from pathlib import Path

# This verb's output is itself the judge's reasoning — don't double-judge.
SKIP_JUDGE = True

NSOS_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(NSOS_DIR))


def handle(envelope: dict) -> str:
    import quality_judge

    text = envelope.get("text", "")
    # Strip the verb itself ("judge <body>") to get the body.
    parts = text.split(None, 1)
    body = parts[1] if len(parts) > 1 else ""
    if not body:
        return "usage: judge <text>"

    scores = quality_judge.score(
        body,
        context={
            "source": envelope.get("source"),
            "verb": "judge",
            "user_text": body,
        },
    )
    gated = quality_judge.gate_decision(scores)
    return json.dumps(
        {"scores": scores, "would_gate": gated},
        indent=2,
        default=str,
    )
