"""
thread — inspect or clear the current channel's thread memory.

    nsos thread          # show last turns on this channel for this sender
    nsos thread clear    # forget this thread
"""

import sys
from pathlib import Path

SKIP_JUDGE = True

NSOS_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(NSOS_DIR))


def handle(envelope: dict) -> str:
    import thread_memory

    parts = (envelope.get("text") or "").split(None, 1)
    arg = parts[1].strip().lower() if len(parts) > 1 else ""

    channel = envelope.get("source", "")
    sender_id = envelope.get("sender_id", "")

    if arg == "clear":
        removed = thread_memory.clear(channel, sender_id)
        return "thread cleared" if removed else "no thread to clear"

    body = thread_memory.summarize(channel, sender_id, n=10)
    return f"thread for ({channel} / {sender_id[:32]}):\n{body}"
