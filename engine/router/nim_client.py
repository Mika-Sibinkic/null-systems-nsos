"""nim_client.py — single canonical NIM v4 client for all of Vinny/NSOS.

Per architectural rule: EVERY LLM call across this codebase routes through here.
Claude Code (the orchestrator) is allowed exactly one shell-out elsewhere
(`vinny-dispatch/router/orchestrator.py`) — everything else MUST import this.

Models verified on NIM as of 2026-05:
  - meta/llama-3.3-70b-instruct (primary, ~1s response)
  - meta/llama-3.1-405b-instruct (reasoning, slower)
"""
from __future__ import annotations
import os, json
from urllib import request, error
from typing import Optional

NIM_BASE = os.environ.get("NIM_BASE_URL", "https://integrate.api.nvidia.com/v1")
PRIMARY_MODEL = os.environ.get("NIM_PRIMARY_MODEL", "meta/llama-3.3-70b-instruct")
REASONING_MODEL = os.environ.get("NIM_REASONING_MODEL", "meta/llama-3.1-405b-instruct")


def call_nim(
    prompt: str,
    *,
    model: str = PRIMARY_MODEL,
    max_tokens: int = 800,
    temperature: float = 0.3,
    system: str = "",
    timeout: int = 60,
) -> str:
    api_key = os.environ.get("NIM_API_KEY")
    if not api_key:
        raise RuntimeError("NIM_API_KEY missing in env")
    msgs = []
    if system:
        msgs.append({"role": "system", "content": system})
    msgs.append({"role": "user", "content": prompt})
    body = json.dumps({
        "model": model,
        "messages": msgs,
        "max_tokens": max_tokens,
        "temperature": temperature,
    }).encode()
    req = request.Request(
        f"{NIM_BASE}/chat/completions",
        data=body,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    try:
        with request.urlopen(req, timeout=timeout) as resp:
            data = json.loads(resp.read().decode())
            return data["choices"][0]["message"]["content"]
    except error.HTTPError as e:
        raise RuntimeError(f"NIM HTTP {e.code}: {e.read().decode()[:200]}") from e


def judge_pair(a: dict, b: dict, *, criterion: str = "higher client impact") -> str:
    """Pairwise judge for council protocol. Returns 'A', 'B', or 'TIE'.

    Uses NIM with a tight contract; falls back to deterministic on failure.
    """
    prompt = f"""Two consulting findings — pick the one with {criterion}. Respond with strict JSON: {{"winner":"A"|"B"|"TIE","reason":"<10 words>"}}.

A: {json.dumps({k: v for k, v in a.items() if k not in ('embedding','cluster')})[:600]}

B: {json.dumps({k: v for k, v in b.items() if k not in ('embedding','cluster')})[:600]}"""
    try:
        text = call_nim(prompt, max_tokens=80, temperature=0.0)
        # Extract JSON
        import re
        m = re.search(r'\{[\s\S]*?\}', text)
        if not m:
            raise ValueError("no json")
        obj = json.loads(m.group(0))
        w = str(obj.get("winner", "TIE")).upper()
        return w if w in ("A", "B", "TIE") else "TIE"
    except Exception:
        # Fallback: deterministic
        if a.get("impact_usd", 0) > b.get("impact_usd", 0):
            return "A"
        if b.get("impact_usd", 0) > a.get("impact_usd", 0):
            return "B"
        return "TIE"


if __name__ == "__main__":
    print(call_nim("Reply with exactly: ready", max_tokens=10))
