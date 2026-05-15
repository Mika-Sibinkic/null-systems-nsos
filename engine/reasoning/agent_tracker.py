#!/usr/bin/env python3
"""
NSOS Agent Performance Tracker
Tracks invocation metrics for every agent across all tiers.
Enables data-driven decisions about agent improvements and restructuring.
"""

import sys
import json
import argparse
from pathlib import Path
from datetime import datetime, timedelta
from collections import defaultdict
from dataclasses import dataclass, asdict
from typing import Optional, Dict, List, Any
import time
import uuid

# Import paths
NSOS_DIR = Path(__file__).parent
sys.path.insert(0, str(NSOS_DIR))

# Try to import llm_adapter for reasoning tier
try:
    import llm_adapter
    HAS_LLM = True
except ImportError:
    HAS_LLM = False


@dataclass
class Invocation:
    """Single agent invocation record."""
    id: str
    agent_type: str
    agent_tier: int
    model_used: str
    project: str
    task_type: str
    task_description: str
    start_time: float
    end_time: Optional[float] = None
    duration_ms: Optional[int] = None
    success: Optional[bool] = None
    output_quality_score: Optional[int] = None
    tokens_in: int = 0
    tokens_out: int = 0
    error: Optional[str] = None
    decomposition_id: Optional[str] = None

    def to_dict(self):
        return asdict(self)


class AgentTracker:
    """Track and analyze agent performance across NSOS system."""

    def __init__(self):
        self.agents_dir = NSOS_DIR / "agents"
        self.invocations_file = self.agents_dir / "invocations.jsonl"
        self.profiles_file = self.agents_dir / "profiles.json"
        self.agents_dir.mkdir(exist_ok=True)

    def start_invocation(
        self,
        agent_type: str,
        agent_tier: int,
        model_used: str,
        project: str,
        task_type: str,
        task_description: str,
        decomposition_id: Optional[str] = None,
    ) -> tuple[str, float]:
        """Start tracking an agent invocation. Returns (invocation_id, start_time)."""
        invocation_id = str(uuid.uuid4())[:8]
        start_time = time.time()

        invocation = Invocation(
            id=invocation_id,
            agent_type=agent_type,
            agent_tier=agent_tier,
            model_used=model_used,
            project=project,
            task_type=task_type,
            task_description=task_description,
            start_time=start_time,
            decomposition_id=decomposition_id,
        )

        # Append to JSONL log
        with open(self.invocations_file, "a") as f:
            f.write(json.dumps(invocation.to_dict()) + "\n")

        return invocation_id, start_time

    def end_invocation(
        self,
        invocation_id: str,
        success: bool,
        output_quality_score: Optional[int] = None,
        tokens_in: int = 0,
        tokens_out: int = 0,
        error: Optional[str] = None,
    ) -> None:
        """Complete an invocation record."""
        end_time = time.time()

        # Read all invocations, find and update the target
        invocations = []
        if self.invocations_file.exists():
            with open(self.invocations_file, "r") as f:
                invocations = [json.loads(line) for line in f if line.strip()]

        # Find and update the invocation
        for inv in invocations:
            if inv["id"] == invocation_id:
                inv["end_time"] = end_time
                inv["duration_ms"] = int((end_time - inv["start_time"]) * 1000)
                inv["success"] = success
                inv["output_quality_score"] = output_quality_score
                inv["tokens_in"] = tokens_in
                inv["tokens_out"] = tokens_out
                inv["error"] = error
                break

        # Write back
        with open(self.invocations_file, "w") as f:
            for inv in invocations:
                f.write(json.dumps(inv) + "\n")

    def _load_invocations(
        self, agent_type: Optional[str] = None, project: Optional[str] = None, days: int = 30
    ) -> List[Dict[str, Any]]:
        """Load invocations from JSONL, filtered by agent_type and/or project."""
        if not self.invocations_file.exists():
            return []

        cutoff_time = time.time() - (days * 86400)
        invocations = []

        with open(self.invocations_file, "r") as f:
            for line in f:
                if not line.strip():
                    continue
                inv = json.loads(line)

                # Filter by time
                if inv.get("start_time", 0) < cutoff_time:
                    continue

                # Filter by agent_type
                if agent_type and inv.get("agent_type") != agent_type:
                    continue

                # Filter by project
                if project and inv.get("project") != project:
                    continue

                invocations.append(inv)

        return invocations

    def get_agent_stats(
        self, agent_type: Optional[str] = None, project: Optional[str] = None, days: int = 30
    ) -> Dict[str, Any]:
        """Get aggregated performance stats for agents."""
        invocations = self._load_invocations(agent_type, project, days)

        if not invocations:
            return {"error": "No invocations found"}

        # Group by agent_type if not filtering by specific type
        stats_by_type = defaultdict(lambda: {
            "count": 0,
            "success_count": 0,
            "total_duration_ms": 0,
            "total_quality": 0,
            "quality_count": 0,
            "total_tokens_in": 0,
            "total_tokens_out": 0,
        })

        for inv in invocations:
            atype = inv.get("agent_type", "unknown")
            stats = stats_by_type[atype]
            stats["count"] += 1

            if inv.get("success"):
                stats["success_count"] += 1

            if inv.get("duration_ms"):
                stats["total_duration_ms"] += inv["duration_ms"]

            if inv.get("output_quality_score") is not None:
                stats["total_quality"] += inv["output_quality_score"]
                stats["quality_count"] += 1

            stats["total_tokens_in"] += inv.get("tokens_in", 0)
            stats["total_tokens_out"] += inv.get("tokens_out", 0)

        # Calculate derived metrics
        result = {}
        for atype, stats in stats_by_type.items():
            result[atype] = {
                "total_invocations": stats["count"],
                "success_rate": round(stats["success_count"] / stats["count"], 3) if stats["count"] > 0 else 0,
                "avg_duration_ms": round(stats["total_duration_ms"] / stats["count"], 1) if stats["count"] > 0 else 0,
                "avg_quality_score": round(stats["total_quality"] / stats["quality_count"], 1) if stats["quality_count"] > 0 else None,
                "total_tokens_in": stats["total_tokens_in"],
                "total_tokens_out": stats["total_tokens_out"],
            }

        return result

    def get_slowest_agents(self, n: int = 5) -> List[Dict[str, Any]]:
        """Identify the slowest agents by average duration."""
        invocations = self._load_invocations(days=30)

        if not invocations:
            return []

        # Group by agent_type and calculate avg duration
        agent_durations = defaultdict(list)
        for inv in invocations:
            if inv.get("duration_ms"):
                agent_durations[inv.get("agent_type", "unknown")].append(inv["duration_ms"])

        # Calculate averages
        avg_by_type = [
            {
                "agent_type": atype,
                "avg_duration_ms": round(sum(durations) / len(durations), 1),
                "invocation_count": len(durations),
            }
            for atype, durations in agent_durations.items()
        ]

        # Sort descending and return top n
        return sorted(avg_by_type, key=lambda x: x["avg_duration_ms"], reverse=True)[:n]

    def get_failing_agents(self, min_failure_rate: float = 0.1) -> List[Dict[str, Any]]:
        """Identify agents with failure rates >= min_failure_rate."""
        invocations = self._load_invocations(days=30)

        if not invocations:
            return []

        # Group by agent_type and count failures
        agent_results = defaultdict(lambda: {"success": 0, "failure": 0})
        for inv in invocations:
            atype = inv.get("agent_type", "unknown")
            if inv.get("success"):
                agent_results[atype]["success"] += 1
            else:
                agent_results[atype]["failure"] += 1

        # Calculate failure rates
        failing = []
        for atype, results in agent_results.items():
            total = results["success"] + results["failure"]
            failure_rate = results["failure"] / total if total > 0 else 0
            if failure_rate >= min_failure_rate:
                failing.append({
                    "agent_type": atype,
                    "failure_rate": round(failure_rate, 3),
                    "failures": results["failure"],
                    "successes": results["success"],
                    "total": total,
                })

        return sorted(failing, key=lambda x: x["failure_rate"], reverse=True)

    def get_model_comparison(self) -> Dict[str, Any]:
        """Compare performance across models and task types."""
        invocations = self._load_invocations(days=30)

        if not invocations:
            return {"error": "No invocations found"}

        # Group by (model, task_type)
        model_task_stats = defaultdict(lambda: {
            "count": 0,
            "success_count": 0,
            "total_quality": 0,
            "quality_count": 0,
        })

        for inv in invocations:
            key = (inv.get("model_used", "unknown"), inv.get("task_type", "unknown"))
            stats = model_task_stats[key]
            stats["count"] += 1

            if inv.get("success"):
                stats["success_count"] += 1

            if inv.get("output_quality_score") is not None:
                stats["total_quality"] += inv["output_quality_score"]
                stats["quality_count"] += 1

        # Format results
        result = {}
        for (model, task_type), stats in model_task_stats.items():
            key = f"{model} / {task_type}"
            result[key] = {
                "invocations": stats["count"],
                "success_rate": round(stats["success_count"] / stats["count"], 3) if stats["count"] > 0 else 0,
                "avg_quality": round(stats["total_quality"] / stats["quality_count"], 1) if stats["quality_count"] > 0 else None,
            }

        return result

    def recommend_improvements(self) -> Dict[str, Any]:
        """LLM-powered analysis of agent performance data."""
        if not HAS_LLM:
            return {"error": "llm_adapter not available; cannot generate recommendations"}

        failing = self.get_failing_agents(min_failure_rate=0.05)
        slowest = self.get_slowest_agents(n=3)
        stats = self.get_agent_stats(days=30)

        # Prepare context for LLM
        context = f"""
Agent Performance Data (30-day window):

Failing Agents (>5% failure rate):
{json.dumps(failing, indent=2)}

Slowest Agents:
{json.dumps(slowest, indent=2)}

Overall Statistics:
{json.dumps(stats, indent=2)}

Provide 3-5 specific, actionable recommendations for improving agent system performance.
Focus on high-impact changes: retiring failing agents, optimizing slow paths, or restructuring tiers.
"""

        try:
            response = llm_adapter.call(
                tier="reasoning",
                prompt=context,
                model="claude-3-7-sonnet-20250219",
            )
            return {
                "recommendations": response.get("content"),
                "confidence": "high" if failing or slowest else "medium",
            }
        except Exception as e:
            return {"error": f"LLM analysis failed: {str(e)}"}

    def generate_report(self, days: int = 7) -> str:
        """Generate a weekly agent performance report for Mika."""
        stats = self.get_agent_stats(days=days)
        slowest = self.get_slowest_agents(n=3)
        failing = self.get_failing_agents(min_failure_rate=0.1)
        model_compare = self.get_model_comparison()

        # Build report
        lines = [
            f"NSOS Agent Performance Report — {days}-Day Window",
            f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
            "",
            "SUMMARY",
            "=" * 60,
        ]

        if isinstance(stats, dict) and "error" not in stats:
            total_invocations = sum(s.get("total_invocations", 0) for s in stats.values())
            avg_success = sum(
                s.get("success_rate", 0) * s.get("total_invocations", 1)
                for s in stats.values()
            ) / max(total_invocations, 1)
            lines.extend([
                f"Total Invocations: {total_invocations}",
                f"Overall Success Rate: {round(avg_success * 100, 1)}%",
                "",
            ])

        lines.extend([
            "AGENT BREAKDOWN",
            "=" * 60,
        ])

        if isinstance(stats, dict) and "error" not in stats:
            for agent_type, metrics in stats.items():
                lines.append(f"{agent_type}:")
                lines.append(f"  Invocations: {metrics['total_invocations']}")
                lines.append(f"  Success Rate: {round(metrics['success_rate'] * 100, 1)}%")
                lines.append(f"  Avg Duration: {metrics['avg_duration_ms']}ms")
                if metrics['avg_quality_score']:
                    lines.append(f"  Avg Quality: {metrics['avg_quality_score']}/100")
                lines.append("")

        if slowest:
            lines.extend([
                "PERFORMANCE BOTTLENECKS (Top 3 Slowest)",
                "=" * 60,
            ])
            for item in slowest:
                lines.append(f"{item['agent_type']}: {item['avg_duration_ms']}ms avg ({item['invocation_count']} invocations)")
            lines.append("")

        if failing:
            lines.extend([
                "RELIABILITY CONCERNS (>10% failure rate)",
                "=" * 60,
            ])
            for item in failing:
                lines.append(f"{item['agent_type']}: {round(item['failure_rate'] * 100, 1)}% failures ({item['failures']}/{item['total']})")
            lines.append("")

        lines.extend([
            "MODEL PERFORMANCE",
            "=" * 60,
        ])
        for combo, metrics in sorted(model_compare.items())[:5]:
            lines.append(f"{combo}: {round(metrics['success_rate'] * 100, 1)}% success, {metrics.get('avg_quality', 'N/A')} quality")

        lines.append("")
        recommendations = self.recommend_improvements()
        if "recommendations" in recommendations:
            lines.extend([
                "RECOMMENDATIONS",
                "=" * 60,
                recommendations["recommendations"],
            ])

        return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description="NSOS Agent Performance Tracker")
    parser.add_argument("--stats", action="store_true", help="Show agent statistics")
    parser.add_argument("--report", action="store_true", help="Generate weekly report")
    parser.add_argument("--slowest", action="store_true", help="Show slowest agents")
    parser.add_argument("--failing", action="store_true", help="Show failing agents")
    parser.add_argument("--model-compare", action="store_true", help="Compare model performance")
    parser.add_argument("--recommend", action="store_true", help="Generate improvement recommendations")
    parser.add_argument("--days", type=int, default=30, help="Analysis window (days)")

    args = parser.parse_args()

    tracker = AgentTracker()

    if args.stats:
        stats = tracker.get_agent_stats(days=args.days)
        print(json.dumps(stats, indent=2))

    elif args.slowest:
        slowest = tracker.get_slowest_agents(n=5)
        print(json.dumps(slowest, indent=2))

    elif args.failing:
        failing = tracker.get_failing_agents(min_failure_rate=0.1)
        print(json.dumps(failing, indent=2))

    elif args.model_compare:
        comparison = tracker.get_model_comparison()
        print(json.dumps(comparison, indent=2))

    elif args.recommend:
        recommendations = tracker.recommend_improvements()
        print(json.dumps(recommendations, indent=2))

    elif args.report:
        report = tracker.generate_report(days=args.days)
        print(report)

    else:
        parser.print_help()


if __name__ == "__main__":
    main()
