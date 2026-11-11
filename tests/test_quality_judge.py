"""The live quality judge goes through engine.router.nim_client and fails closed.

call_nim is monkeypatched: no network, no API key, no paid call.
"""
import json

from engine.gauntlets import quality_judge as qj


RUBRIC = {"relevance": 4, "actionability": 4, "calibration": 3, "confidence": 0.8, "reasoning": "cites $"}


def test_live_judge_scores_through_call_nim(monkeypatch):
    seen = {}

    def fake_call_nim(prompt, **kw):
        seen.update(kw, prompt=prompt)
        return json.dumps(RUBRIC)

    monkeypatch.setattr(qj, "call_nim", fake_call_nim)
    monkeypatch.delenv("NSOS_JUDGE_OFFLINE_DETERMINISTIC", raising=False)
    s = qj.score("Vendor spend is $84k/yr.")
    assert s["status"] == "ok"
    assert (s["relevance"], s["confidence"]) == (4, 0.8)
    assert seen["system"] == qj.RUBRIC_PROMPT
    assert (seen["temperature"], seen["max_tokens"]) == (qj.JUDGE_TEMPERATURE, qj.JUDGE_MAX_TOKENS)
    assert "Vendor spend" in seen["prompt"]


def test_unavailable_judge_holds_the_text(monkeypatch):
    def boom(prompt, **kw):
        raise RuntimeError("NIM HTTP 503")

    monkeypatch.setattr(qj, "call_nim", boom)
    monkeypatch.setattr(qj, "_log_judge_error", lambda msg: None)
    monkeypatch.delenv("NSOS_JUDGE_OFFLINE_DETERMINISTIC", raising=False)
    s = qj.score("anything")
    assert s["status"] == "unavailable"
    assert qj.gate_decision(s) is True  # fails closed in the shared function, not per caller


def test_offline_mode_never_calls_the_model_even_with_a_key(monkeypatch):
    """Offline means nothing leaves the machine, even with NIM_API_KEY in the shell."""
    calls = []

    def recording_boom(*a, **kw):
        calls.append(a)
        raise RuntimeError("must not be called")

    monkeypatch.setenv("NIM_API_KEY", "set-for-test-only")
    monkeypatch.setenv("NSOS_JUDGE_OFFLINE_DETERMINISTIC", "1")
    monkeypatch.setattr(qj, "call_nim", recording_boom)
    assert qj.score("Vendor spend is $84k/yr, per QuickBooks; recommend consolidating.")["status"] == "ok"
    assert calls == []


def test_offline_rubric_counts_the_gates_own_confidence_label():
    """review_gate writes 'Confidence: 0.7'; that label is a confidence word."""
    assert "conf=True" in qj._deterministic_score("Confidence: 0.7")["reasoning"]


def test_offline_gate_passes_a_dollar_figure_plus_one_evidence_word():
    """The README limit, pinned: offline, '$1 invoice' is enough to pass."""
    assert qj.gate_decision(qj._deterministic_score("$1 invoice")) is False
