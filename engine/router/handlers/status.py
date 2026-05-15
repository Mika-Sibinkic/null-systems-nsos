"""
status — NSOS daemon + host health snapshot.

    nsos status

Reads daemon-state.json + .daemon.pid, confirms the PID still points at an
nsos_daemon.py process (guards stale-PID collisions across WSL reboots),
adds host uptime if we're on Linux.
"""

import json
import os
import subprocess
from pathlib import Path

# This handler returns system readouts — never worth gating or scoring.
SKIP_JUDGE = True

NSOS_DIR = Path(__file__).resolve().parent.parent
STATE_FILE = NSOS_DIR / "daemon-state.json"
PID_FILE = NSOS_DIR / ".daemon.pid"


def _pid_is_daemon(pid: int) -> bool:
    try:
        with open(f"/proc/{pid}/cmdline", "rb") as f:
            return "nsos_daemon.py" in f.read().replace(b"\x00", b" ").decode("utf-8", errors="replace")
    except (FileNotFoundError, PermissionError, OSError):
        try:
            os.kill(pid, 0)
            return True
        except Exception:
            return False


def handle(envelope: dict) -> str:
    lines = []

    if PID_FILE.exists():
        try:
            pid = int(PID_FILE.read_text().strip())
            if _pid_is_daemon(pid):
                lines.append(f"daemon: running (pid {pid})")
            else:
                lines.append(f"daemon: NOT running (stale pid file -> {pid})")
        except Exception as e:
            lines.append(f"daemon: state unclear ({e})")
    else:
        lines.append("daemon: NOT running (no pid file)")

    if STATE_FILE.exists():
        try:
            st = json.loads(STATE_FILE.read_text())
            lines.append(f"cycles: {st.get('cycles_run', 0)}")
            last = st.get("last_cycle", "never")
            lines.append(f"last cycle: {last}")
            if st.get("last_error"):
                lines.append(f"last error: {st['last_error']}")
        except Exception as e:
            lines.append(f"state: unreadable ({e})")

    try:
        up = subprocess.run(["uptime", "-p"], capture_output=True, text=True, timeout=2).stdout.strip()
        if up:
            lines.append(f"host {up}")
    except Exception:
        pass

    return "\n".join(lines)
