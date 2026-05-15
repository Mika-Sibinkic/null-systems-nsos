#!/usr/bin/env python3
"""
Agent Memory Store — NSOS Multi-Tier Framework
Version: 1.0

Provides persistent knowledge store for all agent tiers (T0/Conductor, T1/PM, T2/Specialist, T3/Executor).
Solves cold-start problem by allowing agents to read/write shared memories indexed by project, category, tier.

Uses LLM-assisted relevance scoring for intelligent memory retrieval.
All paths relative to NSOS_DIR (project root).
"""

import json
import sys
from pathlib import Path
from datetime import datetime, timedelta
from typing import Optional, List, Dict, Any
import uuid
from dataclasses import dataclass, asdict, field

# Setup path for imports
NSOS_DIR = Path(__file__).parent
sys.path.insert(0, str(NSOS_DIR))

# Try to import LLM adapter; graceful fallback
try:
    from llm_adapter import call_llm, NIM_API_KEY
    LLM_AVAILABLE = True
except ImportError:
    LLM_AVAILABLE = False
    call_llm = None
    NIM_API_KEY = None


@dataclass
class Memory:
    """Single memory entry in the agent knowledge store."""
    id: str
    agent_tier: str  # "T0", "T1", "T2", "T3"
    agent_role: str  # e.g., "Conductor", "ProjectManager", "DataValidator"
    project: str  # e.g., "NSOS", "a client", "a lending client"
    category: str  # "fact" | "insight" | "decision" | "warning" | "preference"
    content: str  # The actual memory content
    confidence: float  # 0.0-1.0, credibility score
    source_task: str  # ID/name of task that created this memory
    timestamp: str  # ISO 8601 timestamp (UTC)
    ttl_hours: Optional[int] = None  # Optional expiry
    references: List[str] = field(default_factory=list)  # IDs of related memories

    def is_expired(self) -> bool:
        """Check if memory has exceeded TTL."""
        if self.ttl_hours is None:
            return False
        # Remove 'Z' suffix for fromisoformat compatibility
        ts = self.timestamp.rstrip('Z')
        created = datetime.fromisoformat(ts)
        now = datetime.utcnow()
        return (now - created).total_seconds() > (self.ttl_hours * 3600)

    def age_hours(self) -> float:
        """Return age of memory in hours."""
        # Remove 'Z' suffix for fromisoformat compatibility
        ts = self.timestamp.rstrip('Z')
        created = datetime.fromisoformat(ts)
        now = datetime.utcnow()
        return (now - created).total_seconds() / 3600.0

    def recency_score(self) -> float:
        """Return recency score (0.0-1.0), decaying over 30 days."""
        age = self.age_hours()
        max_age = 30 * 24  # 30 days in hours
        if age >= max_age:
            return 0.0
        return 1.0 - (age / max_age)

    def relevance_score(self, weight_confidence=0.6, weight_recency=0.4) -> float:
        """Return combined relevance score."""
        return (self.confidence * weight_confidence) + (self.recency_score() * weight_recency)


class AgentMemoryStore:
    """
    Persistent memory store for multi-tier agents.
    
    Memories are stored as JSONL in NSOS_DIR/memory/agent-memories.jsonl
    Each line is a complete JSON object (Memory).
    """

    def __init__(self, memory_dir: Optional[Path] = None):
        """Initialize store. Default: NSOS_DIR/memory/"""
        if memory_dir is None:
            self.memory_dir = NSOS_DIR / "memory"
        else:
            self.memory_dir = Path(memory_dir)
        
        self.memory_file = self.memory_dir / "agent-memories.jsonl"
        self.memory_dir.mkdir(parents=True, exist_ok=True)
        self._cache = None  # Lazy-loaded cache

    def store(
        self,
        agent_tier: str,
        agent_role: str,
        project: str,
        category: str,
        content: str,
        confidence: float,
        source_task: str,
        ttl_hours: Optional[int] = None,
        references: Optional[List[str]] = None,
    ) -> str:
        """
        Store a new memory entry.
        
        Args:
            agent_tier: "T0", "T1", "T2", or "T3"
            agent_role: Human-readable role (e.g., "Conductor", "DataValidator")
            project: Project name (e.g., "NSOS", "a client")
            category: "fact", "insight", "decision", "warning", or "preference"
            content: The memory content (string)
            confidence: 0.0-1.0 credibility score
            source_task: Task ID or name that created this memory
            ttl_hours: Optional expiry time in hours
            references: Optional list of related memory IDs
        
        Returns:
            Memory ID (UUID4)
        """
        memory_id = str(uuid.uuid4())
        memory = Memory(
            id=memory_id,
            agent_tier=agent_tier,
            agent_role=agent_role,
            project=project,
            category=category,
            content=content,
            confidence=min(1.0, max(0.0, confidence)),
            source_task=source_task,
            timestamp=datetime.utcnow().isoformat() + "Z",
            ttl_hours=ttl_hours,
            references=references or [],
        )
        
        # Append to JSONL file
        with open(self.memory_file, "a") as f:
            f.write(json.dumps(asdict(memory)) + "\n")
        
        # Invalidate cache
        self._cache = None
        return memory_id

    def _load_all_memories(self) -> List[Memory]:
        """Load all memories from JSONL file."""
        if self._cache is not None:
            return self._cache
        
        memories = []
        if not self.memory_file.exists():
            self._cache = []
            return []
        
        with open(self.memory_file, "r") as f:
            for line in f:
                if line.strip():
                    try:
                        data = json.loads(line)
                        # Convert to Memory dataclass
                        m = Memory(
                            id=data["id"],
                            agent_tier=data["agent_tier"],
                            agent_role=data["agent_role"],
                            project=data["project"],
                            category=data["category"],
                            content=data["content"],
                            confidence=data["confidence"],
                            source_task=data["source_task"],
                            timestamp=data["timestamp"],
                            ttl_hours=data.get("ttl_hours"),
                            references=data.get("references", []),
                        )
                        memories.append(m)
                    except (json.JSONDecodeError, KeyError):
                        # Skip malformed lines
                        continue
        
        self._cache = memories
        return memories

    def recall(
        self,
        project: Optional[str] = None,
        category: Optional[str] = None,
        agent_tier: Optional[str] = None,
        min_confidence: float = 0.0,
        limit: int = 20,
        max_age_hours: Optional[float] = None,
    ) -> List[Memory]:
        """
        Retrieve memories matching filters, sorted by relevance (confidence * recency).
        
        Args:
            project: Filter by project name
            category: Filter by category
            agent_tier: Filter by tier (T0, T1, T2, T3)
            min_confidence: Minimum confidence threshold
            limit: Max results to return
            max_age_hours: Filter out memories older than this
        
        Returns:
            List of Memory objects, sorted by relevance (descending)
        """
        self.forget_expired()
        all_memories = self._load_all_memories()
        
        # Filter
        filtered = []
        for m in all_memories:
            if project and m.project != project:
                continue
            if category and m.category != category:
                continue
            if agent_tier and m.agent_tier != agent_tier:
                continue
            if m.confidence < min_confidence:
                continue
            if max_age_hours and m.age_hours() > max_age_hours:
                continue
            filtered.append(m)
        
        # Sort by relevance (descending)
        filtered.sort(key=lambda m: m.relevance_score(), reverse=True)
        return filtered[:limit]

    def recall_for_context(
        self,
        project: str,
        task_description: str,
        max_tokens: int = 2000,
    ) -> str:
        """
        Intelligent memory retrieval using LLM to score relevance.
        
        Uses LLM to evaluate which stored memories are most relevant to the current task,
        then returns them formatted as a context block.
        
        Args:
            project: Project name to search within
            task_description: Description of current task
            max_tokens: Approximate token budget for returned context
        
        Returns:
            Formatted context string (empty if no memories or LLM unavailable)
        """
        self.forget_expired()
        project_memories = self.recall(project=project, limit=50)
        
        if not project_memories or not LLM_AVAILABLE:
            return ""
        
        # Build prompt for LLM relevance scoring
        memories_text = "\n".join(
            f"[{m.id[:8]}] [{m.category}] {m.content}" 
            for m in project_memories
        )
        
        prompt = f"""You are a memory relevance evaluator for an AI agent system.

Current Task:
{task_description}

Available Memories:
{memories_text}

Score each memory (0-10) for relevance to this task. Return only the memory IDs and scores in format:
id1: 9
id2: 5
id3: 7
...

Keep scores concise. Omit irrelevant memories."""
        
        try:
            response = call_llm(
                prompt=prompt,
                tier="fast",
                max_tokens=500,
                temperature=0.0,
            )
            
            # Parse scores
            scores = {}
            for line in response.split("\n"):
                if ":" in line:
                    parts = line.split(":")
                    if len(parts) == 2:
                        mem_id = parts[0].strip()
                        try:
                            score = int(parts[1].strip())
                            scores[mem_id] = score
                        except ValueError:
                            continue
            
            # Build context with top-scoring memories
            top_memories = []
            for m in project_memories:
                if m.id in scores and scores[m.id] >= 5:
                    top_memories.append((m, scores[m.id]))
            
            top_memories.sort(key=lambda x: x[1], reverse=True)
            
            # Format output, respecting token budget
            context_lines = ["## Agent Memory Context\n"]
            for m, score in top_memories:
                line = f"[{m.agent_role}] [{m.category}] {m.content}"
                if len("\n".join(context_lines)) < max_tokens * 4:  # Rough token estimate
                    context_lines.append(line)
                else:
                    break
            
            return "\n".join(context_lines) if len(context_lines) > 1 else ""
        
        except Exception:
            # Fallback to basic recall if LLM fails
            return "\n".join(
                f"[{m.agent_role}] [{m.category}] {m.content}"
                for m in project_memories[:10]
            )

    def forget_expired(self) -> int:
        """
        Remove memories past their TTL.
        Rewrites JSONL file with valid memories only.
        
        Returns:
            Number of memories deleted
        """
        all_memories = self._load_all_memories()
        valid_memories = [m for m in all_memories if not m.is_expired()]
        deleted_count = len(all_memories) - len(valid_memories)
        
        if deleted_count > 0:
            # Rewrite file with valid memories
            self.memory_file.write_text("")
            with open(self.memory_file, "a") as f:
                for m in valid_memories:
                    f.write(json.dumps(asdict(m)) + "\n")
            
            # Invalidate cache
            self._cache = None
        
        return deleted_count

    def cross_pollinate(
        self,
        source_project: str,
        target_project: str,
        min_confidence: float = 0.7,
    ) -> List[str]:
        """
        Find memories from source_project that might be relevant to target_project.
        Uses LLM to evaluate transferability.
        
        Args:
            source_project: Source project name
            target_project: Target project name
            min_confidence: Minimum confidence to consider
        
        Returns:
            List of memory IDs suitable for transfer
        """
        if not LLM_AVAILABLE:
            return []
        
        source_memories = self.recall(project=source_project, min_confidence=min_confidence)
        if not source_memories:
            return []
        
        # Get some target context (if any exists)
        target_memories = self.recall(project=target_project, limit=5)
        target_context = "\n".join(
            f"- [{m.category}] {m.content}"
            for m in target_memories
        ) or "(no existing memories)"
        
        # Batch evaluate transferability
        candidates = []
        for m in source_memories:
            prompt = f"""Is this memory from {source_project} relevant/transferable to {target_project}?

Source Memory:
[{m.category}] {m.content}

Target Project Context:
{target_context}

Reply with YES or NO only."""
            
            try:
                response = call_llm(
                    prompt=prompt,
                    tier="fast",
                    max_tokens=10,
                    temperature=0.0,
                )
                if "YES" in response.upper():
                    candidates.append(m.id)
            except Exception:
                continue
        
        return candidates

    def get_stats(self) -> Dict[str, Any]:
        """
        Get summary statistics about stored memories.
        
        Returns:
            Dict with counts by project, category, tier
        """
        self.forget_expired()
        all_memories = self._load_all_memories()
        
        stats = {
            "total_memories": len(all_memories),
            "by_project": {},
            "by_category": {},
            "by_tier": {},
            "avg_confidence": 0.0,
        }
        
        if all_memories:
            stats["avg_confidence"] = sum(m.confidence for m in all_memories) / len(all_memories)
        
        for m in all_memories:
            # By project
            if m.project not in stats["by_project"]:
                stats["by_project"][m.project] = 0
            stats["by_project"][m.project] += 1
            
            # By category
            if m.category not in stats["by_category"]:
                stats["by_category"][m.category] = 0
            stats["by_category"][m.category] += 1
            
            # By tier
            if m.agent_tier not in stats["by_tier"]:
                stats["by_tier"][m.agent_tier] = 0
            stats["by_tier"][m.agent_tier] += 1
        
        return stats


# ── CLI Interface ──

def main():
    """Command-line interface for memory store operations."""
    import argparse
    
    parser = argparse.ArgumentParser(description="NSOS Agent Memory Store CLI")
    parser.add_argument("--memory-dir", type=str, default=None, help="Memory directory (default: NSOS_DIR/memory)")
    
    subparsers = parser.add_subparsers(dest="command", help="Command to execute")
    
    # Store command
    store_parser = subparsers.add_parser("store", help="Store a new memory")
    store_parser.add_argument("--tier", required=True, help="Agent tier (T0-T3)")
    store_parser.add_argument("--role", required=True, help="Agent role")
    store_parser.add_argument("--project", required=True, help="Project name")
    store_parser.add_argument("--category", required=True, help="Memory category")
    store_parser.add_argument("--content", required=True, help="Memory content")
    store_parser.add_argument("--confidence", type=float, default=0.8, help="Confidence (0-1)")
    store_parser.add_argument("--source-task", required=True, help="Source task ID")
    store_parser.add_argument("--ttl-hours", type=int, default=None, help="TTL in hours")
    
    # Recall command
    recall_parser = subparsers.add_parser("recall", help="Recall memories")
    recall_parser.add_argument("--project", default=None, help="Filter by project")
    recall_parser.add_argument("--category", default=None, help="Filter by category")
    recall_parser.add_argument("--tier", default=None, help="Filter by tier")
    recall_parser.add_argument("--min-confidence", type=float, default=0.0)
    recall_parser.add_argument("--limit", type=int, default=20)
    
    # Stats command
    subparsers.add_parser("stats", help="Show memory statistics")
    
    # Cleanup command
    subparsers.add_parser("cleanup", help="Remove expired memories")
    
    args = parser.parse_args()
    
    memory_dir = Path(args.memory_dir) if args.memory_dir else None
    store = AgentMemoryStore(memory_dir=memory_dir)
    
    if args.command == "store":
        mem_id = store.store(
            agent_tier=args.tier,
            agent_role=args.role,
            project=args.project,
            category=args.category,
            content=args.content,
            confidence=args.confidence,
            source_task=args.source_task,
            ttl_hours=args.ttl_hours,
        )
        print(f"Stored memory: {mem_id}")
    
    elif args.command == "recall":
        memories = store.recall(
            project=args.project,
            category=args.category,
            agent_tier=args.tier,
            min_confidence=args.min_confidence,
            limit=args.limit,
        )
        for m in memories:
            print(f"[{m.id[:8]}] [{m.agent_role}] [{m.category}] {m.content}")
    
    elif args.command == "stats":
        stats = store.get_stats()
        print(json.dumps(stats, indent=2))
    
    elif args.command == "cleanup":
        deleted = store.forget_expired()
        print(f"Deleted {deleted} expired memories")
    
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
