"""
ask — natural-language Q&A grounded in NSOS's actual state.

    nsos ask "what's the latest on jetloan"

Fallback handler for NL channels (email, telegram, imessage) when the
first word isn't a registered verb. Before asking the LLM, this pulls a
compact state snapshot from predictions.jsonl, gaps.jsonl, MEMORY.md,
and any available project checkpoint/memory files — so the model
ANSWERS FROM EVIDENCE instead of inventing plausible-sounding status.

SKIP_JUDGE is True: the judge adds a second LLM call (~15s on free NIM)
for a gating decision that's low-value on conversational NL. Mika can
correct in-thread and the correction feeds the learning loop.
"""

import json
import sys
from pathlib import Path
from typing import Any, Dict, List

# Skip the quality judge — conversational latency wins over pre-gating.
SKIP_JUDGE = True

NSOS_DIR = Path(__file__).resolve().parent.parent
PROJECT_ROOT = NSOS_DIR.parent.parent
sys.path.insert(0, str(NSOS_DIR))


ASK_SYSTEM = """You are NSOS — the reasoning system behind Null Systems, Mika Sibinkic's solo AI-augmented consulting practice.

Answer Mika's question in his voice: terse, no permission-seeking, no hedging, no filler. Two-to-five sentences max unless the question explicitly needs more.

CRITICAL: Only state facts that appear in the EVIDENCE block below. If the evidence doesn't cover the question, say "I don't have current data on that — last checkpoint was [date] and only covers [list]." Do NOT invent project status, built features, client conversations, dates, or numbers. Uncertainty is fine; hallucination is a failure.

Be specific when grounded. Reference real projects (a lending client, a marketing client, a consulting client, a client, Sourcing Specialist, Whistle, AJM, Aperture/a vision project, AI Flat-Filler) by name when they apply. Never use words like "thrilled", "excited", "delighted". Never open with "I".

If the question is a follow-up ("what about X?", "done yet?") use the thread context to resolve it."""


def _load_jsonl_tail(path: Path, limit: int) -> List[Dict[str, Any]]:
    if not path.exists():
        return []
    out: List[Dict[str, Any]] = []
    try:
        with open(path) as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    out.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
    except Exception:
        return []
    return out[-limit:]


def _safe_read(path: Path, max_chars: int) -> str:
    try:
        text = path.read_text(errors="ignore")
    except Exception:
        return ""
    return text[:max_chars]


def _detect_projects(question: str) -> List[str]:
    """Return real project-folder names mentioned in the question."""
    q = question.lower()
    mapping = {
        "jetloan": "a lending client",
        "microscout": "a marketing client",
        "sava": "a consulting client",
        "adrema": "a client",
        "sourcing": "Sourcing Specialist",
        "whistle": "Whistle",
        "ajm": "AJM",
        "aperture": "a vision project",
        "branch cam": "a vision project",
        "branch-cam": "a vision project",
        "flat-filler": "AI Flat-Filler",
        "flat filler": "AI Flat-Filler",
        "tunedrop": "TuneDropAI",
        "nsos": "NSOS",
    }
    found: List[str] = []
    for kw, proj in mapping.items():
        if kw in q and proj not in found:
            found.append(proj)
    return found


def _project_state_snippet(project: str, max_chars: int = 1400) -> str:
    """Read the most recent checkpoint/CLAUDE.md/HANDOFF from a project folder."""
    base = PROJECT_ROOT / "Active Projects" / project
    if not base.exists():
        return ""
    candidates = [
        base / "checkpoint.md",
        base / "CLAUDE.md",
        base / "HANDOFF.md",
        base / "context.md",
        base / "MEMORY.md",
    ]
    parts: List[str] = []
    remaining = max_chars
    for c in candidates:
        if not c.exists() or remaining <= 200:
            continue
        snippet = _safe_read(c, min(remaining, 700))
        if snippet.strip():
            parts.append(f"--- {project}/{c.name} ---\n{snippet.strip()}")
            remaining -= len(snippet)
    return "\n\n".join(parts)


def _global_state_snippet(max_chars: int = 1200) -> str:
    """Recent NSOS state + memory index (always included)."""
    parts: List[str] = []

    # Most recent gap predictions
    preds = _load_jsonl_tail(NSOS_DIR / "predictions.jsonl", 3)
    if preds:
        lines = ["RECENT NSOS PREDICTIONS (what the model thought Mika would want):"]
        for p in preds:
            ts = (p.get("timestamp") or "")[:10]
            q = (p.get("situation") or p.get("question") or "")[:120]
            pred = (p.get("prediction") or "")[:200]
            if q and pred:
                lines.append(f"  [{ts}] gap={p.get('gap_id','?')}: {q} → {pred}")
        parts.append("\n".join(lines))

    # Open reasoning gaps
    gaps = _load_jsonl_tail(NSOS_DIR / "gaps.jsonl", 10)
    open_gaps = [g for g in gaps if g.get("status") == "detected"][-5:]
    if open_gaps:
        lines = ["OPEN REASONING GAPS (things NSOS explicitly doesn't know):"]
        for g in open_gaps[:3]:
            lines.append(f"  - {g.get('category','?')}: {g.get('description','')[:160]}")
        parts.append("\n".join(lines))

    # Framework-level memory index (titles only)
    mem_index = PROJECT_ROOT / ".claude" / "memory" / "MEMORY.md"
    if not mem_index.exists():
        mem_index = Path.home() / ".claude" / "projects" / "-Users-operator-Desktop-Null-Systems-business-framework" / "memory" / "MEMORY.md"
    if mem_index.exists():
        mem = _safe_read(mem_index, 800)
        if mem:
            parts.append("MEMORY INDEX:\n" + mem)

    full = "\n\n".join(parts)
    return full[:max_chars]


def _build_evidence(question: str) -> str:
    """Compose the EVIDENCE block — everything the model is allowed to cite."""
    blocks: List[str] = []

    for proj in _detect_projects(question):
        snip = _project_state_snippet(proj, max_chars=1400)
        if snip:
            blocks.append(snip)

    g = _global_state_snippet(max_chars=1200)
    if g:
        blocks.append(g)

    if not blocks:
        return "(no project-specific or recent state available)"
    return "\n\n".join(blocks)[:5000]


def handle(envelope: dict) -> str:
    try:
        from llm_adapter import call_llm
    except Exception as e:
        return f"(ask unavailable: llm_adapter import failed: {e})"

    text = envelope.get("text") or ""
    parts = text.split(None, 1)
    if parts and parts[0].lower() == "ask" and len(parts) > 1:
        body = parts[1].strip()
    else:
        body = text.strip()

    if not body:
        return "usage: ask <your question>"

    # Thread context
    thread = envelope.get("thread") or []
    if thread:
        lines = []
        for t in thread[-5:]:
            user = (t.get("user_text") or "").strip().replace("\n", " ")[:200]
            resp = (t.get("response") or "").strip().replace("\n", " ")[:300]
            if user:
                lines.append(f"Mika: {user}")
            if resp:
                lines.append(f"NSOS: {resp}")
        context_block = "RECENT CONVERSATION ON THIS CHANNEL:\n" + "\n".join(lines) + "\n\n"
    else:
        context_block = ""

    # Grounding — the only source of truth the model is allowed to cite
    evidence = _build_evidence(body)
    evidence_block = f"EVIDENCE (only cite facts from this section):\n{evidence}\n\n"

    prompt = f"{context_block}{evidence_block}QUESTION: {body}"
    try:
        response = call_llm(
            prompt=prompt,
            system=ASK_SYSTEM,
            tier="primary",
            temperature=0.2,  # lower — less creative invention
            max_tokens=600,
        )
    except Exception as e:
        return f"(ask failed: {type(e).__name__}: {e})"

    if not response or not response.strip():
        return "(empty answer from model — try rephrasing)"
    return response.strip()
