"""email_poller.py — Gmail IMAP poller. Only routes messages with subject
starting with [DISPATCH]. Replies via SMTP with In-Reply-To threading.

Auth: Gmail App Password (2FA must be enabled on the account).
Env:
  GMAIL_ADDRESS, GMAIL_APP_PASSWORD
  GMAIL_IMAP_HOST=imap.gmail.com (default)
  GMAIL_SMTP_HOST=smtp.gmail.com (default)
  GMAIL_SMTP_PORT=465 (default, SSL)
  GMAIL_DISPATCH_PREFIX=[DISPATCH] (default)
"""
from __future__ import annotations
import os, sys, time, email, imaplib, smtplib, ssl
from email.mime.text import MIMEText
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from router.dispatcher import dispatch  # noqa: E402

PREFIX = os.environ.get("GMAIL_DISPATCH_PREFIX", "[DISPATCH]")
ADDRESS = os.environ.get("GMAIL_ADDRESS")
APP_PASSWORD = os.environ.get("GMAIL_APP_PASSWORD")
IMAP_HOST = os.environ.get("GMAIL_IMAP_HOST", "imap.gmail.com")
SMTP_HOST = os.environ.get("GMAIL_SMTP_HOST", "smtp.gmail.com")
SMTP_PORT = int(os.environ.get("GMAIL_SMTP_PORT", "465"))
POLL_INTERVAL = int(os.environ.get("GMAIL_POLL_INTERVAL", "60"))


def _imap_connect() -> imaplib.IMAP4_SSL:
    conn = imaplib.IMAP4_SSL(IMAP_HOST)
    conn.login(ADDRESS, APP_PASSWORD)
    conn.select("INBOX")
    return conn


def _smtp_send(to: str, subject: str, body: str, in_reply_to: str | None) -> None:
    msg = MIMEText(body)
    msg["Subject"] = subject
    msg["From"] = ADDRESS
    msg["To"] = to
    if in_reply_to:
        msg["In-Reply-To"] = in_reply_to
        msg["References"] = in_reply_to
    ctx = ssl.create_default_context()
    with smtplib.SMTP_SSL(SMTP_HOST, SMTP_PORT, context=ctx) as s:
        s.login(ADDRESS, APP_PASSWORD)
        s.send_message(msg)


def _extract_body(msg: email.message.Message) -> str:
    if msg.is_multipart():
        for part in msg.walk():
            if part.get_content_type() == "text/plain":
                payload = part.get_payload(decode=True)
                if payload:
                    return payload.decode(part.get_content_charset() or "utf-8", errors="replace")
    payload = msg.get_payload(decode=True)
    if payload:
        return payload.decode(msg.get_content_charset() or "utf-8", errors="replace")
    return ""


def poll_once(conn: imaplib.IMAP4_SSL) -> int:
    """Search for unseen [DISPATCH] messages, process each, mark seen."""
    typ, data = conn.search(None, f'(UNSEEN SUBJECT "{PREFIX}")')
    if typ != "OK" or not data or not data[0]:
        return 0
    ids = data[0].split()
    count = 0
    for uid in ids:
        typ, msg_data = conn.fetch(uid, "(RFC822)")
        if typ != "OK":
            continue
        raw = msg_data[0][1]
        msg = email.message_from_bytes(raw)
        subject = msg.get("Subject", "").strip()
        sender = email.utils.parseaddr(msg.get("From", ""))[1]
        message_id = msg.get("Message-ID", f"email-fallback-{uid.decode()}")
        body = _extract_body(msg).strip()
        # Strip prefix from subject to get the command
        command = subject[len(PREFIX):].strip(" :-")
        if body:
            command = f"{command}\n\n{body}"
        envelope = {
            "msg_id": f"email:{message_id}",
            "channel": "email",
            "from": sender,
            "body": command,
        }
        result = dispatch(envelope)
        reply_body = result.get("reply") or f"({result.get('status', 'no_status')})"
        reply_subject = f"Re: {subject}"
        if result.get("status") not in ("ok", "duplicate"):
            reply_subject = f"[DISPATCH FAIL] {subject[len(PREFIX):].strip()}"
        try:
            _smtp_send(sender, reply_subject, reply_body, in_reply_to=message_id)
        except Exception as e:
            print(f"  SMTP send failed: {e}", file=sys.stderr)
        conn.store(uid, "+FLAGS", r"(\Seen)")
        count += 1
    return count


def run_forever() -> None:
    if not ADDRESS or not APP_PASSWORD:
        sys.exit("GMAIL_ADDRESS and GMAIL_APP_PASSWORD env required")
    print(f"[email_poller] watching {ADDRESS} for subjects starting with {PREFIX!r}", flush=True)
    while True:
        try:
            conn = _imap_connect()
            try:
                n = poll_once(conn)
                if n:
                    print(f"[email_poller] processed {n} messages", flush=True)
            finally:
                try:
                    conn.logout()
                except Exception:
                    pass
        except Exception as e:
            print(f"[email_poller] cycle error: {e}", file=sys.stderr, flush=True)
        time.sleep(POLL_INTERVAL)


if __name__ == "__main__":
    if "--once" in sys.argv:
        if not ADDRESS or not APP_PASSWORD:
            sys.exit("GMAIL_ADDRESS and GMAIL_APP_PASSWORD env required")
        c = _imap_connect()
        try:
            n = poll_once(c)
            print(f"processed: {n}")
        finally:
            c.logout()
    else:
        run_forever()
