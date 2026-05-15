#!/usr/bin/env python3
"""
NSOS Task Decomposer — Intelligent Task Decomposition Engine

When the operator says "take care of <project>", this module breaks that into a
structured execution plan with tier assignments, dependencies, and model selections.

Usage:
    python3 task_decomposer.py --decompose "take care of <project>"
    python3 task_decomposer.py --optimize dec-2026-04-05-001
    python3 task_decomposer.py --history
    python3 task_decomposer.py --patterns

Output: Structured JSON decompositions stored in routing/decompositions.jsonl
"""

# v1.0.0 — Initial release
# - Autonomous task decomposition with LLM reasoning tier
# - Decomposition history tracking and analysis
# - Plan optimization using fast tier
# - Pattern detection for caching and reuse

import argparse
import json
import os
import sys
from datetime import datetime
from pathlib import Path
from typing import Optional, Any
import subprocess

try:
    import anthropic
except ImportError:
    anthropic = None

# ─────────────────────────────────────────────────────────────────────────
# CONFIGURATION
# ─────────────────────────────────────────────────────────────────────────

NSOS_DIR = Path(__file__).parent
PROJECT_ROOT = NSOS_DIR.parent.parent
ORCHESTRATOR_DIR = PROJECT_ROOT / ".claude" / "orchestrator"
ROUTING_DIR = NSOS_DIR / "routing"
MEMORY_DIR = NSOS_DIR / "memory"

# Ensure directories exist
ROUTING_DIR.mkdir(exist_ok=True)
MEMORY_DIR.mkdir(exist_ok=True)

DECOMPOSITIONS_LOG = ROUTING_DIR / "decompositions.jsonl"
PATTERNS_LOG = MEMORY_DIR / "decomposition_patterns.json"
TIER_CONFIG_FILE = NSOS_DIR / "tier_config.json"

# Identity (parameterized — defaults to generic strings)
OPERATOR_NAME = os.environ.get("OPERATOR_NAME", "operator")
COMPANY_NAME = os.environ.get("COMPANY_NAME", "the firm")

# Default model selection by tier (overridable via tier_config.json)
DEFAULT_MODEL_TIERS = {
    "reasoning": "claude-3-7-sonnet-20250219",  # Extended thinking for complex decomposition
    "primary": "claude-3-5-sonnet-20241022",    # Standard multi-turn reasoning
    "fast": "claude-3-5-haiku-20241022",        # Fast, cheap, for optimization passes
    "coding": "claude-3-5-sonnet-20241022",     # Code generation and analysis
    "local": None,                               # Not implemented for NSOS v1
}

# Default tier assignment definitions (overridable via tier_config.json)
DEFAULT_TIER_DEFINITIONS = {
    0: {
        "name": "Conductor",
        "agent": "nsos_conductor",
        "capability": "orchestration, planning, dispatch",
        "scope": "system-wide",
    },
    1: {
        "name": "Project Manager",
        "agent": "project_manager",
        "capability": "project coordination, execution flow",
        "scope": "single project",
    },
    2: {
        "name": "Specialist",
        "agent": "specialist_agent",
        "capability": "narrow domain expertise",
        "scope": "feature or component",
    },
    3: {
        "name": "Executor",
        "agent": "executor_script",
        "capability": "deterministic execution, API calls",
        "scope": "single operation",
    },
}


def _load_tier_config() -> tuple:
    """Load model tiers and tier definitions from config (falls back to defaults)."""
    if TIER_CONFIG_FILE.exists():
        try:
            with open(TIER_CONFIG_FILE) as f:
                cfg = json.load(f)
            model_tiers = cfg.get("model_tiers", DEFAULT_MODEL_TIERS)
            tier_defs_raw = cfg.get("tier_definitions", DEFAULT_TIER_DEFINITIONS)
            # JSON keys are strings; coerce tier keys to int
            tier_defs = {int(k): v for k, v in tier_defs_raw.items()}
            return model_tiers, tier_defs
        except Exception as e:
            print(f"WARNING: Failed to load {TIER_CONFIG_FILE}: {e}. Using defaults.", file=sys.stderr)
    return DEFAULT_MODEL_TIERS, DEFAULT_TIER_DEFINITIONS


MODEL_TIERS, TIER_DEFINITIONS = _load_tier_config()

# ─────────────────────────────────────────────────────────────────────────
# LLM INTERFACE
# ─────────────────────────────────────────────────────────────────────────


def call_llm(
    prompt: str,
    model_tier: str = "primary",
    system: Optional[str] = None,
    temperature: float = 1.0,
    max_tokens: int = 8000,
) -> str:
    """
    Call Claude API with the specified model tier.

    Args:
        prompt: User message to send
        model_tier: One of reasoning|primary|fast|coding
        system: System prompt (optional)
        temperature: Sampling temperature
        max_tokens: Max output tokens

    Returns:
        Response text from Claude

    Raises:
        ImportError: If anthropic library is not installed
        ValueError: If model tier is not configured
    """
    if anthropic is None:
        raise ImportError(
            "The anthropic library is required. Install with: pip install anthropic"
        )

    model = MODEL_TIERS.get(model_tier, MODEL_TIERS["primary"])
    if not model:
        raise ValueError(f"No model configured for tier: {model_tier}")

    client = anthropic.Anthropic()

    try:
        response = client.messages.create(
            model=model,
            max_tokens=max_tokens,
            temperature=temperature,
            system=system or f"You are a task decomposition expert for the {COMPANY_NAME} framework.",
            messages=[{"role": "user", "content": prompt}],
        )
        return response.content[0].text
    except Exception as e:
        print(f"ERROR calling LLM tier={model_tier}: {e}", file=sys.stderr)
        raise


# ─────────────────────────────────────────────────────────────────────────
# PROJECT CONTEXT LOADING
# ─────────────────────────────────────────────────────────────────────────


def load_projects_context() -> dict:
    """
    Load project context from orchestrator/projects.json.

    Returns:
        Dictionary of project metadata keyed by project ID
    """
    projects_file = ORCHESTRATOR_DIR / "projects.json"
    if not projects_file.exists():
        return {}

    try:
        with open(projects_file) as f:
            data = json.load(f)
        projects = {}
        for proj in data.get("projects", []):
            projects[proj.get("id")] = proj
        return projects
    except Exception as e:
        print(f"WARNING: Could not load projects context: {e}", file=sys.stderr)
        return {}


def detect_project_from_command(command: str, projects: dict) -> Optional[str]:
    """
    Detect which project the command refers to.

    Args:
        command: Natural language command
        projects: Project context dictionary

    Returns:
        Project ID if detected, None otherwise
    """
    command_lower = command.lower()

    for proj_id, proj_data in projects.items():
        name_lower = proj_data.get("name", "").lower()
        if name_lower in command_lower:
            return proj_id

    return None


# ─────────────────────────────────────────────────────────────────────────
# DECOMPOSITION LOGIC
# ─────────────────────────────────────────────────────────────────────────


def decompose(
    command: str,
    project: Optional[str] = None,
    operator: Optional[str] = None,
) -> dict:
    """
    Decompose a natural language command into a structured execution plan.

    This is the main entry point. Takes a command like "take care of <project>"
    and returns a detailed plan with tasks, dependencies, tier assignments,
    and model selections.

    Args:
        command: Natural language command (e.g., "take care of <project>")
        project: Optional project ID override
        operator: User requesting decomposition (defaults to OPERATOR_NAME env)

    Returns:
        Decomposition dictionary with structure:
        {
            "id": "dec-YYYY-MM-DD-NNN",
            "timestamp": ISO timestamp,
            "command": original command,
            "project": detected or provided project ID,
            "operator": operator name,
            "tasks": [
                {
                    "id": "task-001",
                    "description": task description,
                    "tier": 0-3,
                    "agent_type": "pm|specialist|executor",
                    "model_class": "reasoning|primary|fast|coding|local",
                    "dependencies": ["task-NNN"],
                    "estimated_complexity": "low|medium|high",
                    "success_criteria": specific measurable condition,
                    "parallelizable_with": ["task-NNN"],
                }
            ],
            "execution_order": [[group1], [group2], ...],  # parallel grouping
            "estimated_total_steps": N,
            "metadata": {
                "reasoning": explanation of decomposition,
                "risk_factors": ["..."],
                "assumptions": ["..."],
            }
        }
    """
    projects = load_projects_context()

    # Default operator from env if not explicitly provided
    if operator is None:
        operator = OPERATOR_NAME

    # Detect project if not provided
    if not project:
        project = detect_project_from_command(command, projects)

    # Build context for LLM
    project_info = projects.get(project, {}) if project else {}
    decompose_prompt = f"""You are an expert task decomposition system for the {COMPANY_NAME} framework.
Your job is to decompose natural language commands into structured execution plans.

COMMAND: {command}
PROJECT: {project or "unknown"}
PROJECT_INFO: {json.dumps(project_info, indent=2)}
OPERATOR: {operator}

Current date: {datetime.now().isoformat()}

TIER DEFINITIONS:
- Tier 0 (Conductor): System orchestration, prioritization, cross-project dispatch
- Tier 1 (PM): Single-project coordination, workflow management
- Tier 2 (Specialist): Domain-specific execution (code, design, analysis)
- Tier 3 (Executor): Deterministic scripts and API calls

MODEL CLASSES:
- "reasoning": For complex decomposition, planning, strategy (expensive)
- "primary": For multi-turn reasoning, standard work
- "fast": For quick optimization passes, cheap analysis
- "coding": For code generation, technical analysis
- "local": For deterministic local execution (no LLM needed)

Decompose this command into concrete tasks with:
1. Clear descriptions (what, not how)
2. Correct tier assignment (0 for meta, 1 for coordination, 2 for execution)
3. Model selection based on task complexity
4. Dependencies between tasks
5. Parallelization opportunities
6. Measurable success criteria

Return valid JSON matching this schema:
{{
    "tasks": [
        {{
            "id": "task-NNN",
            "description": "...",
            "tier": 0|1|2|3,
            "agent_type": "pm|specialist|executor|conductor",
            "model_class": "reasoning|primary|fast|coding|local",
            "dependencies": [],
            "estimated_complexity": "low|medium|high",
            "success_criteria": "...",
            "parallelizable_with": []
        }}
    ],
    "reasoning": "explanation of decomposition logic",
    "risk_factors": ["..."],
    "assumptions": ["..."]
}}
"""

    # Call LLM with reasoning tier
    decomposition_raw = call_llm(
        decompose_prompt, model_tier="reasoning", max_tokens=8000
    )

    # Parse response
    try:
        # Extract JSON from response (handle markdown code blocks)
        if "```json" in decomposition_raw:
            json_str = decomposition_raw.split("```json")[1].split("```")[0].strip()
        elif "```" in decomposition_raw:
            json_str = decomposition_raw.split("```")[1].split("```")[0].strip()
        else:
            json_str = decomposition_raw

        decomp_data = json.loads(json_str)
    except json.JSONDecodeError as e:
        print(f"ERROR: Failed to parse LLM response as JSON: {e}", file=sys.stderr)
        print(f"Response:\n{decomposition_raw}", file=sys.stderr)
        raise

    # Build execution order (parallel groups)
    execution_order = _build_execution_order(decomp_data["tasks"])

    # Generate decomposition ID
    now = datetime.now()
    dec_id = f"dec-{now.strftime('%Y-%m-%d')}-{_get_sequence_number():03d}"

    # Assemble final decomposition
    decomposition = {
        "id": dec_id,
        "timestamp": now.isoformat(),
        "command": command,
        "project": project,
        "operator": operator,
        "tasks": decomp_data.get("tasks", []),
        "execution_order": execution_order,
        "estimated_total_steps": len(decomp_data.get("tasks", [])),
        "metadata": {
            "reasoning": decomp_data.get("reasoning", ""),
            "risk_factors": decomp_data.get("risk_factors", []),
            "assumptions": decomp_data.get("assumptions", []),
        },
    }

    # Log decomposition
    _log_decomposition(decomposition)

    return decomposition


def _build_execution_order(tasks: list) -> list:
    """
    Build parallel execution groups from task dependencies.

    Simple topological sort: group tasks that can run in parallel.

    Args:
        tasks: List of task dictionaries

    Returns:
        List of lists, each sublist is a parallel group
    """
    task_by_id = {t["id"]: t for t in tasks}
    completed = set()
    groups = []

    while len(completed) < len(tasks):
        current_group = []

        for task in tasks:
            task_id = task["id"]
            if task_id in completed:
                continue

            deps = task.get("dependencies", [])
            if all(d in completed for d in deps):
                current_group.append(task_id)

        if not current_group:
            # Fallback: if we're stuck, take the first non-completed
            for task in tasks:
                if task["id"] not in completed:
                    current_group = [task["id"]]
                    break

        groups.append(current_group)
        completed.update(current_group)

    return groups


def _get_sequence_number() -> int:
    """Get next sequence number for today's decompositions."""
    if not DECOMPOSITIONS_LOG.exists():
        return 1

    today = datetime.now().strftime("%Y-%m-%d")
    count = 0

    with open(DECOMPOSITIONS_LOG) as f:
        for line in f:
            try:
                dec = json.loads(line)
                if dec.get("timestamp", "").startswith(today):
                    count += 1
            except:
                pass

    return count + 1


def _log_decomposition(decomposition: dict) -> None:
    """Append decomposition to JSONL log."""
    with open(DECOMPOSITIONS_LOG, "a") as f:
        f.write(json.dumps(decomposition) + "\n")


# ─────────────────────────────────────────────────────────────────────────
# PLAN OPTIMIZATION
# ─────────────────────────────────────────────────────────────────────────


def optimize_plan(decomposition_id: str) -> dict:
    """
    Re-evaluate a decomposition for optimization opportunities.

    Uses the fast LLM tier to check if:
    - Any tasks could be merged
    - Lower tiers could handle some tasks
    - More tasks could run in parallel
    - Any tasks are unnecessary

    Args:
        decomposition_id: ID of decomposition to optimize

    Returns:
        Optimized decomposition dictionary
    """
    # Load original decomposition
    decomposition = _load_decomposition(decomposition_id)
    if not decomposition:
        print(f"ERROR: Decomposition {decomposition_id} not found", file=sys.stderr)
        return {}

    # Build optimization prompt
    optimize_prompt = f"""You are a task optimization expert for {COMPANY_NAME}.
Review this decomposition and identify optimization opportunities:

{json.dumps(decomposition, indent=2)}

Check for:
1. Tasks that could be merged (reduce total tasks)
2. Tasks assigned to higher tiers that could use lower tiers
3. Tasks that could be parallelized (move to same execution group)
4. Unnecessary tasks (that don't advance the goal)
5. Missing critical tasks

Return JSON with:
{{
    "optimizations": [
        {{
            "type": "merge|tier_reduction|parallelize|remove|add",
            "tasks": ["task-ids"],
            "rationale": "why this helps",
            "impact": "low|medium|high"
        }}
    ],
    "summary": "overall assessment"
}}
"""

    # Call fast tier for optimization
    optimization_raw = call_llm(
        optimize_prompt, model_tier="fast", max_tokens=4000
    )

    # Parse optimizations
    try:
        if "```json" in optimization_raw:
            json_str = optimization_raw.split("```json")[1].split("```")[0].strip()
        elif "```" in optimization_raw:
            json_str = optimization_raw.split("```")[1].split("```")[0].strip()
        else:
            json_str = optimization_raw

        opt_data = json.loads(json_str)
    except json.JSONDecodeError as e:
        print(f"ERROR parsing optimization response: {e}", file=sys.stderr)
        return decomposition

    # Store optimization record (but don't modify original)
    opt_record = {
        "original_decomposition_id": decomposition_id,
        "timestamp": datetime.now().isoformat(),
        "optimizations": opt_data.get("optimizations", []),
        "summary": opt_data.get("summary", ""),
    }

    # Log to memory
    opt_log = MEMORY_DIR / "optimizations.jsonl"
    with open(opt_log, "a") as f:
        f.write(json.dumps(opt_record) + "\n")

    return opt_record


def _load_decomposition(dec_id: str) -> Optional[dict]:
    """Load a decomposition from log by ID."""
    if not DECOMPOSITIONS_LOG.exists():
        return None

    with open(DECOMPOSITIONS_LOG) as f:
        for line in f:
            try:
                dec = json.loads(line)
                if dec.get("id") == dec_id:
                    return dec
            except:
                pass

    return None


# ─────────────────────────────────────────────────────────────────────────
# EXECUTION TRACKING
# ─────────────────────────────────────────────────────────────────────────


def log_execution(
    decomposition_id: str,
    task_id: str,
    success: bool,
    actual_time_ms: int,
    output_quality_score: float,
) -> None:
    """
    Log the execution result of a task from a decomposition.

    Used to track how well our decompositions predict actual work.

    Args:
        decomposition_id: Which decomposition this task came from
        task_id: Which task was executed
        success: Whether execution succeeded
        actual_time_ms: How long it actually took (milliseconds)
        output_quality_score: Quality of output (0.0-1.0)
    """
    execution_record = {
        "timestamp": datetime.now().isoformat(),
        "decomposition_id": decomposition_id,
        "task_id": task_id,
        "success": success,
        "actual_time_ms": actual_time_ms,
        "output_quality_score": output_quality_score,
    }

    exec_log = MEMORY_DIR / "execution_log.jsonl"
    with open(exec_log, "a") as f:
        f.write(json.dumps(execution_record) + "\n")


# ─────────────────────────────────────────────────────────────────────────
# PATTERN ANALYSIS
# ─────────────────────────────────────────────────────────────────────────


def analyze_decomposition_patterns(n: int = 50) -> dict:
    """
    Analyze patterns in recent decompositions.

    Looks at the last N decompositions to find:
    - Commands that always decompose the same way (cache candidates)
    - Tier assignments that are consistently correct/wrong
    - Common dependencies and parallelization patterns
    - Average task counts and complexity

    Args:
        n: Number of recent decompositions to analyze

    Returns:
        Pattern analysis dictionary
    """
    if not DECOMPOSITIONS_LOG.exists():
        return {"decompositions_analyzed": 0, "patterns": []}

    decompositions = []
    with open(DECOMPOSITIONS_LOG) as f:
        for line in f:
            try:
                decompositions.append(json.loads(line))
            except:
                pass

    decompositions = decompositions[-n:]  # Last N

    if not decompositions:
        return {"decompositions_analyzed": 0, "patterns": []}

    # Analyze patterns
    command_patterns = {}
    tier_assignments = []
    complexity_distribution = {"low": 0, "medium": 0, "high": 0}

    for dec in decompositions:
        command = dec.get("command", "")
        if command not in command_patterns:
            command_patterns[command] = {"count": 0, "task_count": 0}

        command_patterns[command]["count"] += 1
        command_patterns[command]["task_count"] = len(dec.get("tasks", []))

        for task in dec.get("tasks", []):
            tier_assignments.append(
                {
                    "command_type": command.split()[0:2],
                    "tier": task.get("tier"),
                    "model_class": task.get("model_class"),
                }
            )
            complexity = task.get("estimated_complexity", "medium")
            complexity_distribution[complexity] += 1

    # Identify cache-worthy patterns (same command appearing multiple times)
    cacheable = [
        {"command": cmd, "frequency": data["count"], "avg_task_count": data["task_count"]}
        for cmd, data in sorted(command_patterns.items(), key=lambda x: -x[1]["count"])
        if data["count"] >= 3
    ]

    analysis = {
        "timestamp": datetime.now().isoformat(),
        "decompositions_analyzed": len(decompositions),
        "cacheable_patterns": cacheable,
        "complexity_distribution": complexity_distribution,
        "tier_assignment_frequency": _count_frequencies(tier_assignments),
        "avg_task_count": sum(len(d.get("tasks", [])) for d in decompositions)
        / len(decompositions)
        if decompositions
        else 0,
    }

    # Save to patterns log
    with open(PATTERNS_LOG, "w") as f:
        json.dump(analysis, f, indent=2)

    return analysis


def _count_frequencies(items: list) -> dict:
    """Count frequencies of items."""
    freqs = {}
    for item in items:
        tier = item.get("tier")
        model = item.get("model_class")
        key = f"tier{tier}-{model}"
        freqs[key] = freqs.get(key, 0) + 1
    return freqs


# ─────────────────────────────────────────────────────────────────────────
# CLI
# ─────────────────────────────────────────────────────────────────────────


def main():
    """Command-line interface."""
    parser = argparse.ArgumentParser(
        description="NSOS Task Decomposer — Intelligent task decomposition engine"
    )
    subparsers = parser.add_subparsers(dest="command")

    # Decompose command
    decomp_parser = subparsers.add_parser(
        "decompose", help="Decompose a natural language command"
    )
    decomp_parser.add_argument("command", help="Command to decompose (e.g., 'take care of <project>')")
    decomp_parser.add_argument(
        "--project", help="Project ID (auto-detected if not provided)"
    )
    decomp_parser.add_argument("--operator", default=OPERATOR_NAME, help="Operator name")

    # Optimize command
    opt_parser = subparsers.add_parser(
        "optimize", help="Optimize an existing decomposition"
    )
    opt_parser.add_argument("decomposition_id", help="Decomposition ID to optimize")

    # History command
    subparsers.add_parser("history", help="Show decomposition history")

    # Patterns command
    subparsers.add_parser("patterns", help="Analyze decomposition patterns")

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        return

    # Check for anthropic library only when executing operations
    if args.command in ("decompose", "optimize"):
        if anthropic is None:
            print(
                "ERROR: anthropic library not installed.",
                file=sys.stderr,
            )
            print(
                "Install with: pip install anthropic",
                file=sys.stderr,
            )
            sys.exit(1)

    if args.command == "decompose":
        result = decompose(args.command, project=args.project, operator=args.operator)
        print(json.dumps(result, indent=2))
        print(f"\nDecomposition saved: {result['id']}")

    elif args.command == "optimize":
        result = optimize_plan(args.decomposition_id)
        print(json.dumps(result, indent=2))

    elif args.command == "history":
        if not DECOMPOSITIONS_LOG.exists():
            print("No decomposition history found.")
            return

        with open(DECOMPOSITIONS_LOG) as f:
            decompositions = [json.loads(line) for line in f]

        for dec in decompositions[-10:]:  # Last 10
            print(
                f"{dec['id']:20} | {dec['command']:50} | {len(dec.get('tasks', [])):2} tasks"
            )

    elif args.command == "patterns":
        analysis = analyze_decomposition_patterns(50)
        print(json.dumps(analysis, indent=2))


if __name__ == "__main__":
    main()
