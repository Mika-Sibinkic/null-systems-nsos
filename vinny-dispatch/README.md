# Vinny Dispatch

> Unified entry point for Mika to send commands to NSOS/Vinny over three channels: **terminal**, **email** (`[DISPATCH]` subject), and **Telegram** (`/vinny`).

## Architectural rules (immutable)

1. **Every LLM call goes through NIM.** `engine/router/nim_client.py` is the only LLM client allowed in the rest of the codebase.
2. **Claude Code is a decision-maker, never a worker.** It is invoked in exactly one place: `router/orchestrator.py`. It classifies user intent and emits a JSON plan of NIM task_specs. It is forbidden from acting (zero tools allowed).
3. **All recurring work runs on the Dell.** No Mac cron, no Mac launchd. The Mac is mobile and sleeps.

## Module map

```
vinny-dispatch/
├── router/
│   ├── orchestrator.py   # ONLY place that invokes Claude Code
│   ├── nim_worker.py     # imports engine/router/nim_client.py — only LLM execution path
│   └── dispatcher.py     # core: dedup → classify → execute → reply; writes state.sqlite
├── channels/
│   ├── cli_listener.py   # terminal entry via SSH-forced-command
│   ├── email_poller.py   # Gmail IMAP, filters [DISPATCH] subject
│   └── telegram_bot.py   # long-polling, filters /vinny + /dispatch
├── bin/vinny-recv        # SSH entry → cli_listener
├── systemd/              # vinny-email.service + vinny-telegram.service
└── .env.example
```

## Flow

```
USER  →  channel listener  →  dispatcher  →  orchestrator (claude -p)
                                                    │
                                                    ▼
                                          { task_specs: [NIM, NIM, NIM] }
                                                    │
                                                    ▼
                                            nim_worker.execute_all
                                                    │
                                                    ▼
                                          channel-specific reply
```

Idempotency: every envelope has `msg_id` inserted into SQLite BEFORE any LLM work. Same message → second invocation returns "duplicate".

## Install

See `INSTALL.md` for the Dell deployment steps.

## Run locally (test the orchestrator)

```bash
# In null-systems-nsos repo root, with NIM_API_KEY in env:
python3 vinny-dispatch/router/dispatcher.py "summarize what NSOS does in two sentences"
```

## Logs + inspection

- `logs/dispatcher.log` — per-message structured log
- `logs/email.log` — email poller stdout/stderr (via systemd)
- `logs/telegram.log` — telegram bot stdout/stderr
- `state.sqlite` — `messages(msg_id, channel, sender, body, received_at, status, intent, reply, took_ms)`

## Anti-patterns enforced by code

| Anti-pattern | Where caught |
|---|---|
| Claude doing work instead of decomposing | `orchestrator._validate_plan` rejects non-conforming JSON |
| Non-NIM worker | same validator: `task_spec.worker != "nim"` raises |
| Mac cron / launchd | None exists; this whole tree is Dell-only |
| Duplicate processing | SQLite `PRIMARY KEY` on `msg_id` — insert before work |
