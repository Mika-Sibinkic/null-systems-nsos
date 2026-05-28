"""nim_worker.py — every task_spec from the orchestrator flows through here.

Lint guard: this is the ONLY module besides engine/router/nim_client.py that
imports an LLM client. Everything else is forbidden.
"""
from __future__ import annotations
import sys, json, os
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Sequence

# Import the canonical NIM client
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from engine.router.nim_client import call_nim  # noqa: E402


def execute(spec: dict, *, timeout: int = 90) -> dict:
    """Run a single task_spec. Returns {result, error, model, took_ms}."""
    import time
    start = time.monotonic()
    try:
        text = call_nim(
            spec["prompt"],
            model=spec["model"],
            max_tokens=int(spec.get("max_tokens", 800)),
            temperature=float(spec.get("temperature", 0.3)),
            timeout=timeout,
        )
        return {
            "result": text,
            "error": None,
            "model": spec["model"],
            "took_ms": int((time.monotonic() - start) * 1000),
        }
    except Exception as e:
        return {
            "result": None,
            "error": str(e)[:500],
            "model": spec.get("model", ""),
            "took_ms": int((time.monotonic() - start) * 1000),
        }


def execute_all(specs: Sequence[dict], *, parallel: int = 4) -> list[dict]:
    """Run multiple task_specs in parallel (bounded). Preserves order."""
    if len(specs) <= 1:
        return [execute(s) for s in specs]
    results: list[dict | None] = [None] * len(specs)
    with ThreadPoolExecutor(max_workers=parallel) as ex:
        futures = {ex.submit(execute, s): i for i, s in enumerate(specs)}
        for fut in as_completed(futures):
            results[futures[fut]] = fut.result()
    return [r for r in results if r is not None]


def combine(results: Sequence[dict], post_processing: str | None) -> str:
    """Default combiner — concat results with headers. If post_processing is
    'final-only', return last result only. For richer combining, the
    orchestrator should produce another task_spec rather than relying on string
    logic here.
    """
    if not results:
        return "(no results)"
    if post_processing == "final-only":
        return results[-1].get("result") or results[-1].get("error", "(no output)")
    parts = []
    for i, r in enumerate(results, 1):
        if r.get("error"):
            parts.append(f"--- task {i} (model: {r['model']}) — ERROR ---\n{r['error']}")
        else:
            parts.append(f"--- task {i} (model: {r['model']}, {r['took_ms']}ms) ---\n{r['result']}")
    return "\n\n".join(parts)


if __name__ == "__main__":
    spec = {
        "worker": "nim",
        "model": "meta/llama-3.3-70b-instruct",
        "prompt": "Reply with exactly: ready",
        "max_tokens": 10,
        "temperature": 0.0,
    }
    print(json.dumps(execute(spec), indent=2))
