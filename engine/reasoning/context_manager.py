#!/usr/bin/env python3
"""
NSOS Context Window Manager v1.0

Intelligent context allocation for LLM prompts. Determines what context
to include based on task relevance, ensuring the most valuable information
fills the window without waste.

Key features:
- Source registration with metadata (priority, freshness, token estimates)
- Task-aware context relevance scoring
- Greedy token-efficient context filling
- Universal context (applies to all tasks) + project-specific context
- Context compression for large sources
- Precomputation and caching for fast access
"""

import json
import sys
import argparse
import re
from pathlib import Path
from dataclasses import dataclass, asdict
from datetime import datetime, timedelta
from typing import Optional, Dict, List, Tuple, Callable, Any
from enum import Enum


NSOS_DIR = Path(__file__).parent
CONTEXT_DIR = NSOS_DIR / "context"
SOURCES_REGISTRY = CONTEXT_DIR / "sources.json"
CACHE_DIR = CONTEXT_DIR / "cache"
PROJECT_BASE = NSOS_DIR.parent

# Ensure directories exist
CONTEXT_DIR.mkdir(parents=True, exist_ok=True)
CACHE_DIR.mkdir(parents=True, exist_ok=True)


class ContextCategory(Enum):
    """Source categories for context organization."""
    PROJECT_STATE = "project_state"
    PATTERNS = "patterns"
    CORRECTIONS = "corrections"
    GAPS = "gaps"
    PREDICTIONS = "predictions"
    AGENT_MEMORY = "agent_memory"
    PROJECT_FILES = "project_files"
    COMPANY_GOALS = "company_goals"


@dataclass
class ContextSource:
    """Metadata for a registered context source."""
    name: str
    path_or_function: str  # file path or "function:module.callable"
    category: str
    priority: float  # 0-1, higher = more important
    avg_tokens: int  # estimated size
    freshness_hours: int  # how long until stale

    def to_dict(self) -> Dict:
        return asdict(self)

    @staticmethod
    def from_dict(d: Dict) -> "ContextSource":
        return ContextSource(**d)


def estimate_tokens(text: str) -> int:
    """Estimate token count using word count heuristic."""
    if not text:
        return 0
    words = len(text.split())
    return int(words * 1.3)


def load_registry() -> Dict[str, ContextSource]:
    """Load context sources from registry."""
    if not SOURCES_REGISTRY.exists():
        return {}

    with open(SOURCES_REGISTRY) as f:
        data = json.load(f)

    return {
        name: ContextSource.from_dict(src)
        for name, src in data.items()
    }


def save_registry(sources: Dict[str, ContextSource]) -> None:
    """Save context sources to registry."""
    SOURCES_REGISTRY.parent.mkdir(parents=True, exist_ok=True)
    with open(SOURCES_REGISTRY, 'w') as f:
        json.dump({name: src.to_dict() for name, src in sources.items()}, f, indent=2)


def register_source(
    name: str,
    path_or_function: str,
    category: str,
    priority: float,
    avg_tokens: int = 0,
    freshness_hours: int = 24
) -> None:
    """Register a new context source."""
    sources = load_registry()

    # Auto-estimate tokens if not provided
    if avg_tokens == 0 and not path_or_function.startswith("function:"):
        fpath = PROJECT_BASE / path_or_function if not Path(path_or_function).is_absolute() else Path(path_or_function)
        if fpath.exists() and fpath.is_file():
            try:
                with open(fpath) as f:
                    avg_tokens = estimate_tokens(f.read())
            except Exception:
                avg_tokens = 1000

    sources[name] = ContextSource(
        name=name,
        path_or_function=path_or_function,
        category=category,
        priority=priority,
        avg_tokens=avg_tokens,
        freshness_hours=freshness_hours
    )
    save_registry(sources)


def load_source_content(source: ContextSource) -> Optional[str]:
    """Load content from a source (file or function)."""
    if source.path_or_function.startswith("function:"):
        # Dynamic function call
        try:
            module_path, func_name = source.path_or_function[9:].rsplit(".", 1)
            sys.path.insert(0, str(NSOS_DIR))
            mod = __import__(module_path, fromlist=[func_name])
            func = getattr(mod, func_name)
            return func()
        except Exception as e:
            return f"[Error loading {source.name}: {str(e)}]"
    else:
        # File path
        fpath = PROJECT_BASE / source.path_or_function if not Path(source.path_or_function).is_absolute() else Path(source.path_or_function)
        if fpath.exists():
            try:
                with open(fpath) as f:
                    return f.read()
            except Exception as e:
                return f"[Error reading {source.name}: {str(e)}]"

    return None


def is_source_fresh(source: ContextSource) -> bool:
    """Check if source data is still fresh."""
    fpath = PROJECT_BASE / source.path_or_function if not Path(source.path_or_function).is_absolute() else Path(source.path_or_function)
    if not fpath.exists():
        return False

    mtime = fpath.stat().st_mtime
    age_hours = (datetime.now().timestamp() - mtime) / 3600
    return age_hours < source.freshness_hours


def score_relevance(task_description: str, source: ContextSource) -> float:
    """Score source relevance to task using heuristic keyword matching."""
    if not task_description:
        return source.priority * 0.5  # Baseline if no task given

    task_lower = task_description.lower()

    # Category relevance boosts
    category_boost = {
        ContextCategory.PROJECT_STATE.value: 1.2 if "state" in task_lower or "status" in task_lower else 1.0,
        ContextCategory.PATTERNS.value: 1.3 if "pattern" in task_lower or "bug" in task_lower else 0.9,
        ContextCategory.CORRECTIONS.value: 1.4 if "fix" in task_lower or "correct" in task_lower else 0.8,
        ContextCategory.GAPS.value: 1.3 if "gap" in task_lower or "missing" in task_lower else 0.8,
        ContextCategory.PREDICTIONS.value: 1.2 if "predict" in task_lower or "estimate" in task_lower else 0.7,
        ContextCategory.AGENT_MEMORY.value: 1.1 if "remember" in task_lower or "history" in task_lower else 0.8,
        ContextCategory.PROJECT_FILES.value: 1.0,
        ContextCategory.COMPANY_GOALS.value: 1.1 if "goal" in task_lower or "objective" in task_lower else 0.8,
    }

    boost = category_boost.get(source.category, 1.0)

    # Keyword matching from source name
    name_lower = source.name.lower()
    keywords = re.findall(r'\w+', name_lower)
    keyword_matches = sum(1 for kw in keywords if kw in task_lower)
    keyword_boost = 1.0 + (keyword_matches * 0.15)

    # Freshness bonus
    freshness_bonus = 1.1 if is_source_fresh(source) else 0.9

    return source.priority * boost * keyword_boost * freshness_bonus


def compress_context(text: str, target_tokens: int) -> str:
    """
    Compress context to target token count while preserving key facts.
    Uses heuristic summarization when LLM unavailable.
    """
    if estimate_tokens(text) <= target_tokens:
        return text

    # Try to load llm_adapter for compression
    try:
        sys.path.insert(0, str(NSOS_DIR))
        from llm_adapter import query_model

        prompt = f"""Summarize this context to ~{int(target_tokens / 1.3)} words while preserving all key facts:

{text[:2000]}...

Return ONLY the compressed summary, no preamble."""

        compressed = query_model(prompt, model_class="fast", max_tokens=target_tokens)
        return compressed or text
    except Exception:
        # Fallback: truncate + extract key sections
        lines = text.split('\n')
        estimate = 0
        kept_lines = []

        for line in lines:
            line_tokens = estimate_tokens(line)
            if estimate + line_tokens <= target_tokens:
                kept_lines.append(line)
                estimate += line_tokens
            elif estimate < target_tokens * 0.9:
                break

        result = '\n'.join(kept_lines)
        if len(kept_lines) < len(lines):
            result += f"\n... [{len(lines) - len(kept_lines)} more lines truncated]"

        return result


def build_context(
    task_description: str,
    project: Optional[str] = None,
    max_tokens: int = 4000,
    model_class: str = "primary"
) -> str:
    """
    Build context for a task by scoring and greedily filling token budget.

    Args:
        task_description: Task or question requiring context
        project: Project name for project-specific filtering
        max_tokens: Maximum tokens to use
        model_class: LLM tier for compression (primary, fast, vision)

    Returns:
        Formatted context block with source attribution
    """
    sources = load_registry()
    if not sources:
        auto_register_default_sources()
        sources = load_registry()

    # Score all sources for relevance
    scored_sources: List[Tuple[ContextSource, float]] = [
        (src, score_relevance(task_description, src))
        for src in sources.values()
    ]

    # Filter by project if specified
    if project:
        scored_sources = [
            (src, score) for src, score in scored_sources
            if project.lower() in src.path_or_function.lower() or
               src.category in [ContextCategory.COMPANY_GOALS.value, ContextCategory.PATTERNS.value]
        ]

    # Sort by relevance (highest first)
    scored_sources.sort(key=lambda x: x[1], reverse=True)

    # Greedily fill context window
    context_parts: List[Tuple[str, int]] = []  # (content, tokens_used)
    tokens_used = 0

    for source, relevance_score in scored_sources:
        if tokens_used >= max_tokens:
            break

        content = load_source_content(source)
        if not content:
            continue

        content_tokens = estimate_tokens(content)
        remaining_budget = max_tokens - tokens_used

        if content_tokens <= remaining_budget:
            # Content fits completely
            context_parts.append((content, content_tokens))
            tokens_used += content_tokens
        elif remaining_budget > 500:  # Only compress if meaningful space left
            # Compress to fit
            compressed = compress_context(content, remaining_budget - 50)
            compressed_tokens = estimate_tokens(compressed)
            context_parts.append((compressed, compressed_tokens))
            tokens_used += compressed_tokens

    # Build formatted output with attribution
    result = f"# CONTEXT FOR: {task_description[:80]}\n"
    result += f"# Token budget: {tokens_used}/{max_tokens}\n"
    result += f"# Generated: {datetime.now().isoformat()}\n\n"

    sources_by_category = {}
    for source, score in scored_sources:
        cat = source.category
        if cat not in sources_by_category:
            sources_by_category[cat] = []
        sources_by_category[cat].append(source)

    # Add contexts with headers and attribution
    for source, score in scored_sources:
        if tokens_used <= 0:
            break

        for content, tokens in context_parts:
            if content and source.name in str(source.path_or_function):
                result += f"\n## [{source.category.upper()}] {source.name}\n"
                result += f"(Priority: {source.priority:.2f}, Relevance: {score:.2f})\n"
                result += f"<!-- Source: {source.path_or_function} -->\n"
                result += content + "\n"
                tokens_used -= tokens
                context_parts.remove((content, tokens))
                break

    return result


def get_project_context(project: str, max_tokens: int = 2000) -> str:
    """Pre-built context for a specific project."""
    return build_context(
        f"Project: {project}",
        project=project,
        max_tokens=max_tokens
    )


def get_universal_context(max_tokens: int = 1000) -> str:
    """Context applicable to all tasks: principles, goals, top patterns."""
    return build_context(
        "Universal context for all tasks",
        max_tokens=max_tokens
    )


def precompute_contexts() -> None:
    """Pre-build and cache context blocks for all active projects."""
    print("Precomputing context blocks...")

    # Load projects.json from orchestrator
    projects_file = PROJECT_BASE.parent / ".claude" / "orchestrator" / "projects.json"
    if not projects_file.exists():
        print("No projects.json found, skipping precomputation")
        return

    with open(projects_file) as f:
        projects_data = json.load(f)

    for project in projects_data.get("projects", []):
        project_id = project.get("id")
        if not project_id:
            continue

        print(f"  {project_id}...", end=" ", flush=True)

        context = get_project_context(project_id)
        cache_file = CACHE_DIR / f"{project_id}.cache.txt"

        with open(cache_file, 'w') as f:
            f.write(context)

        print(f"({estimate_tokens(context)} tokens)")

    print("Precomputation complete")


def auto_register_default_sources() -> None:
    """Register default context sources."""
    defaults = [
        ("project-state", "Active Projects/NSOS/memory/state.json", ContextCategory.PROJECT_STATE.value, 0.9, 500, 2),
        ("patterns", ".claude/orchestrator/patterns.json", ContextCategory.PATTERNS.value, 0.85, 1000, 12),
        ("corrections", ".claude/corrections/recent.jsonl", ContextCategory.CORRECTIONS.value, 0.8, 800, 6),
        ("gaps", ".claude/orchestrator/gaps.jsonl", ContextCategory.GAPS.value, 0.75, 600, 8),
        ("agent_memory", "Active Projects/NSOS/memory/agents.jsonl", ContextCategory.AGENT_MEMORY.value, 0.7, 700, 4),
        ("company-goals", ".claude/goals/current-sprint.md", ContextCategory.COMPANY_GOALS.value, 0.9, 400, 24),
    ]

    sources = load_registry()
    for name, path, category, priority, tokens, freshness in defaults:
        if name not in sources:
            register_source(name, path, category, priority, tokens, freshness)


def print_sources() -> None:
    """Print registered sources."""
    sources = load_registry()
    if not sources:
        print("No sources registered. Run with --precompute or register sources.")
        return

    print(f"Registered context sources ({len(sources)}):\n")
    print(f"{'Name':<25} {'Category':<20} {'Priority':<10} {'Tokens':<10} {'Fresh':<6}")
    print("-" * 75)

    for name, src in sorted(sources.items()):
        fresh = "Y" if is_source_fresh(src) else "N"
        print(f"{name:<25} {src.category:<20} {src.priority:<10.2f} {src.avg_tokens:<10} {fresh:<6}")


def print_stats() -> None:
    """Print context manager statistics."""
    sources = load_registry()
    total_tokens = sum(src.avg_tokens for src in sources.values())
    fresh_count = sum(1 for src in sources.values() if is_source_fresh(src))

    print(f"Context Manager Statistics")
    print(f"  Total sources: {len(sources)}")
    print(f"  Total estimated tokens: {total_tokens}")
    print(f"  Fresh sources: {fresh_count}/{len(sources)}")
    print(f"  Registry: {SOURCES_REGISTRY}")
    print(f"  Cache dir: {CACHE_DIR}")
    print(f"  Cache files: {len(list(CACHE_DIR.glob('*.cache.txt')))}")


def main():
    parser = argparse.ArgumentParser(description="NSOS Context Manager")
    parser.add_argument("--build", help="Build context for task", type=str)
    parser.add_argument("--project", help="Filter to project", type=str)
    parser.add_argument("--max-tokens", help="Max tokens (default 4000)", type=int, default=4000)
    parser.add_argument("--sources", help="List registered sources", action="store_true")
    parser.add_argument("--precompute", help="Precompute all project contexts", action="store_true")
    parser.add_argument("--stats", help="Show statistics", action="store_true")
    parser.add_argument("--register", help="Register source: NAME PATH CATEGORY PRIORITY", nargs=4)

    args = parser.parse_args()

    if args.register:
        name, path, category, priority = args.register
        register_source(name, path, category, float(priority))
        print(f"Registered {name}")
    elif args.precompute:
        precompute_contexts()
    elif args.sources:
        print_sources()
    elif args.stats:
        print_stats()
    elif args.build:
        context = build_context(
            args.build,
            project=args.project,
            max_tokens=args.max_tokens
        )
        print(context)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
