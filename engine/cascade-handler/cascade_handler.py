"""
NSOS Cascade Handler — Intelligent Failure Recovery System

Analyzes agent failures across NSOS tiers and determines optimal recovery strategy.
Replaces dumb retries with LLM-guided or rule-based intelligent recovery decisions.

Version: 1.0.0
"""

import json
import sys
import argparse
from pathlib import Path
from datetime import datetime, timedelta
from enum import Enum
from typing import Optional, Dict, Any, List
from collections import defaultdict

# Add parent directory to path for llm_adapter import
NSOS_DIR = Path(__file__).parent
sys.path.insert(0, str(NSOS_DIR))

try:
    from llm_adapter import call_reasoning_tier
    HAS_LLM = True
except ImportError:
    HAS_LLM = False


class RecoveryStrategy(str, Enum):
    """Recovery strategies for agent failures."""
    RETRY_SAME = "retry_same"
    RETRY_DIFFERENT_MODEL = "retry_different_model"
    RETRY_SIMPLER = "retry_simpler"
    ESCALATE_TIER = "escalate_tier"
    DECOMPOSE_FURTHER = "decompose_further"
    SKIP_AND_CONTINUE = "skip_and_continue"
    HUMAN_REQUIRED = "human_required"


class ErrorCategory(str, Enum):
    """Categorization of failure types."""
    TIMEOUT = "timeout"
    API_ERROR = "api_error"
    QUALITY_TOO_LOW = "quality_too_low"
    MODEL_REFUSED = "model_refused"
    MEMORY_EXHAUSTED = "memory_exhausted"
    MALFORMED_INPUT = "malformed_input"
    RATE_LIMITED = "rate_limited"
    UNKNOWN = "unknown"


def ensure_recovery_dirs() -> None:
    """Create recovery tracking directories if they don't exist."""
    recovery_dir = NSOS_DIR / "recovery"
    recovery_dir.mkdir(parents=True, exist_ok=True)


def categorize_error(error: str, error_type: Optional[str] = None) -> ErrorCategory:
    """Categorize error message into known failure patterns."""
    error_lower = error.lower()

    if "timeout" in error_lower or "timed out" in error_lower:
        return ErrorCategory.TIMEOUT
    elif "rate limit" in error_lower or "429" in error_lower:
        return ErrorCategory.RATE_LIMITED
    elif "api" in error_lower or "connection" in error_lower or "500" in error_lower:
        return ErrorCategory.API_ERROR
    elif "quality" in error_lower or "low score" in error_lower:
        return ErrorCategory.QUALITY_TOO_LOW
    elif "refused" in error_lower or "declined" in error_lower:
        return ErrorCategory.MODEL_REFUSED
    elif "memory" in error_lower or "exhausted" in error_lower or "out of memory" in error_lower:
        return ErrorCategory.MEMORY_EXHAUSTED
    elif "malformed" in error_lower or "invalid" in error_lower or "syntax" in error_lower:
        return ErrorCategory.MALFORMED_INPUT
    else:
        return ErrorCategory.UNKNOWN


def rule_based_recovery(
    error_category: ErrorCategory,
    agent_tier: int,
    attempt_number: int,
    task_description: str
) -> RecoveryStrategy:
    """
    Fast path: rule-based recovery without LLM.
    Returns the most likely recovery strategy based on error category and context.
    """
    if error_category == ErrorCategory.TIMEOUT:
        if attempt_number == 1:
            return RecoveryStrategy.RETRY_SAME
        else:
            return RecoveryStrategy.RETRY_DIFFERENT_MODEL

    elif error_category == ErrorCategory.RATE_LIMITED:
        return RecoveryStrategy.RETRY_SAME  # Wait and retry

    elif error_category == ErrorCategory.API_ERROR:
        if attempt_number < 2:
            return RecoveryStrategy.RETRY_SAME
        else:
            return RecoveryStrategy.RETRY_DIFFERENT_MODEL

    elif error_category == ErrorCategory.QUALITY_TOO_LOW:
        if agent_tier < 2:
            return RecoveryStrategy.ESCALATE_TIER
        else:
            return RecoveryStrategy.RETRY_SIMPLER

    elif error_category == ErrorCategory.MODEL_REFUSED:
        return RecoveryStrategy.RETRY_DIFFERENT_MODEL

    elif error_category == ErrorCategory.MEMORY_EXHAUSTED:
        return RecoveryStrategy.DECOMPOSE_FURTHER

    elif error_category == ErrorCategory.MALFORMED_INPUT:
        return RecoveryStrategy.RETRY_SIMPLER

    else:  # UNKNOWN
        return RecoveryStrategy.DECOMPOSE_FURTHER


def llm_recovery_analysis(
    error_category: ErrorCategory,
    agent_type: str,
    agent_tier: int,
    model_used: str,
    task_description: str,
    error: str,
    attempt_number: int
) -> Dict[str, Any]:
    """
    Use reasoning-tier LLM to analyze failure and recommend recovery strategy.
    Returns structured recovery decision with confidence score.
    """
    if not HAS_LLM:
        return None

    prompt = f"""Analyze this agent failure and recommend recovery strategy.

Error Category: {error_category.value}
Agent Type: {agent_type}
Agent Tier: {agent_tier}
Model Used: {model_used}
Attempt Number: {attempt_number}
Task: {task_description}
Error Message: {error}

Available recovery strategies:
- retry_same: Retry with same model and task
- retry_different_model: Swap to different model class
- retry_simpler: Simplify the task description
- escalate_tier: Escalate to higher tier agent
- decompose_further: Break task into smaller subtasks
- skip_and_continue: Mark as non-critical, move on
- human_required: Escalate to human (Mika)

Respond with JSON:
{{
  "strategy": "...",
  "reasoning": "...",
  "confidence": 0.X,
  "recommended_model": "... or null",
  "should_retry_immediately": true/false
}}"""

    try:
        response = call_reasoning_tier(prompt)
        result = json.loads(response)
        return result
    except Exception as e:
        return None


def handle_failure(
    invocation_id: str,
    agent_type: str,
    agent_tier: int,
    model_used: str,
    task_description: str,
    error: str,
    error_type: Optional[str] = None,
    attempt_number: int = 1
) -> Dict[str, Any]:
    """
    Main entry point: Analyze failure and return recovery plan.

    Args:
        invocation_id: Unique identifier for this invocation
        agent_type: Type of agent (e.g., "researcher", "builder", "analyst")
        agent_tier: Tier level (0=conductor, 1=pm, 2=specialist, 3=executor)
        model_used: Model that failed
        task_description: What the agent was trying to do
        error: Error message
        error_type: Optional explicit error type
        attempt_number: Which attempt is this (1-based)

    Returns:
        RecoveryPlan dict with strategy, reasoning, next steps
    """
    ensure_recovery_dirs()

    # Categorize the error
    category = categorize_error(error, error_type)

    # Log the failure
    failure_entry = {
        "timestamp": datetime.now().isoformat(),
        "invocation_id": invocation_id,
        "agent_type": agent_type,
        "agent_tier": agent_tier,
        "model_used": model_used,
        "task_description": task_description,
        "error_category": category.value,
        "error_message": error,
        "attempt_number": attempt_number
    }

    failures_log = NSOS_DIR / "recovery" / "failures.jsonl"
    with open(failures_log, "a") as f:
        f.write(json.dumps(failure_entry) + "\n")

    # Try LLM-based recovery analysis first
    recovery_plan = None
    llm_result = None

    if HAS_LLM:
        llm_result = llm_recovery_analysis(
            category, agent_type, agent_tier, model_used, task_description, error, attempt_number
        )

    if llm_result:
        strategy = RecoveryStrategy(llm_result["strategy"])
        confidence = llm_result.get("confidence", 0.7)
        reasoning = llm_result.get("reasoning", "LLM-guided recovery")
    else:
        # Fall back to rule-based fast path
        strategy = rule_based_recovery(category, agent_tier, attempt_number, task_description)
        confidence = 0.6
        reasoning = f"Rule-based recovery: {category.value} error at tier {agent_tier}"

    # Build recovery plan
    recovery_plan = {
        "invocation_id": invocation_id,
        "timestamp": datetime.now().isoformat(),
        "failure_id": f"{invocation_id}:{attempt_number}",
        "strategy": strategy.value,
        "reasoning": reasoning,
        "error_category": category.value,
        "confidence": confidence,
        "new_model": llm_result.get("recommended_model") if llm_result else None,
        "new_tier": agent_tier + 1 if strategy == RecoveryStrategy.ESCALATE_TIER else None,
        "simplified_task": None,
        "sub_tasks": [],
        "max_attempts": 3 if strategy in [RecoveryStrategy.RETRY_SAME, RecoveryStrategy.RETRY_DIFFERENT_MODEL] else 1,
        "should_retry_immediately": llm_result.get("should_retry_immediately", False) if llm_result else False
    }

    # Enhance plan with strategy-specific details
    if strategy == RecoveryStrategy.RETRY_SIMPLER:
        recovery_plan["simplified_task"] = f"Simplified: {task_description[:50]}..."

    elif strategy == RecoveryStrategy.DECOMPOSE_FURTHER:
        recovery_plan["sub_tasks"] = [
            "Subtask 1: Break down original task",
            "Subtask 2: Execute components",
            "Subtask 3: Integrate results"
        ]

    return recovery_plan


def log_recovery(failure_id: str, strategy: str, success: bool, details: Optional[str] = None) -> None:
    """Log the outcome of a recovery attempt."""
    ensure_recovery_dirs()

    recovery_entry = {
        "timestamp": datetime.now().isoformat(),
        "failure_id": failure_id,
        "strategy": strategy,
        "success": success,
        "details": details
    }

    recoveries_log = NSOS_DIR / "recovery" / "recoveries.jsonl"
    with open(recoveries_log, "a") as f:
        f.write(json.dumps(recovery_entry) + "\n")


def get_recovery_stats(lookback_hours: int = 24) -> Dict[str, Any]:
    """Analyze recovery statistics over recent time period."""
    ensure_recovery_dirs()

    failures_log = NSOS_DIR / "recovery" / "failures.jsonl"
    recoveries_log = NSOS_DIR / "recovery" / "recoveries.jsonl"

    if not failures_log.exists() or not recoveries_log.exists():
        return {"message": "No recovery data yet"}

    cutoff_time = datetime.now() - timedelta(hours=lookback_hours)

    # Count failures by category and strategy outcomes
    failure_categories = defaultdict(int)
    strategy_success = defaultdict(lambda: {"success": 0, "total": 0})
    agent_failure_count = defaultdict(int)
    mttr_list = []

    failures_by_id = {}
    with open(failures_log) as f:
        for line in f:
            entry = json.loads(line)
            ts = datetime.fromisoformat(entry["timestamp"])
            if ts < cutoff_time:
                continue
            failure_categories[entry["error_category"]] += 1
            agent_failure_count[entry["agent_type"]] += 1
            failures_by_id[entry["invocation_id"]] = entry

    with open(recoveries_log) as f:
        for line in f:
            entry = json.loads(line)
            ts = datetime.fromisoformat(entry["timestamp"])
            if ts < cutoff_time:
                continue

            strategy = entry["strategy"]
            strategy_success[strategy]["total"] += 1
            if entry["success"]:
                strategy_success[strategy]["success"] += 1

    # Compute success rates and MTTR
    stats = {
        "lookback_hours": lookback_hours,
        "total_failures": sum(failure_categories.values()),
        "failure_categories": dict(failure_categories),
        "strategy_success_rates": {},
        "agent_failure_counts": dict(agent_failure_count),
        "mttr_minutes": None
    }

    for strategy, counts in strategy_success.items():
        if counts["total"] > 0:
            stats["strategy_success_rates"][strategy] = {
                "success_count": counts["success"],
                "total_attempts": counts["total"],
                "success_rate": counts["success"] / counts["total"]
            }

    return stats


def analyze_failure_patterns(n: int = 100) -> Dict[str, Any]:
    """Use LLM to identify systemic failure patterns."""
    if not HAS_LLM:
        return {"message": "LLM not available"}

    ensure_recovery_dirs()
    failures_log = NSOS_DIR / "recovery" / "failures.jsonl"

    if not failures_log.exists():
        return {"message": "No failures to analyze"}

    # Load recent failures
    failures = []
    with open(failures_log) as f:
        for line in f:
            failures.append(json.loads(line))

    recent = failures[-n:] if len(failures) > n else failures

    # Group by agent type and model
    groups = defaultdict(list)
    for failure in recent:
        key = (failure["agent_type"], failure["model_used"])
        groups[key].append(failure)

    # Identify patterns
    patterns = []
    for (agent_type, model), group_failures in groups.items():
        if len(group_failures) >= 3:
            error_categories = defaultdict(int)
            for f in group_failures:
                error_categories[f["error_category"]] += 1

            most_common = max(error_categories.items(), key=lambda x: x[1])

            patterns.append({
                "agent_type": agent_type,
                "model": model,
                "failure_count": len(group_failures),
                "most_common_error": most_common[0],
                "error_frequency": most_common[1]
            })

    analysis = {
        "analyzed_failure_count": len(recent),
        "patterns_found": len(patterns),
        "high_frequency_patterns": sorted(
            patterns,
            key=lambda x: x["error_frequency"],
            reverse=True
        )[:5]
    }

    return analysis


def circuit_breaker(agent_type: str, model_used: str, lookback_hours: int = 1) -> Dict[str, Any]:
    """
    Check if agent+model combo should be circuit-broken (disabled).
    If same combo fails 3+ times in lookback period, it's temporarily disabled.
    """
    ensure_recovery_dirs()
    failures_log = NSOS_DIR / "recovery" / "failures.jsonl"

    if not failures_log.exists():
        return {"should_disable": False, "failure_count": 0}

    cutoff_time = datetime.now() - timedelta(hours=lookback_hours)
    failure_count = 0

    with open(failures_log) as f:
        for line in f:
            entry = json.loads(line)
            ts = datetime.fromisoformat(entry["timestamp"])
            if ts < cutoff_time:
                continue

            if entry["agent_type"] == agent_type and entry["model_used"] == model_used:
                failure_count += 1

    should_disable = failure_count >= 3

    return {
        "agent_type": agent_type,
        "model": model_used,
        "failure_count": failure_count,
        "should_disable": should_disable,
        "lookback_hours": lookback_hours,
        "threshold": 3
    }


def get_circuit_breaker_status() -> List[Dict[str, Any]]:
    """Get all active circuit breakers."""
    ensure_recovery_dirs()
    failures_log = NSOS_DIR / "recovery" / "failures.jsonl"

    if not failures_log.exists():
        return []

    cutoff_time = datetime.now() - timedelta(hours=1)
    combos = defaultdict(int)

    with open(failures_log) as f:
        for line in f:
            entry = json.loads(line)
            ts = datetime.fromisoformat(entry["timestamp"])
            if ts < cutoff_time:
                continue

            key = (entry["agent_type"], entry["model_used"])
            combos[key] += 1

    breakers = []
    for (agent_type, model), count in combos.items():
        if count >= 3:
            breakers.append({
                "agent_type": agent_type,
                "model": model,
                "failure_count": count,
                "status": "ACTIVE"
            })

    return breakers


def main():
    """CLI interface for cascade handler."""
    parser = argparse.ArgumentParser(description="NSOS Cascade Handler")
    parser.add_argument("--failures", action="store_true", help="Show recent failures")
    parser.add_argument("--recoveries", action="store_true", help="Show recovery history")
    parser.add_argument("--stats", action="store_true", help="Show recovery statistics")
    parser.add_argument("--analyze", action="store_true", help="Analyze failure patterns")
    parser.add_argument("--circuit-status", action="store_true", help="Show circuit breaker status")
    parser.add_argument("--lookback", type=int, default=24, help="Lookback hours for stats")

    args = parser.parse_args()

    ensure_recovery_dirs()

    if args.failures:
        failures_log = NSOS_DIR / "recovery" / "failures.jsonl"
        if failures_log.exists():
            with open(failures_log) as f:
                lines = f.readlines()
                for line in lines[-20:]:  # Last 20
                    print(line.strip())
        else:
            print("No failure log found")

    elif args.recoveries:
        recoveries_log = NSOS_DIR / "recovery" / "recoveries.jsonl"
        if recoveries_log.exists():
            with open(recoveries_log) as f:
                lines = f.readlines()
                for line in lines[-20:]:  # Last 20
                    print(line.strip())
        else:
            print("No recovery log found")

    elif args.stats:
        stats = get_recovery_stats(lookback_hours=args.lookback)
        print(json.dumps(stats, indent=2))

    elif args.analyze:
        patterns = analyze_failure_patterns(n=100)
        print(json.dumps(patterns, indent=2))

    elif args.circuit_status:
        breakers = get_circuit_breaker_status()
        if breakers:
            print("ACTIVE CIRCUIT BREAKERS:")
            for breaker in breakers:
                print(json.dumps(breaker, indent=2))
        else:
            print("No active circuit breakers")

    else:
        parser.print_help()


if __name__ == "__main__":
    main()
