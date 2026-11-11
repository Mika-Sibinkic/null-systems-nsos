"""Pins the five promotion-gate decisions on a tmp repo with fixture inputs."""
import importlib.util
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
_spec = importlib.util.spec_from_file_location("promotion_gate", ROOT / "learning" / "promotion-gate" / "promotion_gate.py")
gate = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(gate)


def _repo(tmp_path: Path, *, test_body: str, score: float, perf: dict) -> Path:
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests" / "test_fixture.py").write_text(f"def test_fixture():\n    {test_body}\n")
    (tmp_path / "runs").mkdir()
    (tmp_path / "runs" / "latest-gauntlet-score.json").write_text(json.dumps({"score": score}))
    (tmp_path / "runs" / "perf-delta.json").write_text(json.dumps(perf))
    return tmp_path


def _proposal(tmp_path: Path, *, checked: bool, positives: int) -> Path:
    p = tmp_path / "proposal.md"
    p.write_text(f"# Proposal\n\n- [{'x' if checked else ' '}] Operator reviewed\n")
    reviews = [{"verdict": "net-positive"}] * positives + [{"verdict": "net-negative"}]
    p.with_suffix(".reviews.json").write_text(json.dumps(reviews))
    return p


def _decisions(evaluation: dict) -> dict:
    return {g["gate"]: g["pass"] for g in evaluation["gates"]}


def test_all_five_gates_pass(tmp_path):
    repo = _repo(tmp_path, test_body="assert True", score=90, perf={"latency_pct": 2, "cost_pct": 1})
    ev = gate.evaluate_proposal(_proposal(tmp_path, checked=True, positives=2), repo)
    assert _decisions(ev) == {"regression": True, "gauntlet": True, "performance": True,
                              "council": True, "operator": True}
    assert ev["overall_pass"] is True


def test_each_gate_can_fail(tmp_path):
    repo = _repo(tmp_path, test_body="assert False", score=60, perf={"latency_pct": 25, "cost_pct": 1})
    ev = gate.evaluate_proposal(_proposal(tmp_path, checked=False, positives=1), repo)
    assert _decisions(ev) == {"regression": False, "gauntlet": False, "performance": False,
                              "council": False, "operator": False}
    assert ev["overall_pass"] is False


def test_gauntlet_gate_is_one_sided(tmp_path):
    def check(score):
        (tmp_path / "runs").mkdir(exist_ok=True)
        (tmp_path / "runs" / "latest-gauntlet-score.json").write_text(json.dumps({"score": score}))
        return gate.gauntlet_score_check(tmp_path, baseline=74.6, tolerance=5.0)["pass"]

    assert check(90) is True      # better than baseline is never a regression
    assert check(69.6) is True    # exactly baseline - tolerance
    assert check(69.5) is False


def test_missing_input_files_report_not_wired(tmp_path):
    for result in (gate.gauntlet_score_check(tmp_path), gate.performance_analyzer(tmp_path)):
        assert result["pass"] is False
        assert "not wired" in result["reason"]
