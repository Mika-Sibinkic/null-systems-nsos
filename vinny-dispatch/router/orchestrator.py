"""orchestrator.py — ONLY place in the codebase that may invoke Claude Code.

Claude is the decision-maker:
  - classifies user intent from raw command
  - decomposes into deterministic NIM-compatible task specs
  - is FORBIDDEN from acting (zero tools allowed)

Output contract (strict JSON):
  {
    "intent": "<short label>",
    "task_specs": [
      {
        "worker": "nim",                         # only "nim" is allowed
        "model": "meta/llama-3.3-70b-instruct",  # must start with "meta/" or other NIM-served prefix
        "prompt": "...",
        "max_tokens": 800,
        "temperature": 0.3
      },
      ...
    ],
    "post_processing": "<optional one-line description of how to combine outputs>"
  }

Anything else from Claude is a contract violation → reject.
"""
from __future__ import annotations
import json, os, re, subprocess
from pathlib import Path
from typing import TypedDict

CLAUDE_BIN = os.environ.get("VINNY_CLAUDE_BIN", "claude")
ALLOWED_MODEL_PREFIXES = (
    "meta/",
    "deepseek-ai/",
    "mistralai/",
    "google/",
    "nvidia/",
    "qwen/",
)

CLASSIFIER_SYSTEM = """You are the Vinny dispatch orchestrator. You are NOT a worker LLM. You do NOT execute anything. You ONLY decompose user commands into a JSON plan that downstream NIM workers will execute.

Available NIM models:
- meta/llama-3.3-70b-instruct (default, fast)
- meta/llama-3.1-405b-instruct (slower, better reasoning)

Output STRICT JSON with this shape — nothing else, no prose, no fences:
{"intent":"<short label>","task_specs":[{"worker":"nim","model":"<from list>","prompt":"<self-contained prompt>","max_tokens":<int>,"temperature":<0.0-1.0>}],"post_processing":"<one-line summary of how to combine outputs, or null>"}

Rules:
1. Each task_spec.prompt must be SELF-CONTAINED — the NIM worker sees only that string, no context from the user command, no memory.
2. If the user command is simple (1 question), produce 1 task_spec.
3. If it requires parallel sub-tasks (e.g., "research X across 3 sources"), produce 1 task_spec per sub-task.
4. Never include shell commands, file paths, or executable code in prompts unless the goal is to ANALYZE that code.
5. If the user command is destructive (delete, drop, rm -rf), set intent to "REJECT_DESTRUCTIVE" and task_specs to [].
"""


class TaskSpec(TypedDict):
    worker: str
    model: str
    prompt: str
    max_tokens: int
    temperature: float


class Plan(TypedDict):
    intent: str
    task_specs: list[TaskSpec]
    post_processing: str | None


def _strip_fences(text: str) -> str:
    text = text.strip()
    # Remove ```json ... ``` or ``` ... ``` wrappers
    m = re.search(r'```(?:json)?\s*([\s\S]*?)```', text)
    if m:
        return m.group(1).strip()
    return text


def classify(command: str, *, timeout: int = 60) -> Plan:
    """Invoke Claude Code headless to produce a plan. Returns Plan or raises."""
    user_prompt = f"USER COMMAND:\n{command}\n\nReturn the JSON plan."
    args = [
        CLAUDE_BIN,
        "-p", user_prompt,
        "--output-format", "json",
        "--system-prompt", CLASSIFIER_SYSTEM,
        "--allowed-tools", "",  # zero tools — cannot execute anything
    ]
    try:
        result = subprocess.run(args, capture_output=True, text=True, timeout=timeout)
    except FileNotFoundError as e:
        raise RuntimeError(f"claude CLI not found ({CLAUDE_BIN}): {e}")
    if result.returncode != 0:
        raise RuntimeError(f"claude exit {result.returncode}: {result.stderr[:300]}")

    # claude --output-format json returns a wrapper; extract the model's text
    raw = result.stdout.strip()
    try:
        wrapper = json.loads(raw)
        text = wrapper.get("result") or wrapper.get("text") or wrapper.get("content") or raw
    except json.JSONDecodeError:
        text = raw

    plan_text = _strip_fences(text if isinstance(text, str) else json.dumps(text))
    try:
        plan = json.loads(plan_text)
    except json.JSONDecodeError as e:
        raise RuntimeError(f"orchestrator returned non-JSON: {plan_text[:200]}") from e

    _validate_plan(plan)
    return plan  # type: ignore


def _validate_plan(plan: dict) -> None:
    if not isinstance(plan, dict):
        raise ValueError("plan is not a dict")
    if "intent" not in plan or "task_specs" not in plan:
        raise ValueError("plan missing intent or task_specs")
    if plan["intent"] == "REJECT_DESTRUCTIVE":
        return  # acceptable, empty task_specs
    for i, spec in enumerate(plan["task_specs"]):
        if not isinstance(spec, dict):
            raise ValueError(f"task_spec[{i}] is not a dict")
        if spec.get("worker") != "nim":
            raise ValueError(f"task_spec[{i}].worker must be 'nim', got {spec.get('worker')!r}")
        model = spec.get("model", "")
        if not any(model.startswith(p) for p in ALLOWED_MODEL_PREFIXES):
            raise ValueError(f"task_spec[{i}].model {model!r} not in allowed prefixes")
        if not isinstance(spec.get("prompt", ""), str) or not spec["prompt"]:
            raise ValueError(f"task_spec[{i}].prompt missing or empty")


if __name__ == "__main__":
    import sys
    cmd = " ".join(sys.argv[1:]) or "Summarize what NSOS does in 2 sentences."
    plan = classify(cmd)
    print(json.dumps(plan, indent=2))
