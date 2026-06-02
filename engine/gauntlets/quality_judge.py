#!/usr/bin/env python3
"""
NSOS Quality Judge — 3-layer output quality system.

Layer 1 (rubric scoring): every NSOS output is scored via one fast-tier LLM
call against four dimensions — relevance, actionability, calibration,
confidence. Prometheus-style rubric-as-system-prompt, output-as-user-prompt.
Rubric and thresholds are loaded from quality_rules.json (operator-agnostic).

Layer 2 (preference memory): score + output + eventual operator response get
logged to SQLite (nsos_quality_log). Training signal for later tuning.

Layer 3 (confidence gate): if scores fall below threshold, the normal
response is replaced by a confirmation prompt ("I found X but I'm not
confident — worth looking at?"). The yes/no answer on the same channel
resolves the gate, and the resolution is captured as a preference signal.

Router integration: see router.py — `apply()` wraps every handler response
except handlers that opt out via SKIP_JUDGE = True.

Fails open: if the LLM call raises, the output still surfaces (the judge
is advisory, not load-bearing). The failure is logged.
"""

from __future__ import annotations

import json
import os
import re
import sqlite3
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

NSOS_DIR = Path(__file__).resolve().parent
DB_PATH = NSOS_DIR / "quality.db"
LOGS_DIR = NSOS_DIR / "logs"
RULES_PATH = NSOS_DIR / "quality_rules.json"

# Identity (parameterized — defaults to generic strings)
OPERATOR_NAME = os.environ.get("OPERATOR_NAME", "operator")
COMPANY_NAME = os.environ.get("COMPANY_NAME", "the firm")


def _load_rules() -> Dict[str, Any]:
    """Load rubric + thresholds from quality_rules.json. Returns empty dict on failure."""
    try:
        with open(RULES_PATH) as f:
            return json.load(f)
    except Exception:
        return {}


_RULES = _load_rules()


def _sub(text: str) -> str:
    """Substitute identity tokens in a rule string."""
    return text.replace("{OPERATOR_NAME}", OPERATOR_NAME).replace("{COMPANY_NAME}", COMPANY_NAME)


def _build_rubric_prompt() -> str:
    """Compose the rubric system prompt from the loaded rules + identity tokens."""
    if not _RULES:
        # Minimal fallback if quality_rules.json is missing.
        return (
            f"You are a quality judge for NSOS, the reasoning system powering {COMPANY_NAME} "
            f"({OPERATOR_NAME}'s AI-augmented consulting practice).\n\n"
            'Return ONLY a JSON object: {"relevance": <int 0-5>, "actionability": <int 0-5>, '
            '"calibration": <int 0-5>, "confidence": <float 0.0-1.0>, "reasoning": "<...>"}'
        )
    intro = _sub(_RULES.get("rubric_intro", ""))
    schema = json.dumps(_RULES.get("output_schema", {}), indent=2)
    dim_lines = "\n".join(
        f"- {name} ({_sub(desc)})" for name, desc in _RULES.get("dimensions", {}).items()
    )
    note = _sub(_RULES.get("calibration_note", ""))
    return (
        f"{intro}\n\n"
        "Score the output below across four dimensions. Return ONLY a JSON object with this exact shape, "
        "no prose, no markdown fences:\n\n"
        f"{schema}\n\n"
        "Dimensions:\n"
        f"{dim_lines}\n\n"
        f"{note}"
    )


# ── thresholds (loaded from quality_rules.json; env vars override) ──────────
#
# Gate condition: output is withheld from the user if EITHER
#   (relevance + actionability + calibration) < SUM_THRESHOLD
# OR confidence < CONF_THRESHOLD.
_THRESH = _RULES.get("thresholds", {})
SUM_THRESHOLD = float(os.environ.get("NSOS_JUDGE_SUM_THRESHOLD", str(_THRESH.get("sum_threshold", 9))))
CONF_THRESHOLD = float(os.environ.get("NSOS_JUDGE_CONF_THRESHOLD", str(_THRESH.get("confidence_threshold", 0.5))))

# ── LLM routing ─────────────────────────────────────────────────────────────
# Defaults to fast tier. Rubric is terse; expect <150 tokens.
_JUDGE_CALL = _RULES.get("judge_call", {})
JUDGE_TIER = _JUDGE_CALL.get("tier", "fast")
JUDGE_MAX_TOKENS = int(_JUDGE_CALL.get("max_tokens", 400))
JUDGE_TEMPERATURE = float(_JUDGE_CALL.get("temperature", 0.1))

RUBRIC_PROMPT = _build_rubric_prompt()


def _call_judge_llm(prompt: str) -> Optional[str]:
    """Run the rubric call via the configured fast tier. Returns raw string or None on failure."""
    try:
        sys.path.insert(0, str(NSOS_DIR))
        from llm_adapter import call_llm  # noqa: WPS433
    except Exception as e:
        _log_judge_error(f"llm_adapter import failed: {e}")
        return None
    try:
        return call_llm(
            prompt=prompt,
            system=RUBRIC_PROMPT,
            tier=JUDGE_TIER,
            temperature=JUDGE_TEMPERATURE,
            max_tokens=JUDGE_MAX_TOKENS,
        )
    except Exception as e:
        _log_judge_error(f"call_llm failed: {e}")
        return None


def _parse_judge_json(raw: Optional[str]) -> Optional[Dict[str, Any]]:
    """Extract the rubric JSON from a potentially-messy LLM response."""
    if not raw:
        return None
    text = raw.strip()
    text = re.sub(r"^```json?\s*|\s*```$", "", text, flags=re.MULTILINE).strip()
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        match = re.search(r"\{[^{}]*\"relevance\"[\s\S]*?\}", text)
        if not match:
            return None
        try:
            parsed = json.loads(match.group(0))
        except json.JSONDecodeError:
            return None
    required = {"relevance", "actionability", "calibration", "confidence"}
    if not required.issubset(parsed.keys()):
        return None
    try:
        parsed["relevance"] = int(parsed["relevance"])
        parsed["actionability"] = int(parsed["actionability"])
        parsed["calibration"] = int(parsed["calibration"])
        parsed["confidence"] = float(parsed["confidence"])
    except (TypeError, ValueError):
        return None
    parsed["reasoning"] = str(parsed.get("reasoning", "")).strip()[:400]
    return parsed


def score(output_text: str, context: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Score an NSOS output. Never raises — returns a dict with status + scores.

    On judge-unavailable (provider down, parse failure), returns status='unavailable'
    with neutral scores that fail-open (do NOT gate).
    """
    ctx_lines = []
    if context:
        src = context.get("source")
        if src:
            ctx_lines.append(f"channel: {src}")
        verb = context.get("verb")
        if verb:
            ctx_lines.append(f"verb: {verb}")
        user_text = context.get("user_text")
        if user_text:
            ctx_lines.append(f"user said: {user_text[:200]}")
    ctx_block = ("CONTEXT:\n" + "\n".join(ctx_lines) + "\n\n") if ctx_lines else ""
    prompt = f"{ctx_block}NSOS OUTPUT:\n{output_text[:3000]}"

    raw = _call_judge_llm(prompt)
    parsed = _parse_judge_json(raw)
    if parsed is None:
        return {
            "status": "unavailable",
            "relevance": None,
            "actionability": None,
            "calibration": None,
            "confidence": None,
            "reasoning": "judge call failed or returned unparseable JSON",
            "raw": (raw[:500] if raw else None),
        }
    parsed["status"] = "ok"
    parsed["raw"] = raw
    return parsed


def gate_decision(scores: Dict[str, Any]) -> bool:
    """Return True if output should be SUPPRESSED (gated), False to surface normally.

    Fails open on unavailable judge — always surface when we can't score.
    """
    if scores.get("status") != "ok":
        return False
    r = scores.get("relevance") or 0
    a = scores.get("actionability") or 0
    c = scores.get("calibration") or 0
    conf = scores.get("confidence") or 0.0
    if (r + a + c) < SUM_THRESHOLD:
        return True
    if conf < CONF_THRESHOLD:
        return True
    return False


# ── SQLite storage ──────────────────────────────────────────────────────────


def _db() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(DB_PATH))
    conn.execute("""
        CREATE TABLE IF NOT EXISTS nsos_quality_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TEXT NOT NULL,
            envelope_id TEXT,
            channel TEXT,
            sender_id TEXT,
            verb TEXT,
            user_text TEXT,
            output_text TEXT,
            output_suppressed INTEGER DEFAULT 0,
            judge_status TEXT,
            judge_relevance INTEGER,
            judge_actionability INTEGER,
            judge_calibration INTEGER,
            judge_confidence REAL,
            judge_reasoning TEXT,
            judge_raw_json TEXT,
            operator_response TEXT,
            response_timestamp TEXT
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS nsos_gate_pending (
            id TEXT PRIMARY KEY,
            created_at TEXT NOT NULL,
            channel TEXT NOT NULL,
            sender_id TEXT NOT NULL,
            original_output TEXT NOT NULL,
            quality_log_id INTEGER,
            resolved_at TEXT,
            resolution TEXT
        )
    """)
    conn.execute("""
        CREATE INDEX IF NOT EXISTS idx_gate_pending_open
        ON nsos_gate_pending (channel, sender_id, resolved_at)
    """)
    conn.commit()
    return conn


def log_judgment(
    *,
    envelope: Dict[str, Any],
    verb: str,
    output_text: str,
    suppressed: bool,
    scores: Dict[str, Any],
) -> int:
    """Insert a row into nsos_quality_log. Returns the new rowid."""
    with _db() as conn:
        cur = conn.execute(
            """
            INSERT INTO nsos_quality_log
            (timestamp, envelope_id, channel, sender_id, verb, user_text,
             output_text, output_suppressed,
             judge_status, judge_relevance, judge_actionability,
             judge_calibration, judge_confidence, judge_reasoning, judge_raw_json)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                datetime.now(timezone.utc).isoformat(),
                envelope.get("id"),
                envelope.get("source"),
                envelope.get("sender_id"),
                verb,
                envelope.get("text"),
                output_text,
                1 if suppressed else 0,
                scores.get("status"),
                scores.get("relevance"),
                scores.get("actionability"),
                scores.get("calibration"),
                scores.get("confidence"),
                scores.get("reasoning"),
                json.dumps(scores, default=str),
            ),
        )
        rowid = cur.lastrowid
        conn.commit()
    return int(rowid)


def open_gate(
    *,
    envelope: Dict[str, Any],
    original_output: str,
    quality_log_id: int,
) -> str:
    """Register a pending gate. Returns the gate id."""
    gid = f"gate_{uuid.uuid4().hex[:12]}"
    with _db() as conn:
        conn.execute(
            """
            INSERT INTO nsos_gate_pending
            (id, created_at, channel, sender_id, original_output, quality_log_id)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                gid,
                datetime.now(timezone.utc).isoformat(),
                envelope["source"],
                envelope["sender_id"],
                original_output,
                quality_log_id,
            ),
        )
        conn.commit()
    return gid


def find_open_gate(channel: str, sender_id: str) -> Optional[Tuple[str, str, int]]:
    """Return (gate_id, original_output, quality_log_id) for most-recent open
    gate on this channel/sender, or None if none pending."""
    with _db() as conn:
        cur = conn.execute(
            """
            SELECT id, original_output, quality_log_id
            FROM nsos_gate_pending
            WHERE channel = ? AND sender_id = ? AND resolved_at IS NULL
            ORDER BY created_at DESC LIMIT 1
            """,
            (channel, sender_id),
        )
        row = cur.fetchone()
    if not row:
        return None
    return (row[0], row[1], int(row[2]) if row[2] is not None else 0)


def resolve_gate(gate_id: str, resolution: str, quality_log_id: Optional[int]) -> None:
    """Record gate resolution and mirror it into the preference log."""
    now = datetime.now(timezone.utc).isoformat()
    with _db() as conn:
        conn.execute(
            "UPDATE nsos_gate_pending SET resolved_at = ?, resolution = ? WHERE id = ?",
            (now, resolution, gate_id),
        )
        if quality_log_id:
            operator_response = "acted_on" if resolution == "yes" else "dismissed"
            conn.execute(
                "UPDATE nsos_quality_log SET operator_response = ?, response_timestamp = ? WHERE id = ?",
                (operator_response, now, quality_log_id),
            )
        conn.commit()


# ── router integration ─────────────────────────────────────────────────────


def apply(
    *,
    envelope: Dict[str, Any],
    verb: str,
    response: str,
    skip: bool,
) -> Tuple[str, Dict[str, Any]]:
    """Run scoring and gating on a handler response.

    Returns (final_response_for_user, decision_metadata).

    If `skip` is True (handler opted out), the response is passed through
    untouched and no DB row is written.
    """
    if skip:
        return response, {"skipped": True}

    scores = score(
        response,
        context={
            "source": envelope.get("source"),
            "verb": verb,
            "user_text": envelope.get("text"),
        },
    )
    gated = gate_decision(scores)
    log_id = log_judgment(
        envelope=envelope,
        verb=verb,
        output_text=response,
        suppressed=gated,
        scores=scores,
    )
    if not gated:
        return response, {"gated": False, "scores": scores, "quality_log_id": log_id}

    # Gated: register a pending gate and return the confirmation prompt instead.
    summary = response.strip().split("\n")[0][:200]
    open_gate(envelope=envelope, original_output=response, quality_log_id=log_id)
    prompt = (
        f"found: {summary}\n"
        f"low confidence on relevance — show full? (yes / no)"
    )
    return prompt, {"gated": True, "scores": scores, "quality_log_id": log_id}


def maybe_resolve_gate_reply(envelope: Dict[str, Any]) -> Optional[str]:
    """If the envelope's text is a yes/no resolving an open gate for this
    channel+sender, resolve it and return the reply to send back. Else None."""
    text = (envelope.get("text") or "").strip().lower()
    if text not in {"yes", "y", "no", "n"}:
        return None
    gate = find_open_gate(envelope["source"], envelope["sender_id"])
    if not gate:
        return None
    gate_id, original_output, quality_log_id = gate
    if text in {"yes", "y"}:
        resolve_gate(gate_id, "yes", quality_log_id)
        return original_output
    resolve_gate(gate_id, "no", quality_log_id)
    return "suppressed; logged as not-worth-surfacing"


# ── internal error logging ──────────────────────────────────────────────────


def _log_judge_error(msg: str) -> None:
    LOGS_DIR.mkdir(parents=True, exist_ok=True)
    with open(LOGS_DIR / "judge-errors.log", "a") as f:
        f.write(f"{datetime.now(timezone.utc).isoformat()} {msg}\n")


# ── CLI for standalone testing ──────────────────────────────────────────────


def main() -> int:
    import argparse
    p = argparse.ArgumentParser(description="NSOS Quality Judge — standalone test")
    p.add_argument("--text", required=True, help="Output text to score")
    p.add_argument("--channel", default="cli")
    p.add_argument("--verb", default="manual")
    p.add_argument("--user-text", default="")
    p.add_argument("--gate", action="store_true",
                   help="Build-gate mode: exit 1 if the output is gated OR the judge is unavailable (fail-CLOSED).")
    args = p.parse_args()
    scores = score(
        args.text,
        context={"source": args.channel, "verb": args.verb, "user_text": args.user_text},
    )
    gated = gate_decision(scores)
    print(json.dumps({"scores": scores, "gated": gated}, indent=2, default=str))
    if args.gate:
        # Fail-closed for the build pipeline: an unscoreable output must NOT pass silently.
        if scores.get("status") != "ok":
            print("GATE: FAIL — judge unavailable (fail-closed)", file=sys.stderr)
            return 1
        if gated:
            print("GATE: FAIL — output below quality threshold", file=sys.stderr)
            return 1
        print("GATE: PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
