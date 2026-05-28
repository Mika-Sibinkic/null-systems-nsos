"""
project_dispatch — PM-tier dispatch for project-execution commands.

    take care of <project>
    handle <project>
    pm <project>

This is the headline verb. When the operator addresses NSOS to handle a
project, this handler:

  1. Resolves the project name to a real folder under <PROJECTS_DIR>/.
  2. Loads compact project state (checkpoint, CLAUDE.md, MEMORY).
  3. WWOD-predicts the highest-leverage next action the operator would take.
  4. Opens a DoD record (dod_ledger) so success is binary at the leaf.
  5. Logs the prediction to predictions.jsonl with the gap_id "scope-of-dispatch".
  6. Replies with: predicted action + DoD + "reply 'go' to execute / correct to train".

Important: the handler does NOT execute project work synchronously — chat
channels expect a quick reply. Execution happens when the operator replies
'go' (or sends a follow-up verb like 'dispatch' / 'execute'); the daemon
picks that up via the existing thread context.

Each dispatch call emits both a prediction and a DoD; the post-hoc operator
reply ("go" / correction) becomes a high-signal training pair for WWOD.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

# Quality judge wraps the response with a quality gate. project-dispatch
# output is itself a prediction-with-evidence; gating it would just add
# latency for a response the operator is going to correct or confirm anyway.
SKIP_JUDGE = True

NSOS_DIR = Path(__file__).resolve().parent.parent
PROJECT_ROOT = NSOS_DIR.parent.parent
PROJECTS_DIR = Path(os.environ.get("NSOS_PROJECTS_DIR", str(PROJECT_ROOT / "projects")))
sys.path.insert(0, str(NSOS_DIR))


# ---------------------------------------------------------------------------
# project resolution
# ---------------------------------------------------------------------------

# Lower-case keyword -> real <PROJECTS_DIR>/ subfolder name. Override by
# writing NSOS_DIR/knowledge/project_map.json with the same shape.
def _load_project_map() -> Dict[str, str]:
    custom = NSOS_DIR / "knowledge" / "project_map.json"
    if custom.exists():
        try:
            with open(custom) as f:
                data = json.load(f)
            if isinstance(data, dict) and data:
                return {str(k).lower(): str(v) for k, v in data.items()}
        except (json.JSONDecodeError, IOError):
            pass
    return {}


PROJECT_MAP = _load_project_map()


def _resolve_project(token: str) -> Optional[str]:
    t = token.lower().strip().rstrip("?.!")
    if not t:
        return None
    if t in PROJECT_MAP:
        return PROJECT_MAP[t]
    for kw, proj in PROJECT_MAP.items():
        if kw in t or t in kw:
            return proj
    return None


def _parse_target(text: str) -> Optional[str]:
    """
    Accepts inputs like:
      "take care of <project>"
      "take care <project>"
      "take_care <project>"
      "tc <project>"
    Returns the project folder name or None.
    """
    cleaned = text.strip().lower()
    # Strip the verb form.
    for prefix in ("take care of ", "take care ", "take_care of ", "take_care ", "tc "):
        if cleaned.startswith(prefix):
            cleaned = cleaned[len(prefix):]
            break
    cleaned = cleaned.strip()
    if not cleaned:
        return None
    return _resolve_project(cleaned)


# ---------------------------------------------------------------------------
# state loading
# ---------------------------------------------------------------------------

def _safe_read(path: Path, max_chars: int) -> str:
    try:
        text = path.read_text(errors="ignore")
    except Exception:
        return ""
    return text[:max_chars]


def _load_project_state(project_folder: str, max_chars: int = 6000) -> Dict[str, Any]:
    """
    Load compact project state. Returns:
      {folder, files: {checkpoint, claude_md, memory_md}, snippets: <truncated>}
    """
    base = PROJECTS_DIR / project_folder
    if not base.exists():
        return {"folder": str(base), "exists": False, "snippets": ""}

    candidates = [
        ("checkpoint", base / "checkpoint.md"),
        ("CLAUDE", base / "CLAUDE.md"),
        ("HANDOFF", base / "HANDOFF.md"),
        ("context", base / "context.md"),
        ("MEMORY", base / "MEMORY.md"),
        ("PRD", base / "PRD.md"),
        ("status", base / "STATUS.md"),
    ]
    parts: List[str] = []
    files_present: Dict[str, bool] = {}
    remaining = max_chars
    for label, path in candidates:
        if not path.exists():
            files_present[label] = False
            continue
        files_present[label] = True
        if remaining <= 200:
            continue
        snippet = _safe_read(path, min(remaining, 1400))
        if snippet.strip():
            parts.append(f"--- {project_folder}/{path.name} ---\n{snippet.strip()}")
            remaining -= len(snippet)

    return {
        "folder": str(base),
        "exists": True,
        "files_present": files_present,
        "snippets": "\n\n".join(parts),
    }


def _load_framework_memory(project_folder: str, max_chars: int = 1200) -> str:
    """Pull project-relevant memory entries from the framework MEMORY.md.

    Override discovery roots via NSOS_MEMORY_PATHS (colon-separated).
    """
    env_paths = os.environ.get("NSOS_MEMORY_PATHS", "")
    candidates = [Path(p) for p in env_paths.split(":") if p.strip()]
    if not candidates:
        candidates = [
            PROJECT_ROOT / ".claude" / "memory" / "MEMORY.md",
            NSOS_DIR / "memory" / "MEMORY.md",
        ]
    folder_keywords = project_folder.lower().split()
    for c in candidates:
        if not c.exists():
            continue
        text = _safe_read(c, 12000)
        relevant = [
            line for line in text.splitlines()
            if any(kw in line.lower() for kw in folder_keywords)
        ]
        if relevant:
            return ("MEMORY entries for " + project_folder + ":\n" +
                    "\n".join(relevant))[:max_chars]
    return ""


# ---------------------------------------------------------------------------
# WWOD prediction + DoD
# ---------------------------------------------------------------------------

WWOD_SYSTEM = """You are NSOS predicting the operator's next action on a project they just asked you to dispatch.

Operator's verbatim heuristics that govern this prediction:
  - "Bias toward action" — pick something that ships, not something that plans.
  - "Real data, not synthetic" — verification only counts on production data.
  - "Output-driven iteration" — every fix needs a regression fixture; no speculative changes.
  - "Minimize manual work" — prefer doing it now over telling the operator to do it.
  - "Verify before you say done" — only assert progress with a firsthand evidence pointer.
  - "One-shot decisions when costs allow" — pick a single highest-leverage next action; don't enumerate options.

OUTPUT JSON ONLY in this exact shape:
{
  "next_action": "imperative single-sentence command of what to do next",
  "rationale": "1-2 sentences, citing the specific project state that drove this",
  "binary_dod": ["criterion 1", "criterion 2", ...],
  "ordinal_predicted": "rework|acceptable|excellent",
  "failure_modes": ["named risk 1", "named risk 2"],
  "estimated_time": "minutes|hours|days",
  "confidence": 0.0-1.0,
  "needs_operator": ["specific things only the operator can resolve, empty list if none"]
}

If the project has a deadline mentioned, weight that. If a regression test would close a known gap, weight that. If the last work was deployed inactive, "activate after verification" is a strong candidate. If the latest correspondence is a client question waiting for reply, drafting that reply may outrank code work."""


def _wwod_predict(project_folder: str, state_blob: str) -> Dict[str, Any]:
    """
    Call the LLM to predict next action. Returns parsed JSON or a heuristic
    fallback if the LLM is unavailable / returns malformed output.
    """
    try:
        from llm_adapter import call_llm  # type: ignore
    except Exception as e:
        return _heuristic_predict(project_folder, state_blob, reason=f"llm_unavailable:{type(e).__name__}")

    prompt = f"PROJECT: {project_folder}\n\nSTATE:\n{state_blob}\n\nPredict the single next action."
    try:
        raw = call_llm(prompt=prompt, system=WWOD_SYSTEM, tier="primary",
                       temperature=0.2, max_tokens=600)
    except Exception as e:
        return _heuristic_predict(project_folder, state_blob, reason=f"llm_call_failed:{type(e).__name__}")

    if not raw or not raw.strip():
        return _heuristic_predict(project_folder, state_blob, reason="llm_empty")

    txt = raw.strip()
    if txt.startswith("```"):
        txt = txt.strip("`")
        if txt.startswith("json\n"):
            txt = txt[5:]
    try:
        parsed = json.loads(txt)
        # minimal validation
        if "next_action" not in parsed:
            return _heuristic_predict(project_folder, state_blob, reason="llm_malformed")
        return parsed
    except json.JSONDecodeError:
        return _heuristic_predict(project_folder, state_blob, reason="llm_not_json")


def _heuristic_predict(project_folder: str, state_blob: str, reason: str) -> Dict[str, Any]:
    """
    Deterministic fallback. Picks the highest-leverage default given the
    project: if checkpoint exists, propose "resume checkpoint." Otherwise
    propose "load project state and write a checkpoint."
    """
    has_checkpoint = "checkpoint.md" in state_blob.lower()
    if has_checkpoint:
        action = (f"Resume the open checkpoint for {project_folder} — read checkpoint.md, "
                  f"identify the next-step block, and execute it; report outcome with evidence pointer.")
        dod = [
            "next-step from checkpoint.md is identified by name",
            "execution produces a verifiable artifact (commit hash, file path, or test output)",
            "regression suite runs and the run is recorded",
        ]
    else:
        action = (f"Audit {project_folder}'s current state and write a checkpoint.md capturing "
                  f"latest deployed version, open work, and immediate next step.")
        dod = [
            "checkpoint.md exists in the project folder",
            "checkpoint names the latest deployed version + URL or hash",
            "checkpoint identifies the single next action with binary success criteria",
        ]
    return {
        "next_action": action,
        "rationale": f"Heuristic fallback ({reason}) — picked the lowest-risk concrete next step.",
        "binary_dod": dod,
        "ordinal_predicted": "acceptable",
        "failure_modes": ["scope drift", "stale state assumed current"],
        "estimated_time": "minutes",
        "confidence": 0.4,
        "needs_operator": [],
        "_fallback": True,
    }


# ---------------------------------------------------------------------------
# logging
# ---------------------------------------------------------------------------

def _log_prediction(project_folder: str, prediction: Dict[str, Any], dod_id: str) -> str:
    """Append a record to predictions.jsonl."""
    pred_file = NSOS_DIR / "predictions.jsonl"
    from datetime import datetime, timezone
    record = {
        "timestamp": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "kind": "project_dispatch_prediction",
        "gap_id": "gap-scope-of-dispatch",  # the "scope of dispatch project" gap
        "project": project_folder,
        "situation": f"operator dispatched: {project_folder.lower()}",
        "predicted": prediction.get("next_action"),
        "rationale": prediction.get("rationale"),
        "confidence": prediction.get("confidence"),
        "dod_id": dod_id,
        "outcome": "predicted",  # updated to "confirmed"|"corrected"|"rejected" on operator reply
    }
    try:
        pred_file.parent.mkdir(parents=True, exist_ok=True)
        with open(pred_file, "a", encoding="utf-8") as f:
            f.write(json.dumps(record) + "\n")
    except Exception:
        pass  # don't fail the user-facing reply over a log write
    return record["timestamp"]


# ---------------------------------------------------------------------------
# entry
# ---------------------------------------------------------------------------

def handle(envelope: dict) -> str:
    text = (envelope.get("text") or "").strip()
    project = _parse_target(text)

    if not project:
        known = ", ".join(sorted(set(PROJECT_MAP.values()))) if PROJECT_MAP else "(no projects mapped — see knowledge/project_map.json)"
        return ("usage: take care of <project>\n"
                "known: " + known)

    state = _load_project_state(project)
    if not state.get("exists"):
        return (f"project folder not found: {PROJECTS_DIR}/{project}\n"
                f"(resolved from: {text!r})")

    framework_mem = _load_framework_memory(project)
    state_blob = (state["snippets"] or "(no project state files)") + (
        ("\n\n" + framework_mem) if framework_mem else ""
    )

    prediction = _wwod_predict(project, state_blob)

    # Open a DoD so success is binary.
    try:
        import dod_ledger
        dod = dod_ledger.open_dod(
            scope="task",
            scope_id=f"take_care:{project.lower().replace(' ', '_')}",
            parent_id=f"project:{project.lower().replace(' ', '_')}",
            binary_criteria=prediction.get("binary_dod", []),
            ordinal_predicted=prediction.get("ordinal_predicted"),
            failure_modes=[
                {"name": fm, "description": "", "detected": False}
                for fm in prediction.get("failure_modes", [])
            ],
            rationale=prediction.get("rationale", ""),
            skip_wwod=False,  # let dod_ledger run its own operator-DoD prediction
        )
        dod_id = dod["id"]
    except Exception as e:
        dod_id = "(dod_ledger unavailable: " + type(e).__name__ + ")"

    pred_ts = _log_prediction(project, prediction, dod_id)

    # Compose operator-facing reply.
    confidence_pct = int(round((prediction.get("confidence") or 0.0) * 100))
    needs_operator = prediction.get("needs_operator") or []
    fallback_tag = " [FALLBACK PREDICTION]" if prediction.get("_fallback") else ""

    lines = [
        f"taking care of {project}{fallback_tag}",
        "",
        f"NEXT ACTION ({confidence_pct}% conf):",
        prediction.get("next_action", "(no action predicted)"),
        "",
        "WHY:",
        prediction.get("rationale", ""),
        "",
        "DoD (binary):",
    ]
    for c in prediction.get("binary_dod", []):
        lines.append(f"  • {c}")
    if prediction.get("ordinal_predicted"):
        lines.append(f"target tier: {prediction['ordinal_predicted']}")
    if prediction.get("failure_modes"):
        lines.append("watching for: " + ", ".join(prediction["failure_modes"]))
    if needs_operator:
        lines.append("")
        lines.append("NEEDS OPERATOR:")
        for n in needs_operator:
            lines.append(f"  - {n}")
    lines.append("")
    lines.append(f"reply 'go' to execute, or correct.  [pred {pred_ts} / dod {dod_id}]")
    return "\n".join(lines)
