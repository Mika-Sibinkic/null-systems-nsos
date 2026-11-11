#!/usr/bin/env python3
"""
NSOS quality judge: a rubric scorer for client-facing text.

Live mode: one call through engine/router/nim_client.py scores the text on
relevance, actionability, calibration (0-5) and confidence (0-1), against the
rubric in quality_rules.json. gate_decision() then says whether to hold it.

Offline mode (NSOS_JUDGE_OFFLINE_DETERMINISTIC=1, used by the tests and the
demo): no model call at all. _deterministic_score() is a structural regex check
for a dollar or hour figure, an evidence word, a confidence word and a next
step. A dollar figure and one evidence word are enough to pass ("$1 invoice"
passes). That is all "passes the quality gate" means offline.

Without the flag and without a working model, score() returns
status='unavailable' and gate_decision() holds the text (fails closed).
"""

from __future__ import annotations

import json
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional

NSOS_DIR = Path(__file__).resolve().parent
_REPO = str(NSOS_DIR.parents[1])
if _REPO not in sys.path:  # also importable when run as `python engine/gauntlets/quality_judge.py`
    sys.path.insert(0, _REPO)
from engine.router.nim_client import call_nim  # noqa: E402  the one LLM client (CLAUDE.md rule 3)

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

# ── LLM call ────────────────────────────────────────────────────────────────
# call_nim's default model is the fast tier. Rubric is terse; expect <150 tokens.
_JUDGE_CALL = _RULES.get("judge_call", {})
JUDGE_MAX_TOKENS = int(_JUDGE_CALL.get("max_tokens", 400))
JUDGE_TEMPERATURE = float(_JUDGE_CALL.get("temperature", 0.1))

RUBRIC_PROMPT = _build_rubric_prompt()

# ── offline-deterministic judge ──────────────────────────────────────────────
# When no model is configured (CI, offline build, no NIM key) the live
# rubric call returns None and the gate fails CLOSED — correct for production,
# but it would block a synthetic offline build from ever verifying client-facing
# output. So, ONLY when explicitly enabled via NSOS_JUDGE_OFFLINE_DETERMINISTIC=1,
# fall back to a deterministic structural rubric (mirrors council.deterministic_judge:
# a reproducible offline scorer so the build can verify gating logic without a key).
# Default OFF — production keeps the fail-closed live-LLM behavior untouched.
# Read on every call, so the mode never depends on which module imported this first.
def offline_deterministic() -> bool:
    return os.environ.get("NSOS_JUDGE_OFFLINE_DETERMINISTIC", "") in ("1", "true", "yes")


def judge_mode() -> str:
    """What score() will do: 'offline-deterministic', 'live' or 'fail-closed'."""
    if offline_deterministic():
        return "offline-deterministic"
    return "live" if os.environ.get("NIM_API_KEY") else "fail-closed"

_DOLLAR_RE = re.compile(r"\$\s?\d")
_HOURS_RE = re.compile(r"\b\d[\d,\.]*\s*(hours?|hrs?|hr/?yr|hours?/year)\b", re.I)
_EVIDENCE_RE = re.compile(r"\b(source|evidence|QuickBooks|accounting|baseline|invoice|vendor|because|per |based on)\b", re.I)
# (?i:...) on the word only: "Confidence: 0.7" counts, but plain "low" or "likely" does not.
_CONF_RE = re.compile(r"\b((?i:confiden\w*)|HIGH|MEDIUM|LOW|LIKELY|VERIFIED|UNVERIFIED|\d{1,3}\s?%)\b")
_NEXT_STEP_RE = re.compile(r"\b(recommend|next step|should|propose|scope|switch|collect|reduce|consolidate|insource|re-?platform)\b", re.I)


def _deterministic_score(output_text: str) -> Dict[str, Any]:
    """Reproducible structural rubric — no LLM. Scores the four dimensions on the
    same 0-5 / 0.0-1.0 scale the LLM rubric uses, from defensible textual signals:
    a grounded client-facing finding cites dollars/hours (relevance), names a
    concrete action (actionability), points at its evidence + a confidence word
    (calibration), and earns a confidence band proportional to how grounded it is.
    """
    t = (output_text or "").strip()
    has_money = bool(_DOLLAR_RE.search(t)) or bool(_HOURS_RE.search(t))
    has_evidence = bool(_EVIDENCE_RE.search(t))
    has_conf = bool(_CONF_RE.search(t))
    has_next = bool(_NEXT_STEP_RE.search(t))
    long_enough = len(t) >= 40

    relevance = 5 if (has_money and has_evidence) else 4 if has_money else 2 if long_enough else 0
    actionability = 5 if has_next else 3 if has_money else 1
    calibration = 5 if (has_evidence and has_conf) else 4 if has_evidence else 2 if long_enough else 1
    # confidence: 0.5 floor + grounding bonuses, capped at 0.95
    confidence = min(0.95, 0.5 + 0.2 * has_money + 0.15 * has_evidence + 0.1 * has_conf)
    return {
        "status": "ok",
        "relevance": relevance,
        "actionability": actionability,
        "calibration": calibration,
        "confidence": round(confidence, 3),
        "reasoning": "offline-deterministic structural rubric (no LLM): "
                     f"money={has_money} evidence={has_evidence} conf={has_conf} action={has_next}",
        "raw": "offline-deterministic",
    }


def _call_judge_llm(prompt: str) -> Optional[str]:
    """Run the rubric call through nim_client. Returns raw string or None on failure."""
    try:
        return call_nim(
            prompt,
            system=RUBRIC_PROMPT,
            temperature=JUDGE_TEMPERATURE,
            max_tokens=JUDGE_MAX_TOKENS,
        )
    except Exception as e:
        _log_judge_error(f"call_nim failed: {e}")
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
    with null scores; gate_decision() holds anything with that status.
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

    if offline_deterministic():
        # Checked before any model call: offline means nothing leaves the machine,
        # even when NIM_API_KEY happens to be set in the shell.
        return _deterministic_score(output_text)
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

    Fails closed: text the judge could not score is held.
    """
    if scores.get("status") != "ok":
        return True
    r = scores.get("relevance") or 0
    a = scores.get("actionability") or 0
    c = scores.get("calibration") or 0
    conf = scores.get("confidence") or 0.0
    if (r + a + c) < SUM_THRESHOLD:
        return True
    if conf < CONF_THRESHOLD:
        return True
    return False


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
        if gated:
            why = "below quality threshold" if scores.get("status") == "ok" else "judge unavailable"
            print(f"GATE: FAIL — {why}", file=sys.stderr)
            return 1
        print("GATE: PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
