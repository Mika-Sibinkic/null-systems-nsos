"""nim_client.py — the one model client in NSOS (CLAUDE.md rule 3).

The only caller today is the quality judge (engine/gauntlets/quality_judge.py).
Default model: meta/llama-3.3-70b-instruct (NIM_PRIMARY_MODEL).
"""
from __future__ import annotations
import os, json
from urllib import request, error

NIM_BASE = os.environ.get("NIM_BASE_URL", "https://integrate.api.nvidia.com/v1")
PRIMARY_MODEL = os.environ.get("NIM_PRIMARY_MODEL", "meta/llama-3.3-70b-instruct")


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
