"""The live quality judge goes through engine.router.nim_client and fails closed.

call_nim is monkeypatched: no network, no API key, no paid call.
"""
import importlib.util
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from engine.router import nim_client  # noqa: E402

# A private module object: other tests import `quality_judge` with the offline env set,
# and a shared sys.modules entry would freeze whichever mode loaded first.
_spec = importlib.util.spec_from_file_location("qj_under_test", ROOT / "engine" / "gauntlets" / "quality_judge.py")
qj = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(qj)

RUBRIC = {"relevance": 4, "actionability": 4, "calibration": 3, "confidence": 0.8, "reasoning": "cites $"}


def test_live_judge_scores_through_call_nim(monkeypatch):
    seen = {}

    def fake_call_nim(prompt, **kw):
        seen.update(kw, prompt=prompt)
        return json.dumps(RUBRIC)

    monkeypatch.setattr(qj, "call_nim", fake_call_nim)
    monkeypatch.setattr(qj, "OFFLINE_DETERMINISTIC", False)
    s = qj.score("Vendor spend is $84k/yr.")
    assert s["status"] == "ok"
    assert (s["relevance"], s["confidence"]) == (4, 0.8)
    assert seen["system"] == qj.RUBRIC_PROMPT
    assert (seen["temperature"], seen["max_tokens"]) == (qj.JUDGE_TEMPERATURE, qj.JUDGE_MAX_TOKENS)
    assert "Vendor spend" in seen["prompt"]


def test_live_judge_failure_is_unavailable(monkeypatch):
    def boom(prompt, **kw):
        raise RuntimeError("NIM HTTP 503")

    monkeypatch.setattr(qj, "call_nim", boom)
    monkeypatch.setattr(qj, "_log_judge_error", lambda msg: None)
    monkeypatch.setattr(qj, "OFFLINE_DETERMINISTIC", False)
    assert qj.score("anything")["status"] == "unavailable"


def _boom(*a, **kw):
    raise RuntimeError("NIM HTTP 503")


def test_judge_pair_raises_when_nim_fails_outside_offline_mode(monkeypatch):
    monkeypatch.setattr(nim_client, "call_nim", _boom)
    monkeypatch.delenv("NSOS_JUDGE_OFFLINE_DETERMINISTIC", raising=False)
    with pytest.raises(RuntimeError):
        nim_client.judge_pair({"impact_usd": 2}, {"impact_usd": 1})


def test_offline_mode_never_calls_the_model_even_with_a_key(monkeypatch):
    """Offline means nothing leaves the machine, even with NIM_API_KEY in the shell."""
    calls = []

    def recording_boom(*a, **kw):
        calls.append(a)
        raise RuntimeError("must not be called")

    monkeypatch.setenv("NIM_API_KEY", "set-for-test-only")
    monkeypatch.setenv("NSOS_JUDGE_OFFLINE_DETERMINISTIC", "1")
    monkeypatch.setattr(nim_client, "call_nim", recording_boom)
    monkeypatch.setattr(qj, "call_nim", recording_boom)
    monkeypatch.setattr(qj, "OFFLINE_DETERMINISTIC", True)
    assert nim_client.judge_pair({"impact_usd": 2}, {"impact_usd": 1}) == "A"
    assert qj.score("Vendor spend is $84k/yr, per QuickBooks; recommend consolidating.")["status"] == "ok"
    assert calls == []
