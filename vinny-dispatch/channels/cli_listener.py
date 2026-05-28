"""cli_listener.py — entry point for terminal/SSH-bridged commands.

Invoked by `vinny-dispatch/bin/vinny-recv` (called over SSH by the Mac wrapper).
Reads command from argv or stdin, calls dispatch, writes reply to stdout.
Exit codes: 0 ok, 1 dispatcher error, 2 NIM/worker failure (best-effort).
"""
from __future__ import annotations
import sys, os, uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from router.dispatcher import dispatch  # noqa: E402


def main(argv: list[str]) -> int:
    if "--msg-id" in argv:
        i = argv.index("--msg-id")
        msg_id = argv[i + 1]
        argv = argv[:i] + argv[i + 2:]
    else:
        msg_id = f"cli:{uuid.uuid4().hex[:12]}"

    if argv[1:]:
        body = " ".join(argv[1:])
    else:
        body = sys.stdin.read().strip()
    if not body:
        sys.stderr.write("usage: cli_listener <command...> | echo cmd | cli_listener\n")
        return 1

    envelope = {
        "msg_id": msg_id,
        "channel": "cli",
        "from": os.environ.get("SSH_CLIENT", "").split(" ", 1)[0] or os.environ.get("USER", "?"),
        "body": body,
    }
    result = dispatch(envelope)
    status = result.get("status")
    sys.stdout.write((result.get("reply") or "") + "\n")
    if status == "ok" or status == "duplicate":
        return 0
    if status == "error":
        msg = (result.get("reply") or "").lower()
        if "nim" in msg or "timeout" in msg:
            return 2
        return 1
    return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv))
