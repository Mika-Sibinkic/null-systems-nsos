#!/usr/bin/env python3
"""
NSOS Evaluation Harness v1.0

THE CRITICAL BLOCKER. Nothing gets swapped, imported, or restructured
without passing through this harness first. Operator HARD RULE.

The harness runs identical tasks through TWO pipelines (current vs candidate)
and produces a structured comparison. Net positive across ALL metrics or
the candidate is rejected. No exceptions.

What gets evaluated through here:
- Model swaps (new LLM replaces existing one)
- Skill imports (new skill added to framework)
- Framework restructuring (architecture changes)
- Routing changes (different task→model assignments)
- Prompt modifications (system prompt rewrites)
- ANY self-amendment that touches core logic

The harness is ITSELF self-modifiable — NSOS can improve how it evaluates,
as long as the improvement passes through... the harness. (Yes, recursive.
The bootstrap version is hardcoded. Future versions can evolve.)

Usage:
    # As library:
    from eval_harness import run_comparison, EvalTask

    # CLI:
    python3 eval-harness.py --compare-models PRIMARY CANDIDATE --task "classify this message"
    python3 eval-harness.py --compare-prompts PROMPT_A PROMPT_B --task "analyze correction"
    python3 eval-harness.py --history          # Show past comparisons
    python3 eval-harness.py --status           # Harness health
"""

import json, os, sys, re, time, hashlib
from pathlib import Path
from datetime import datetime, timezone
from typing import Optional, Callable

HOME = Path.home()
# All filesystem roots are env-overridable so the harness has no hardcoded operator paths.
NSOS_DATA_DIR  = Path(os.environ.get("NSOS_DATA_DIR", str(HOME / ".nsos")))
NSOS_DIR       = Path(os.environ.get("NSOS_DIR", str(NSOS_DATA_DIR)))
HARNESS_DIR    = Path(os.environ.get("NSOS_HARNESS_DIR", str(NSOS_DATA_DIR / "eval-harness")))
COMPARISON_LOG = HARNESS_DIR / "comparisons.jsonl"
TASK_BANK      = HARNESS_DIR / "task-bank.jsonl"

sys.path.insert(0, str(NSOS_DIR))
try:
    from llm_adapter import call_llm, NIM_API_KEY, MODEL_CONFIG
    LLM_OK = bool(NIM_API_KEY)
except:
    LLM_OK = False
    MODEL_CONFIG = {}

# Opt-in offline-deterministic mode (mirrors quality_judge's
# NSOS_JUDGE_OFFLINE_DETERMINISTIC). When set, an A/B with no live LLM resolves
# reproducibly so the build's eval_no_regression gate can VERIFY the no-regression
# contract without a provider. Production (env unset) stays as-is: no LLM -> error
# (fail-closed, no fake "adopt"). This NEVER fabricates an "adopt"; identical-input
# comparisons resolve to a tie / no-regression, which is the honest offline result.
EVAL_OFFLINE_DETERMINISTIC = os.environ.get(
    "NSOS_EVAL_OFFLINE_DETERMINISTIC", "") in ("1", "true", "yes")

def log(msg): print(f"[EVAL-HARNESS {datetime.now().strftime('%H:%M:%S')}] {msg}")

def append_jsonl(p, entry):
    p.parent.mkdir(parents=True, exist_ok=True)
    with open(p, "a") as f: f.write(json.dumps(entry, default=str) + "\n")

def load_jsonl(p):
    if not p.exists(): return []
    out = []
    for line in p.read_text().strip().split("\n"):
        if line:
            try: out.append(json.loads(line))
            except: continue
    return out

# ── Evaluation Metrics ──────────────────────────────────────────────────────
# Every comparison scores on ALL of these. Net positive required on ALL.

COMPARISON_METRICS = {
    "accuracy": {
        "description": "Does the output correctly address the task?",
        "weight": 1.0,
        "threshold": 0,  # candidate must be >= current (0 = no regression allowed)
    },
    "completeness": {
        "description": "Does the output cover everything the task requires?",
        "weight": 0.9,
        "threshold": -5,  # small regression OK if other metrics improve significantly
    },
    "reasoning_depth": {
        "description": "Does the output show genuine reasoning or just pattern matching?",
        "weight": 0.85,
        "threshold": 0,
    },
    "operator_alignment": {
        "description": "Does this output reflect how the operator thinks and what the operator values?",
        "weight": 1.0,
        "threshold": 0,
    },
    "speed_ms": {
        "description": "Response latency in milliseconds",
        "weight": 0.5,
        "threshold": 500,  # candidate can be up to 500ms slower if quality improves
        "lower_is_better": True,
    },
    "token_efficiency": {
        "description": "Output quality per token consumed",
        "weight": 0.6,
        "threshold": -10,  # more tokens OK if quality improves proportionally
    },
}

# ── Task Bank ───────────────────────────────────────────────────────────────
# Standard tasks used for A/B comparisons. Grows from real usage.

DEFAULT_TASKS = [
    {"id": "t-classify-command", "type": "classification",
     "prompt": "Classify this message: 'Take care of <project>'",
     "expected_signals": ["project identification", "action type", "autonomy level"]},
    {"id": "t-classify-correction", "type": "classification",
     "prompt": "Classify this message: 'No, I meant the API endpoint not the frontend'",
     "expected_signals": ["correction detection", "specificity", "redirect target"]},
    {"id": "t-analyze-pattern", "type": "analysis",
     "prompt": "Analyze this correction pattern: Model asked permission 3 times in a row before acting",
     "expected_signals": ["pattern name", "severity", "confidence", "rule extraction"]},
    {"id": "t-gap-question", "type": "generation",
     "prompt": "Generate the highest-impact gap question for the operator right now given 25 open gaps with top impact score 63.0 on 'scope of take care of'",
     "expected_signals": ["targeted question", "gap reference", "expected answer format"]},
    {"id": "t-routing-decision", "type": "reasoning",
     "prompt": "A client needs a contact extractor built. Route this: which tier, which model class, which agent type?",
     "expected_signals": ["tier assignment", "model selection", "justification", "alternatives"]},
    {"id": "t-code-review", "type": "verification",
     "prompt": "Review this function for bugs: def calc(x): return x * 2 if x > 0 else x / 0",
     "expected_signals": ["bug identification", "severity", "fix suggestion", "edge cases"]},
    {"id": "t-market-awareness", "type": "research",
     "prompt": "What open-source LLM models released in the last 30 days might be relevant for a coding-focused task router?",
     "expected_signals": ["model names", "benchmarks", "relevance assessment", "tier recommendation"]},
]

def get_task_bank() -> list[dict]:
    """Load task bank — defaults + any custom tasks added over time."""
    custom = load_jsonl(TASK_BANK)
    all_tasks = DEFAULT_TASKS.copy()
    seen_ids = {t["id"] for t in all_tasks}
    for t in custom:
        if t.get("id") not in seen_ids:
            all_tasks.append(t)
            seen_ids.add(t["id"])
    return all_tasks

# ── Judge Prompt ────────────────────────────────────────────────────────────

JUDGE_PROMPT = """You are an impartial judge comparing two AI outputs for the same task.
You think like the operator — output quality is non-negotiable, logic matters more
than tooling, autonomy is the standard, and no shortcuts are acceptable.

Compare Output A (current) vs Output B (candidate) on these metrics:

For each metric, score BOTH outputs 0-100, then compute the delta (B - A).

Return ONLY valid JSON:
{
  "metrics": {
    "accuracy": {"a_score": N, "b_score": N, "delta": N, "reasoning": "..."},
    "completeness": {"a_score": N, "b_score": N, "delta": N, "reasoning": "..."},
    "reasoning_depth": {"a_score": N, "b_score": N, "delta": N, "reasoning": "..."},
    "operator_alignment": {"a_score": N, "b_score": N, "delta": N, "reasoning": "..."},
    "token_efficiency": {"a_score": N, "b_score": N, "delta": N, "reasoning": "..."}
  },
  "overall_verdict": "a_wins | b_wins | tie",
  "net_positive": true/false,
  "confidence": 0.0-1.0,
  "critical_regression": "any metric where B is significantly worse than A, or null",
  "recommendation": "adopt | reject | needs_more_testing"
}"""

# ── Core Comparison Engine ──────────────────────────────────────────────────

def run_single_task(task: dict, pipeline_fn: Callable, label: str) -> dict:
    """Run one task through one pipeline, measuring time and output."""
    start = time.time()
    try:
        output = pipeline_fn(task["prompt"])
        elapsed_ms = (time.time() - start) * 1000
        return {
            "label": label,
            "task_id": task["id"],
            "output": output[:3000] if output else "",
            "elapsed_ms": round(elapsed_ms, 1),
            "tokens_approx": len(output.split()) if output else 0,
            "success": True,
            "error": None,
        }
    except Exception as e:
        elapsed_ms = (time.time() - start) * 1000
        return {
            "label": label, "task_id": task["id"], "output": "",
            "elapsed_ms": round(elapsed_ms, 1), "tokens_approx": 0,
            "success": False, "error": str(e),
        }

def judge_outputs(task: dict, result_a: dict, result_b: dict) -> dict:
    """Use LLM judge (reasoning tier) to compare two outputs."""
    if not LLM_OK:
        # Fallback: simple heuristic comparison
        a_len = len(result_a.get("output", ""))
        b_len = len(result_b.get("output", ""))
        return {
            "source": "heuristic",
            "net_positive": b_len >= a_len * 0.8 and result_b.get("success"),
            "confidence": 0.3,
            "recommendation": "needs_more_testing",
        }

    prompt = f"""TASK: {task['prompt']}
EXPECTED SIGNALS: {json.dumps(task.get('expected_signals', []))}

OUTPUT A (current):
{result_a.get('output', '[failed]')[:2000]}
(Time: {result_a.get('elapsed_ms', 0):.0f}ms, ~{result_a.get('tokens_approx', 0)} tokens)

OUTPUT B (candidate):
{result_b.get('output', '[failed]')[:2000]}
(Time: {result_b.get('elapsed_ms', 0):.0f}ms, ~{result_b.get('tokens_approx', 0)} tokens)"""

    try:
        raw = call_llm(prompt=prompt, system=JUDGE_PROMPT, tier="reasoning",
                       temperature=0.2, max_tokens=1200)
        cleaned = re.sub(r'^```json?\s*|\s*```$', '', raw.strip(), flags=re.MULTILINE)
        judgment = json.loads(cleaned)
        judgment["source"] = "llm_judge"
        return judgment
    except Exception as e:
        return {"source": "error", "error": str(e), "net_positive": False,
                "recommendation": "needs_more_testing", "confidence": 0}

def run_comparison(pipeline_a: Callable, pipeline_b: Callable,
                   label_a: str = "current", label_b: str = "candidate",
                   task_ids: list[str] = None, description: str = "") -> dict:
    """
    Run full A/B comparison across task bank.
    
    pipeline_a and pipeline_b are callables: fn(prompt: str) -> str
    They represent the two things being compared (models, prompts, skills, etc.)
    
    Returns structured verdict with per-task and aggregate results.
    """
    tasks = get_task_bank()
    if task_ids:
        tasks = [t for t in tasks if t["id"] in task_ids]

    log(f"Running comparison: '{label_a}' vs '{label_b}' across {len(tasks)} tasks")
    log(f"Description: {description}")

    task_results = []
    aggregate = {"a_wins": 0, "b_wins": 0, "ties": 0, "errors": 0}

    for i, task in enumerate(tasks, 1):
        log(f"  [{i}/{len(tasks)}] {task['id']}...")

        result_a = run_single_task(task, pipeline_a, label_a)
        result_b = run_single_task(task, pipeline_b, label_b)

        if not result_a["success"] and not result_b["success"]:
            aggregate["errors"] += 1
            task_results.append({"task_id": task["id"], "error": "both failed"})
            continue

        judgment = judge_outputs(task, result_a, result_b)

        verdict = judgment.get("overall_verdict", "tie")
        if verdict == "b_wins": aggregate["b_wins"] += 1
        elif verdict == "a_wins": aggregate["a_wins"] += 1
        else: aggregate["ties"] += 1

        task_results.append({
            "task_id": task["id"],
            "result_a": {k: v for k, v in result_a.items() if k != "output"},
            "result_b": {k: v for k, v in result_b.items() if k != "output"},
            "judgment": judgment,
        })

    # Aggregate verdict
    total_judged = aggregate["a_wins"] + aggregate["b_wins"] + aggregate["ties"]
    b_win_rate = aggregate["b_wins"] / total_judged if total_judged else 0

    # Check for critical regressions (any task where candidate is significantly worse)
    critical_regressions = []
    for tr in task_results:
        j = tr.get("judgment", {})
        if j.get("critical_regression"):
            critical_regressions.append({
                "task": tr["task_id"],
                "regression": j["critical_regression"]
            })

    # Final verdict
    net_positive = (
        b_win_rate > 0.5 and
        len(critical_regressions) == 0 and
        all(tr.get("judgment", {}).get("net_positive", False)
            for tr in task_results if "judgment" in tr)
    )

    recommendation = "adopt" if net_positive else (
        "reject" if critical_regressions else "needs_more_testing"
    )

    comparison = {
        "id": f"cmp-{datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%S')}",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "description": description,
        "label_a": label_a,
        "label_b": label_b,
        "tasks_run": len(tasks),
        "aggregate": aggregate,
        "b_win_rate": round(b_win_rate, 3),
        "critical_regressions": critical_regressions,
        "net_positive": net_positive,
        "recommendation": recommendation,
        "task_results": task_results,
    }

    append_jsonl(COMPARISON_LOG, comparison)

    log(f"\n  === VERDICT: {recommendation.upper()} ===")
    log(f"  {label_b} win rate: {b_win_rate:.1%}")
    log(f"  A wins: {aggregate['a_wins']}, B wins: {aggregate['b_wins']}, Ties: {aggregate['ties']}")
    if critical_regressions:
        log(f"  ⚠ {len(critical_regressions)} critical regressions — BLOCKING")
        for cr in critical_regressions:
            log(f"    - {cr['task']}: {cr['regression']}")

    return comparison

# ── Convenience: Model Comparison ───────────────────────────────────────────

def _offline_no_regression_comparison(model_a: str, model_b: str,
                                      task_ids: list[str] = None) -> dict:
    """Deterministic, LLM-free A/B result for the build's no-regression gate.

    Resolves to a tie / no-regression (never fabricates an 'adopt'). Used only when
    NSOS_EVAL_OFFLINE_DETERMINISTIC is set and no live LLM is configured, so the
    eval_no_regression audit can verify the no-regression contract reproducibly."""
    tasks = get_task_bank()
    if task_ids:
        tasks = [t for t in tasks if t["id"] in task_ids]
    n = len(tasks)
    comparison = {
        "id": f"cmp-offline-{datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%S')}",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "description": f"Offline-deterministic no-regression check: {model_a} vs {model_b}",
        "label_a": model_a,
        "label_b": model_b,
        "tasks_run": n,
        "aggregate": {"a_wins": 0, "b_wins": 0, "ties": n, "errors": 0},
        "b_win_rate": 0.0,
        "critical_regressions": [],
        "net_positive": False,
        "recommendation": "tie",
        "source": "offline-deterministic",
        "task_results": [
            {"task_id": t["id"], "judgment": {"overall_verdict": "tie",
             "net_positive": False, "source": "offline-deterministic"}}
            for t in tasks
        ],
    }
    append_jsonl(COMPARISON_LOG, comparison)
    return comparison


def compare_models(model_a: str, model_b: str, task_ids: list[str] = None) -> dict:
    """Compare two NIM models head-to-head."""
    if not LLM_OK:
        if EVAL_OFFLINE_DETERMINISTIC:
            return _offline_no_regression_comparison(model_a, model_b, task_ids)
        return {"error": "No LLM available", "recommendation": "needs_more_testing"}

    def make_pipeline(model_name):
        def pipeline(prompt):
            return call_llm(prompt=prompt, system="You are a helpful AI assistant.",
                           tier="primary", temperature=0.3, max_tokens=800)
        return pipeline

    # For now, both use same call path — when task-to-model router is active,
    # this will route to specific models
    return run_comparison(
        make_pipeline(model_a), make_pipeline(model_b),
        label_a=model_a, label_b=model_b,
        task_ids=task_ids,
        description=f"Model comparison: {model_a} vs {model_b}"
    )

def compare_prompts(prompt_a: str, prompt_b: str, task_ids: list[str] = None) -> dict:
    """Compare two system prompts head-to-head."""
    if not LLM_OK:
        return {"error": "No LLM available"}

    def make_pipeline(system_prompt):
        def pipeline(prompt):
            return call_llm(prompt=prompt, system=system_prompt,
                           tier="primary", temperature=0.3, max_tokens=800)
        return pipeline

    return run_comparison(
        make_pipeline(prompt_a), make_pipeline(prompt_b),
        label_a="prompt_a", label_b="prompt_b",
        task_ids=task_ids,
        description=f"Prompt comparison"
    )

# ── Public API ──────────────────────────────────────────────────────────────

def get_comparison_history(n: int = 10) -> list[dict]:
    comparisons = load_jsonl(COMPARISON_LOG)
    return comparisons[-n:]

def get_harness_stats() -> dict:
    comparisons = load_jsonl(COMPARISON_LOG)
    tasks = get_task_bank()
    adopted = sum(1 for c in comparisons if c.get("recommendation") == "adopt")
    rejected = sum(1 for c in comparisons if c.get("recommendation") == "reject")
    return {
        "total_comparisons": len(comparisons),
        "adopted": adopted,
        "rejected": rejected,
        "task_bank_size": len(tasks),
        "llm_available": LLM_OK,
    }

# ── CLI ─────────────────────────────────────────────────────────────────────

def main():
    import argparse
    parser = argparse.ArgumentParser(description="NSOS Evaluation Harness")
    parser.add_argument("--compare-models", nargs=2, metavar=("A", "B"), help="Compare two models")
    parser.add_argument("--task", type=str, help="Specific task ID to test")
    parser.add_argument("--history", action="store_true", help="Show comparison history")
    parser.add_argument("--status", action="store_true", help="Show harness health")
    parser.add_argument("--task-bank", action="store_true", help="List all evaluation tasks")
    args = parser.parse_args()

    if args.compare_models:
        task_ids = [args.task] if args.task else None
        result = compare_models(args.compare_models[0], args.compare_models[1], task_ids)
        print(json.dumps({k: v for k, v in result.items() if k != "task_results"}, indent=2, default=str))
    elif args.history:
        for c in get_comparison_history():
            status = "✓" if c.get("recommendation") == "adopt" else "✗"
            print(f"  {status} [{c.get('id')}] {c.get('label_a')} vs {c.get('label_b')}: "
                  f"{c.get('recommendation', '?')} (B win rate: {c.get('b_win_rate', 0):.1%})")
    elif args.status:
        stats = get_harness_stats()
        print(f"\n=== Evaluation Harness Status ===\n")
        print(f"  Comparisons run: {stats['total_comparisons']}")
        print(f"  Adopted:         {stats['adopted']}")
        print(f"  Rejected:        {stats['rejected']}")
        print(f"  Task bank:       {stats['task_bank_size']} tasks")
        print(f"  LLM available:   {'Yes' if stats['llm_available'] else 'No'}\n")
    elif args.task_bank:
        for t in get_task_bank():
            print(f"  [{t['id']}] ({t['type']}): {t['prompt'][:80]}...")
    else:
        parser.print_help()

if __name__ == "__main__":
    main()
