"""dispatcher.py — core: receive envelope → dedup → classify → execute → reply.

Single source of truth for state. The only writer to state.sqlite.

Envelope schema:
  {
    "msg_id": "<channel-specific unique id>",
    "channel": "cli" | "email" | "telegram",
    "from": "<sender identifier>",
    "body": "<the actual command text>",
    "reply_hook": <optional callable, set by channel listener>
  }
"""
from __future__ import annotations
import sqlite3, json, time, os, sys
from pathlib import Path
from typing import Callable

ROOT = Path(__file__).resolve().parents[1]
STATE = Path(os.environ.get("VINNY_STATE", str(ROOT / "state.sqlite")))
LOG = Path(os.environ.get("VINNY_LOG", str(ROOT / "logs" / "dispatcher.log")))

sys.path.insert(0, str(ROOT))
from router.orchestrator import classify, _validate_plan
from router.nim_worker import execute_all, combine


def _init_db() -> sqlite3.Connection:
    STATE.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(STATE), isolation_level=None)  # autocommit
    conn.execute("""
        CREATE TABLE IF NOT EXISTS messages (
            msg_id TEXT PRIMARY KEY,
            channel TEXT NOT NULL,
            sender TEXT,
            body TEXT,
            received_at REAL NOT NULL,
            status TEXT NOT NULL,
            intent TEXT,
            reply TEXT,
            took_ms INTEGER
        )
    """)
    return conn


def _log(line: str) -> None:
    LOG.parent.mkdir(parents=True, exist_ok=True)
    with LOG.open("a") as f:
        f.write(f"[{time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())}] {line}\n")


def dispatch(envelope: dict) -> dict:
    """Process one envelope. Returns {status, reply, ...} for the channel."""
    conn = _init_db()
    msg_id = envelope["msg_id"]
    body = envelope.get("body", "")
    sender = envelope.get("from", "?")
    channel = envelope.get("channel", "?")

    # IDEMPOTENCY — insert BEFORE any work, in same txn
    try:
        conn.execute(
            "INSERT INTO messages (msg_id, channel, sender, body, received_at, status) "
            "VALUES (?, ?, ?, ?, ?, 'in_progress')",
            (msg_id, channel, sender, body, time.time()),
        )
    except sqlite3.IntegrityError:
        # Duplicate
        prior = conn.execute(
            "SELECT status, reply FROM messages WHERE msg_id = ?", (msg_id,)
        ).fetchone()
        _log(f"DUP msg_id={msg_id} channel={channel} prior_status={prior[0] if prior else '?'}")
        return {"status": "duplicate", "reply": prior[1] if prior else None}

    _log(f"NEW msg_id={msg_id} channel={channel} body={body[:80]!r}")

    start = time.monotonic()
    try:
        plan = classify(body)
        intent = plan.get("intent", "?")

        if intent == "REJECT_DESTRUCTIVE":
            reply = "REJECTED — orchestrator classified this as destructive. No action taken."
        elif not plan.get("task_specs"):
            reply = f"(intent: {intent}) — orchestrator returned no task_specs."
        else:
            results = execute_all(plan["task_specs"])
            reply = combine(results, plan.get("post_processing"))

        took_ms = int((time.monotonic() - start) * 1000)
        conn.execute(
            "UPDATE messages SET status='done', intent=?, reply=?, took_ms=? WHERE msg_id=?",
            (intent, reply, took_ms, msg_id),
        )
        _log(f"OK msg_id={msg_id} intent={intent} took_ms={took_ms} reply_len={len(reply)}")
        return {"status": "ok", "intent": intent, "reply": reply, "took_ms": took_ms}

    except Exception as e:
        err = f"{type(e).__name__}: {str(e)[:300]}"
        conn.execute(
            "UPDATE messages SET status='error', reply=? WHERE msg_id=?",
            (err, msg_id),
        )
        _log(f"ERR msg_id={msg_id} {err}")
        return {"status": "error", "reply": err}


def history(limit: int = 20) -> list[dict]:
    conn = _init_db()
    rows = conn.execute(
        "SELECT msg_id, channel, sender, body, received_at, status, intent, took_ms "
        "FROM messages ORDER BY received_at DESC LIMIT ?", (limit,),
    ).fetchall()
    cols = ["msg_id", "channel", "sender", "body", "received_at", "status", "intent", "took_ms"]
    return [dict(zip(cols, r)) for r in rows]


if __name__ == "__main__":
    import argparse, uuid
    p = argparse.ArgumentParser()
    p.add_argument("--channel", default="cli")
    p.add_argument("--msg-id", default=None)
    p.add_argument("--from", dest="sender", default=os.environ.get("USER", "?"))
    p.add_argument("body", nargs="+")
    args = p.parse_args()
    envelope = {
        "msg_id": args.msg_id or f"{args.channel}:{uuid.uuid4().hex[:12]}",
        "channel": args.channel,
        "from": args.sender,
        "body": " ".join(args.body),
    }
    result = dispatch(envelope)
    print(result.get("reply") or json.dumps(result, indent=2))
    sys.exit(0 if result.get("status") == "ok" else 1)
