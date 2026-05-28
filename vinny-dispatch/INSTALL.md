# Vinny Dispatch — Install on Dell G7

Run when SSH to `dell` works. Estimated time: 5 min + Mika provides 2 secrets.

## 1. Push code from laptop to Dell

```bash
# from null-systems-nsos repo root
rsync -av --exclude='__pycache__' --exclude='state.sqlite' --exclude='.env' \
  vinny-dispatch/ dell:/home/mika/vinny-dispatch/
chmod +x dell:/home/mika/vinny-dispatch/bin/vinny-recv
```

## 2. Provide secrets (one-time, on Dell)

```bash
ssh dell "cp /home/mika/vinny-dispatch/.env.example /home/mika/vinny-dispatch/.env"
ssh dell "nano /home/mika/vinny-dispatch/.env"
```

Fill:
- `TELEGRAM_BOT_TOKEN` — create bot via @BotFather, /newbot, name "Vinny"
- `TELEGRAM_ALLOWED_CHAT_IDS` — Mika's chat id (use @userinfobot to get it)
- `GMAIL_ADDRESS` + `GMAIL_APP_PASSWORD` — myaccount.google.com → Security → 2-Step → App passwords

## 3. Smoke test (no daemons yet)

```bash
# CLI path (uses Claude Code on Dell — confirm `claude` is in $PATH first)
ssh dell "claude --version"
ssh dell "set -a && source /home/mika/nsos/repo/Active\\ Projects/NSOS/.env && set +a && \
  python3 /home/mika/vinny-dispatch/channels/cli_listener.py 'reply with: ready'"
```

Expected: returns a reply like "ready" within 30s.

## 4. Install systemd services

```bash
ssh dell "mkdir -p ~/.config/systemd/user && \
  cp /home/mika/vinny-dispatch/systemd/vinny-*.service ~/.config/systemd/user/ && \
  systemctl --user daemon-reload && \
  systemctl --user enable --now vinny-email.service vinny-telegram.service && \
  systemctl --user status vinny-email vinny-telegram"
```

If `systemctl --user` fails ("No medium found"), install as root:
```bash
ssh dell "sudo cp /home/mika/vinny-dispatch/systemd/vinny-*.service /etc/systemd/system/ && \
  sudo systemctl daemon-reload && \
  sudo systemctl enable --now vinny-email vinny-telegram"
```

## 5. Per-channel smoke tests

**Telegram**: open chat with @YourVinnyBot, send `/vinny reply with: ready` → expect reply in <5s.

**Email**: send to `GMAIL_ADDRESS` with subject `[DISPATCH] reply with: ready` → expect threaded reply within 60s.

**CLI** (from Mac): `bin/vinny "reply with: ready"` → expect "ready" in stdout.

## 6. Inspection

```bash
ssh dell "tail -50 /home/mika/vinny-dispatch/logs/dispatcher.log"
ssh dell "sqlite3 /home/mika/vinny-dispatch/state.sqlite 'SELECT msg_id, channel, status, intent, took_ms FROM messages ORDER BY received_at DESC LIMIT 20;'"
```

## Troubleshooting

| Symptom | Fix |
|---|---|
| `claude: command not found` on Dell | install Claude Code CLI on Dell (`npm i -g @anthropic-ai/claude-code` or via curl install) |
| Telegram silent | check `TELEGRAM_ALLOWED_CHAT_IDS` matches your chat id; check `systemctl --user status vinny-telegram` |
| Email silent | Gmail App Password rotated? IMAP must be enabled in Gmail settings |
| Dispatcher returns "NIM HTTP 404" | `nim_client.py` model name needs update (catalog has shifted before — see runs/) |
| `claude` returns prose instead of JSON | orchestrator validation rejects it; check `logs/dispatcher.log` for the raw output |
