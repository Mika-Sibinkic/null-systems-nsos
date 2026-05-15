#!/usr/bin/env python3
"""
NSOS Meta Router — Intelligent Task Routing & Auditing
Version: 1.0

Routes tasks to optimal LLM tier based on complexity, history, and required capabilities.
Performs pre-flight and post-flight audits to validate routing decisions.

Task taxonomy:
- coding: Generate, fix, or refactor code
- orchestration: Task decomposition, planning, dispatch
- analysis: Data analysis, pattern detection, synthesis
- classification: Categorize, label, or structure data
- generation: Create original content (docs, specs, designs)
- verification: Check, test, validate outputs
- research: Information gathering, exploration
- execution: Deterministic operations (API calls, CLI)
"""

import json
import sys
from pathlib import Path
from datetime import datetime
from typing import Optional, Dict, Any, List
from collections import defaultdict

# Setup
NSOS_DIR = Path(__file__).parent
ROUTING_DIR = NSOS_DIR / "routing"
ROUTING_DIR.mkdir(exist_ok=True)

DECISIONS_LOG = ROUTING_DIR / "decisions.jsonl"
STATS_FILE = ROUTING_DIR / "stats.json"

# Try to import llm_adapter
try:
    from llm_adapter import call_llm, MODELS
    HAS_LLM = True
except ImportError:
    HAS_LLM = False


# Task taxonomy
TASK_TYPES = {
    "coding": {
        "description": "Generate, fix, or refactor code",
        "required_capabilities": ["code_generation", "syntax_understanding"],
        "typical_tiers": {"reasoning": 0.3, "primary": 0.6, "fast": 0.1},
    },
    "orchestration": {
        "description": "Task decomposition, planning, dispatch",
        "required_capabilities": ["reasoning", "project_context", "tier_assignment"],
        "typical_tiers": {"reasoning": 0.7, "primary": 0.2, "fast": 0.1},
    },
    "analysis": {
        "description": "Data analysis, pattern detection, synthesis",
        "required_capabilities": ["reasoning", "pattern_recognition"],
        "typical_tiers": {"reasoning": 0.4, "primary": 0.5, "fast": 0.1},
    },
    "classification": {
        "description": "Categorize, label, or structure data",
        "required_capabilities": ["classification", "consistency"],
        "typical_tiers": {"primary": 0.5, "fast": 0.5},
    },
    "generation": {
        "description": "Create original content (docs, specs, designs)",
        "required_capabilities": ["creativity", "structure", "domain_knowledge"],
        "typical_tiers": {"reasoning": 0.2, "primary": 0.7, "fast": 0.1},
    },
    "verification": {
        "description": "Check, test, validate outputs",
        "required_capabilities": ["quality_judgment", "rigor"],
        "typical_tiers": {"primary": 0.6, "fast": 0.4},
    },
    "research": {
        "description": "Information gathering, exploration",
        "required_capabilities": ["information_synthesis", "breadth"],
        "typical_tiers": {"reasoning": 0.3, "primary": 0.5, "fast": 0.2},
    },
    "execution": {
        "description": "Deterministic operations (API calls, CLI)",
        "required_capabilities": ["precision", "error_handling"],
        "typical_tiers": {"primary": 0.5, "fast": 0.5},
    },
}


class TaskRouter:
    """Routes tasks to optimal LLM tier."""

    def __init__(self):
        self.decisions = []
        self.stats = self._load_stats()
        self._load_decisions()

    def _load_stats(self) -> Dict[str, Any]:
        """Load routing statistics."""
        if not STATS_FILE.exists():
            return {
                "total_routed": 0,
                "routing_accuracy": defaultdict(lambda: {"correct": 0, "total": 0}),
                "tier_distribution": defaultdict(int),
            }
        try:
            with open(STATS_FILE) as f:
                return json.load(f)
        except (json.JSONDecodeError, IOError):
            return {
                "total_routed": 0,
                "routing_accuracy": defaultdict(lambda: {"correct": 0, "total": 0}),
                "tier_distribution": defaultdict(int),
            }

    def _load_decisions(self) -> None:
        """Load past routing decisions."""
        if not DECISIONS_LOG.exists():
            return
        try:
            with open(DECISIONS_LOG) as f:
                for line in f:
                    if line.strip():
                        try:
                            self.decisions.append(json.loads(line))
                        except json.JSONDecodeError:
                            continue
        except IOError:
            pass

    def _save_decision(self, decision: Dict[str, Any]) -> None:
        """Save routing decision to log."""
        with open(DECISIONS_LOG, "a") as f:
            f.write(json.dumps(decision) + "\n")

    def _save_stats(self) -> None:
        """Save routing statistics."""
        # Convert defaultdicts for JSON serialization
        stats = {
            "total_routed": self.stats.get("total_routed", 0),
            "routing_accuracy": {k: dict(v) for k, v in self.stats.get("routing_accuracy", {}).items()},
            "tier_distribution": dict(self.stats.get("tier_distribution", {})),
        }
        with open(STATS_FILE, "w") as f:
            json.dump(stats, f, indent=2)

    def route_task(
        self,
        task_description: str,
        task_type: Optional[str] = None,
        project: Optional[str] = None,
        complexity_hint: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Route a task to the best tier.

        Args:
            task_description: What needs to be done
            task_type: One of TASK_TYPES keys (auto-detected if not provided)
            project: Project context
            complexity_hint: "low", "medium", "high"

        Returns:
            {tier, confidence, reasoning, pre_flight_checks}
        """
        # Auto-detect task type if not provided
        if not task_type:
            task_type = self._detect_task_type(task_description)

        # Get routing recommendation
        task_meta = TASK_TYPES.get(task_type, TASK_TYPES["analysis"])
        routing_probs = task_meta.get("typical_tiers", {})

        # Adjust based on complexity hint
        if complexity_hint == "high":
            routing_probs = {k: v * 1.3 for k, v in routing_probs.items()}
        elif complexity_hint == "low":
            routing_probs = {k: v * 0.7 for k, v in routing_probs.items()}

        # Normalize to probabilities
        total = sum(routing_probs.values())
        routing_probs = {k: v / total for k, v in routing_probs.items()}

        # Select best tier
        best_tier = max(routing_probs.items(), key=lambda x: x[1])[0]
        confidence = routing_probs[best_tier]

        # Pre-flight audit
        pre_flight = self._pre_flight_audit(
            task_description, task_type, best_tier
        )

        # Build decision record
        decision = {
            "id": f"route-{datetime.now().isoformat()}",
            "timestamp": datetime.now().isoformat(),
            "task_description": task_description[:200],
            "task_type": task_type,
            "project": project,
            "complexity_hint": complexity_hint,
            "selected_tier": best_tier,
            "confidence": confidence,
            "reasoning": f"{task_type} → {best_tier} (confidence: {confidence:.2f})",
            "pre_flight_checks": pre_flight,
            "output_quality_score": None,
            "post_flight_passed": None,
        }

        self._save_decision(decision)
        self.stats["total_routed"] = self.stats.get("total_routed", 0) + 1

        return {
            "tier": best_tier,
            "confidence": confidence,
            "reasoning": decision["reasoning"],
            "pre_flight_checks": pre_flight,
            "routing_id": decision["id"],
        }

    def _detect_task_type(self, description: str) -> str:
        """Auto-detect task type from description."""
        desc_lower = description.lower()

        keywords = {
            "coding": ["code", "function", "class", "bug", "fix", "refactor", "implement"],
            "orchestration": ["decompose", "plan", "dispatch", "coordinate", "tier"],
            "analysis": ["analyze", "pattern", "synthesize", "understand", "detect"],
            "classification": ["classify", "categorize", "label", "tag", "organize"],
            "generation": ["generate", "create", "write", "design", "draft"],
            "verification": ["check", "test", "validate", "verify", "audit"],
            "research": ["research", "explore", "investigate", "discover", "gather"],
            "execution": ["execute", "call", "api", "cli", "script"],
        }

        scores = {}
        for task_type, words in keywords.items():
            score = sum(1 for word in words if word in desc_lower)
            scores[task_type] = score

        # Return highest-scoring type, default to analysis
        return max(scores.items(), key=lambda x: x[1])[0] if any(scores.values()) else "analysis"

    def _pre_flight_audit(
        self,
        task_description: str,
        task_type: str,
        selected_tier: str,
    ) -> Dict[str, bool]:
        """
        Validate task before routing.

        Returns:
            {has_clear_success_criteria, has_sufficient_context, tier_has_capability}
        """
        checks = {
            "has_clear_success_criteria": any(
                word in task_description.lower()
                for word in ["should", "must", "verify", "check", "ensure"]
            ),
            "has_sufficient_context": len(task_description) > 20,
            "tier_has_capability": True,  # Assume all tiers have required capabilities
        }

        return checks

    def post_flight_audit(
        self,
        routing_id: str,
        output: str,
        success: bool,
        quality_score: Optional[float] = None,
    ) -> Dict[str, Any]:
        """
        Validate output after execution.

        Args:
            routing_id: ID from route_task
            output: Generated output
            success: Whether execution succeeded
            quality_score: Human-provided quality score (0-1)

        Returns:
            {audit_passed, quality_assessment, confidence_adjustment}
        """
        # Find the routing decision
        decision = next((d for d in self.decisions if d.get("id") == routing_id), None)

        if not decision:
            return {"error": "Routing decision not found"}

        # Assess output quality
        quality_checks = {
            "output_not_empty": len(output.strip()) > 0,
            "output_coherent": "\n" in output or len(output) > 100,
            "success_confirmed": success,
        }

        all_passed = all(quality_checks.values())

        # Confidence adjustment
        confidence_delta = 0.0
        if all_passed and quality_score and quality_score > 0.7:
            confidence_delta = 0.05
        elif not success or (quality_score and quality_score < 0.5):
            confidence_delta = -0.1

        # Update decision record
        decision["output_quality_score"] = quality_score or 0.5
        decision["post_flight_passed"] = all_passed
        decision["confidence_adjustment"] = confidence_delta

        # Update stats
        task_type = decision.get("task_type", "analysis")
        tier = decision.get("selected_tier", "primary")

        if task_type in self.stats["routing_accuracy"]:
            acc = self.stats["routing_accuracy"][task_type]
        else:
            acc = {"correct": 0, "total": 0}
            self.stats["routing_accuracy"][task_type] = acc

        acc["total"] = acc.get("total", 0) + 1
        if all_passed:
            acc["correct"] = acc.get("correct", 0) + 1

        self.stats["tier_distribution"][tier] = self.stats["tier_distribution"].get(tier, 0) + 1
        self._save_stats()

        return {
            "audit_passed": all_passed,
            "quality_checks": quality_checks,
            "confidence_adjustment": confidence_delta,
            "routing_accuracy_updated": True,
        }

    def get_routing_stats(self) -> Dict[str, Any]:
        """Get routing performance statistics."""
        return {
            "total_routed": self.stats.get("total_routed", 0),
            "by_task_type": {
                task_type: {
                    "total": acc.get("total", 0),
                    "correct": acc.get("correct", 0),
                    "accuracy": (
                        acc.get("correct", 0) / acc.get("total", 1)
                        if acc.get("total", 0) > 0
                        else 0.0
                    ),
                }
                for task_type, acc in self.stats.get("routing_accuracy", {}).items()
            },
            "tier_distribution": dict(self.stats.get("tier_distribution", {})),
        }


def main():
    """CLI interface."""
    import argparse

    parser = argparse.ArgumentParser(description="NSOS Meta Router")
    parser.add_argument("--route", help="Route a task", type=str)
    parser.add_argument("--task-type", help="Task type hint", type=str)
    parser.add_argument("--project", help="Project context", type=str)
    parser.add_argument("--complexity", help="Complexity hint (low|medium|high)", type=str)
    parser.add_argument("--stats", help="Show routing statistics", action="store_true")

    args = parser.parse_args()

    router = TaskRouter()

    if args.route:
        result = router.route_task(
            task_description=args.route,
            task_type=args.task_type,
            project=args.project,
            complexity_hint=args.complexity,
        )
        print(json.dumps(result, indent=2))

    elif args.stats:
        stats = router.get_routing_stats()
        print(json.dumps(stats, indent=2))

    else:
        parser.print_help()


if __name__ == "__main__":
    main()
