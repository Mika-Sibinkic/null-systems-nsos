"""telegram_bot.py — Telegram long-polling bot. Routes /vinny and /dispatch
commands to the dispatcher.

Pure stdlib HTTP (no aiogram dep, so it works on any Dell python3 without pip).

Env:
  TELEGRAM_BOT_TOKEN
  TELEGRAM_ALLOWED_CHAT_IDS=12345,67890  (comma-separated whitelist)
  TELEGRAM_PREFIXES=/vinny,/dispatch (default)
"""
from __future__ import annotations
import os, sys, json, time
from pathlib import Path
from urllib import request, parse, error

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from router.dispatcher import dispatch  # noqa: E402

TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
ALLOWED = set(filter(None, os.environ.get("TELEGRAM_ALLOWED_CHAT_IDS", "").split(",")))
PREFIXES = tuple(os.environ.get("TELEGRAM_PREFIXES", "/vinny,/dispatch").split(","))
TIMEOUT = int(os.environ.get("TELEGRAM_LONG_POLL_TIMEOUT", "30"))
BASE = f"https://api.telegram.org/bot{TOKEN}"


def _api(method: str, params: dict | None = None, *, timeout: int = 35) -> dict:
    url = f"{BASE}/{method}"
    if params:
        url += "?" + parse.urlencode(params, safe=",")
    try:
        with request.urlopen(url, timeout=timeout) as resp:
            return json.loads(resp.read().decode())
    except error.HTTPError as e:
        return {"ok": False, "error": f"HTTP {e.code}: {e.read().decode()[:200]}"}


def send_message(chat_id: str | int, text: str, *, reply_to: int | None = None) -> None:
    # Telegram has a 4096-char limit per message; chunk if needed
    chunks = [text[i:i + 4000] for i in range(0, len(text), 4000)] or [""]
    for i, chunk in enumerate(chunks):
        params = {"chat_id": chat_id, "text": chunk}
        if reply_to and i == 0:
            params["reply_to_message_id"] = reply_to
        _api("sendMessage", params)


def process_update(upd: dict) -> None:
    msg = upd.get("message") or upd.get("edited_message")
    if not msg:
        return
    chat_id = str(msg["chat"]["id"])
    if ALLOWED and chat_id not in ALLOWED:
        return  # silently ignore non-whitelisted chats
    text = msg.get("text", "")
    sender = msg.get("from", {}).get("username") or str(msg.get("from", {}).get("id", "?"))
    message_id = msg.get("message_id")

    # Must match one of our prefixes
    matched = None
    for p in PREFIXES:
        if text.startswith(p):
            matched = p
            break
    if not matched:
        return

    command = text[len(matched):].strip()
    if not command:
        send_message(chat_id, f"Usage: {matched} <command>", reply_to=message_id)
        return

    envelope = {
        "msg_id": f"tg:{chat_id}:{message_id}",
        "channel": "telegram",
        "from": sender,
        "body": command,
    }
    result = dispatch(envelope)

    if result.get("status") == "duplicate":
        return  # don't re-send

    reply = result.get("reply") or f"({result.get('status', '?')})"
    if result.get("status") == "error":
        reply = f"❌ error: {reply}"
    send_message(chat_id, reply, reply_to=message_id)


def run_forever() -> None:
    if not TOKEN:
        sys.exit("TELEGRAM_BOT_TOKEN env required")
    offset = 0
    print(f"[telegram_bot] long-polling for prefixes {PREFIXES}", flush=True)
    while True:
        try:
            resp = _api("getUpdates", {"offset": offset, "timeout": TIMEOUT}, timeout=TIMEOUT + 5)
            if not resp.get("ok"):
                print(f"[telegram_bot] getUpdates failed: {resp.get('error')}", file=sys.stderr, flush=True)
                time.sleep(5)
                continue
            for upd in resp.get("result", []):
                offset = max(offset, upd["update_id"] + 1)
                try:
                    process_update(upd)
                except Exception as e:
                    print(f"[telegram_bot] update error: {e}", file=sys.stderr, flush=True)
        except Exception as e:
            print(f"[telegram_bot] cycle error: {e}", file=sys.stderr, flush=True)
            time.sleep(5)


if __name__ == "__main__":
    run_forever()
