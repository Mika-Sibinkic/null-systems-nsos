#!/usr/bin/env python3
"""
NSOS — Self-Iteration Engine

Implements the Observe -> Analyze -> Propose -> Apply -> Learn loop.
Every change is Git-snapshotted, every outcome is logged, and any
change can be reverted in one command.

Usage:
    python3 iterate.py --mode=full        # Full iteration (all observers)
    python3 iterate.py --mode=observe     # Observe only, no proposals
    python3 iterate.py --mode=propose     # Generate proposals, don't apply
    python3 iterate.py --mode=apply ID    # Apply a specific proposal
    python3 iterate.py --mode=revert ID   # Revert a specific amendment
    python3 iterate.py --mode=status      # Show current NSOS health

Author: Autonomous framework engine
"""

import json
import os
import sys
import subprocess
import hashlib
from pathlib import Path
from datetime import datetime, timezone, timedelta
from dataclasses import dataclass, asdict, field
from typing import Optional
import argparse
import re

# ── Paths ───────────────────────────────────────────────────────────────────

HOME = Path.home()
# All filesystem roots are env-overridable so the iterator has no hardcoded operator paths.
FRAMEWORK_ROOT = Path(os.environ.get("NSOS_FRAMEWORK_ROOT", str(HOME / ".nsos" / "framework")))
BIZ_FRAMEWORK  = Path(os.environ.get("NSOS_BIZ_ROOT", str(HOME / ".nsos" / "biz")))
ORCHESTRATOR   = Path(os.environ.get("NSOS_ORCHESTRATOR_DIR", str(FRAMEWORK_ROOT / ".claude" / "orchestrator")))
NSOS_DIR       = Path(os.environ.get("NSOS_DIR", str(FRAMEWORK_ROOT / "nsos")))
LOGS_DIR       = NSOS_DIR / "logs"
METRICS_DIR    = NSOS_DIR / "metrics"
PROPOSALS_DIR  = NSOS_DIR / "proposals"
SNAPSHOTS_DIR  = NSOS_DIR / "snapshots"

# Config files
SELF_AMENDMENT  = ORCHESTRATOR / "self-amendment.json"
EFFICIENCY_RULES = ORCHESTRATOR / "efficiency-rules.json"
PROJECTS_JSON   = ORCHESTRATOR / "projects.json"
CORRECTIONS_DIR = BIZ_FRAMEWORK / ".claude" / "corrections"
CORRECTIONS_FILE = CORRECTIONS_DIR / "corrections.json"
AMENDMENT_LOG   = ORCHESTRATOR / "logs" / "amendment-log.jsonl"
ITERATION_LOG   = METRICS_DIR / "iteration-log.jsonl"
OUTCOMES_LOG    = METRICS_DIR / "change-outcomes.jsonl"
SKILLS_DIR      = FRAMEWORK_ROOT / ".claude" / "skills"

# ── Data Classes ────────────────────────────────────────────────────────────

@dataclass
class Observation:
    """A single thing NSOS noticed about the framework."""
    id: str
    category: str          # process_health | knowledge | efficiency | revenue
    source: str            # which observer found it
    description: str
    severity: str          # info | warning | action_needed
    evidence: list = field(default_factory=list)
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

@dataclass
class Proposal:
    """A structured change proposal following self-amendment.json format."""
    id: str
    amendment_category: str  # parameter_tuning | process_restructuring | goal_level
    what: str
    why: str
    current_value: str
    proposed_value: str
    risk: str
    reversible: bool = True
    confidence: float = 0.0
    evidence: list = field(default_factory=list)
    file_target: str = ""
    status: str = "pending"  # pending | approved | rejected | applied
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

# ── Utility Functions ───────────────────────────────────────────────────────

def load_json(path: Path) -> dict | list:
    """Safely load a JSON file, returning empty dict/list on failure."""
    if not path.exists():
        return {} if path.suffix == ".json" else []
    try:
        with open(path) as f:
            return json.load(f)
    except (json.JSONDecodeError, IOError) as e:
        log(f"⚠ Failed to load {path.name}: {e}")
        return {}

def load_jsonl(path: Path) -> list[dict]:
    """Load a JSONL file as a list of dicts."""
    if not path.exists():
        return []
    entries = []
    with open(path) as f:
        for line in f:
            line = line.strip()
            if line:
                try:
                    entries.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
    return entries

def append_jsonl(path: Path, entry: dict):
    """Append a single JSON object as a line to a JSONL file."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "a") as f:
        f.write(json.dumps(entry, default=str) + "\n")

def save_json(path: Path, data):
    """Write JSON with pretty formatting."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w") as f:
        json.dump(data, f, indent=2, default=str)

def log(msg: str):
    """Print timestamped log message."""
    ts = datetime.now().strftime("%H:%M:%S")
    print(f"[NSOS {ts}] {msg}")

def gen_id(prefix: str) -> str:
    """Generate a unique ID like nsos-2026-04-04-001."""
    today = datetime.now().strftime("%Y-%m-%d")
    # Count existing entries today to get sequence number
    existing = load_jsonl(ITERATION_LOG) + load_jsonl(AMENDMENT_LOG)
    today_count = sum(1 for e in existing if today in e.get("id", ""))
    return f"{prefix}-{today}-{today_count + 1:03d}"

def run_git(*args, cwd=None) -> tuple[bool, str]:
    """Run a git command and return (success, output)."""
    cwd = cwd or FRAMEWORK_ROOT
    try:
        result = subprocess.run(
            ["git"] + list(args),
            cwd=str(cwd), capture_output=True, text=True, timeout=30
        )
        output = result.stdout.strip() or result.stderr.strip()
        return result.returncode == 0, output
    except (subprocess.TimeoutExpired, FileNotFoundError) as e:
        return False, str(e)

# ── Git Management ──────────────────────────────────────────────────────────

def ensure_git():
    """Initialize git repo if it doesn't exist. Create initial commit."""
    ok, _ = run_git("rev-parse", "--git-dir")
    if ok:
        log("✓ Git repo found")
        return True

    log("Initializing git repository...")
    ok, out = run_git("init")
    if not ok:
        log(f"✗ Git init failed: {out}")
        return False

    # Create .gitignore
    gitignore = FRAMEWORK_ROOT / ".gitignore"
    if not gitignore.exists():
        gitignore.write_text(
            "# NSOS gitignore\n"
            ".DS_Store\n"
            "node_modules/\n"
            "__pycache__/\n"
            "*.pyc\n"
            ".env\n"
            "*.log\n"
        )

    run_git("add", "-A")
    run_git("commit", "-m", "nsos: initial commit — framework baseline snapshot")
    log("✓ Git repo initialized with baseline commit")
    return True

def git_snapshot(description: str) -> Optional[str]:
    """Create a pre-change snapshot tag. Returns tag name or None."""
    tag = f"nsos/pre-{datetime.now().strftime('%Y%m%d-%H%M%S')}"
    ok, out = run_git("tag", tag, "-m", f"NSOS: snapshot before {description}")
    if ok:
        log(f"✓ Snapshot tag: {tag}")
        return tag
    else:
        log(f"⚠ Snapshot tag failed: {out}")
        return None

def git_commit_change(category: str, description: str, evidence: list,
                      confidence: float, approved_by: str = "autonomous") -> Optional[str]:
    """Commit a change with NSOS-format commit message. Returns hash or None."""
    run_git("add", "-A")

    # Check if there's anything to commit
    ok, status = run_git("diff", "--cached", "--stat")
    if not ok or not status.strip():
        log("No changes to commit")
        return None

    msg = (
        f"nsos: [{category}] {description}\n\n"
        f"What: {description}\n"
        f"Why: {'; '.join(evidence[:3])}\n"
        f"Category: {category}\n"
        f"Confidence: {confidence:.2f}\n"
        f"Reversible: yes\n"
        f"Revert: git revert <this-hash>\n\n"
        f"Evidence:\n" + "\n".join(f"- {e}" for e in evidence) + "\n\n"
        f"Approved-by: {approved_by}\n"
    )

    ok, out = run_git("commit", "-m", msg)
    if ok:
        _, hash_out = run_git("rev-parse", "HEAD")
        log(f"✓ Committed: {hash_out[:8]}")
        return hash_out.strip()
    else:
        log(f"✗ Commit failed: {out}")
        return None

# ── PHASE 1: OBSERVE ────────────────────────────────────────────────────────

def observe_corrections() -> list[Observation]:
    """Scan correction patterns for recurring issues."""
    observations = []
    corrections = load_json(CORRECTIONS_FILE)
    if not corrections:
        observations.append(Observation(
            id=gen_id("obs"), category="process_health", source="corrections_observer",
            description="No corrections file found — correction tracking may not be active",
            severity="warning"
        ))
        return observations

    if isinstance(corrections, dict):
        corrections = corrections.get("corrections", [])

    # Check for recurring corrections (same topic 3+ times)
    topic_counts = {}
    for c in corrections:
        tags = c.get("tags", [])
        topic = c.get("category", c.get("topic", "unknown"))
        topic_counts[topic] = topic_counts.get(topic, 0) + 1

    for topic, count in topic_counts.items():
        if count >= 3:
            observations.append(Observation(
                id=gen_id("obs"), category="process_health",
                source="corrections_observer",
                description=f"Recurring correction: '{topic}' appeared {count} times — likely a process gap",
                severity="action_needed",
                evidence=[f"{count} corrections with topic/category '{topic}'"]
            ))

    # Check correction decay health
    now = datetime.now(timezone.utc)
    stale_count = 0
    for c in corrections:
        created = c.get("created_at", c.get("timestamp", ""))
        if created:
            try:
                created_dt = datetime.fromisoformat(created.replace("Z", "+00:00"))
                age_days = (now - created_dt).days
                if age_days > 90 and not c.get("pinned", False):
                    stale_count += 1
            except (ValueError, TypeError):
                continue

    if stale_count > 0:
        observations.append(Observation(
            id=gen_id("obs"), category="process_health",
            source="corrections_observer",
            description=f"{stale_count} corrections are past 90-day soft max age and not pinned",
            severity="info",
            evidence=[f"{stale_count} corrections eligible for archive review"]
        ))

    log(f"  Corrections: {len(corrections)} total, {len(observations)} observations")
    return observations

def observe_skills() -> list[Observation]:
    """Check skill staleness and coverage gaps."""
    observations = []
    if not SKILLS_DIR.exists():
        observations.append(Observation(
            id=gen_id("obs"), category="knowledge", source="skills_observer",
            description="Skills directory not found",
            severity="warning"
        ))
        return observations

    now = datetime.now()
    stale_skills = []
    total_skills = 0

    for skill_file in SKILLS_DIR.glob("*.md"):
        total_skills += 1
        mtime = datetime.fromtimestamp(skill_file.stat().st_mtime)
        age_days = (now - mtime).days
        if age_days > 30:
            stale_skills.append((skill_file.stem, age_days))

    if stale_skills:
        worst = sorted(stale_skills, key=lambda x: -x[1])[:5]
        observations.append(Observation(
            id=gen_id("obs"), category="knowledge", source="skills_observer",
            description=f"{len(stale_skills)}/{total_skills} skills unchanged for 30+ days",
            severity="info" if len(stale_skills) < total_skills * 0.5 else "warning",
            evidence=[f"{name}: {days}d stale" for name, days in worst]
        ))

    log(f"  Skills: {total_skills} total, {len(stale_skills)} stale")
    return observations

def observe_projects() -> list[Observation]:
    """Analyze project health — scoring drift, concentration, staleness."""
    observations = []
    projects_data = load_json(PROJECTS_JSON)
    projects = projects_data.get("projects", [])
    revenue_classes = projects_data.get("revenue_classes", {})

    if not projects:
        observations.append(Observation(
            id=gen_id("obs"), category="revenue", source="projects_observer",
            description="No projects found in projects.json",
            severity="warning"
        ))
        return observations

    # Revenue concentration check
    active_rev = [p for p in projects if p.get("revenue_class") == "active_revenue"]
    total = len(projects)
    if len(active_rev) <= 1 and total > 3:
        observations.append(Observation(
            id=gen_id("obs"), category="revenue", source="projects_observer",
            description=f"Revenue concentration risk: only {len(active_rev)} active revenue project(s) out of {total}",
            severity="warning",
            evidence=[f"Active revenue: {[p['name'] for p in active_rev]}"]
        ))

    # Check for projects without CLAUDE.md
    for p in projects:
        project_path = FRAMEWORK_ROOT / p.get("path", "")
        claude_md = project_path / "CLAUDE.md"
        if project_path.exists() and not claude_md.exists():
            observations.append(Observation(
                id=gen_id("obs"), category="process_health", source="projects_observer",
                description=f"Project '{p['name']}' has no CLAUDE.md — missing project definition",
                severity="info",
                evidence=[f"Path: {p.get('path', 'unknown')}"]
            ))

    # Check for stale project directories (not in projects.json)
    active_projects_dir = FRAMEWORK_ROOT / "Active Projects"
    if active_projects_dir.exists():
        registered_paths = {p.get("path", "") for p in projects}
        for d in active_projects_dir.iterdir():
            if d.is_dir() and not d.name.startswith("."):
                rel = f"Active Projects/{d.name}"
                if rel not in registered_paths:
                    observations.append(Observation(
                        id=gen_id("obs"), category="process_health",
                        source="projects_observer",
                        description=f"Directory '{d.name}' exists but isn't in projects.json",
                        severity="info",
                        evidence=[f"Unregistered project directory: {rel}"]
                    ))

    log(f"  Projects: {total} registered, {len(active_rev)} revenue-generating")
    return observations

def observe_amendments() -> list[Observation]:
    """Review past amendment outcomes for learning signals."""
    observations = []
    amendments = load_jsonl(AMENDMENT_LOG)

    if not amendments:
        log("  Amendments: no history yet (first run)")
        return observations

    # Check approval rate
    reviewed = [a for a in amendments if a.get("status") in ("approved", "rejected")]
    if len(reviewed) >= 5:
        approved = sum(1 for a in reviewed if a["status"] == "approved")
        rate = approved / len(reviewed)
        observations.append(Observation(
            id=gen_id("obs"), category="efficiency", source="amendment_observer",
            description=f"Amendment approval rate: {rate:.0%} ({approved}/{len(reviewed)})",
            severity="info" if rate >= 0.7 else "warning",
            evidence=[f"Approval rate over {len(reviewed)} reviews: {rate:.0%}"]
        ))

    # Check for reverted changes
    reverted = [a for a in amendments if a.get("reverted", False)]
    if reverted:
        observations.append(Observation(
            id=gen_id("obs"), category="process_health", source="amendment_observer",
            description=f"{len(reverted)} past amendments were reverted — check if pattern exists",
            severity="warning",
            evidence=[f"Reverted: {a.get('id', '?')}" for a in reverted[:5]]
        ))

    log(f"  Amendments: {len(amendments)} total, {len(reviewed)} reviewed")
    return observations

def observe_git_hygiene() -> list[Observation]:
    """Check git health — uncommitted changes, orphan branches, etc."""
    observations = []

    ok, _ = run_git("rev-parse", "--git-dir")
    if not ok:
        observations.append(Observation(
            id=gen_id("obs"), category="efficiency", source="git_observer",
            description="No git repository — cannot track changes or revert",
            severity="action_needed",
            evidence=["Git repo not initialized in framework root"]
        ))
        return observations

    # Uncommitted changes
    _, status = run_git("status", "--porcelain")
    if status:
        changed_files = len(status.strip().split("\n"))
        observations.append(Observation(
            id=gen_id("obs"), category="efficiency", source="git_observer",
            description=f"{changed_files} uncommitted changes in framework",
            severity="info" if changed_files < 10 else "warning",
            evidence=[f"{changed_files} files with uncommitted changes"]
        ))

    log(f"  Git: repo {'active' if ok else 'missing'}")
    return observations

def observe_efficiency_rules() -> list[Observation]:
    """Check if efficiency rules have drifted from actual usage."""
    observations = []
    rules = load_json(EFFICIENCY_RULES)
    if not rules:
        return observations

    # Check scoring formula components against projects
    scoring = rules.get("orchestrator_scoring", {})
    projects_data = load_json(PROJECTS_JSON)
    projects = projects_data.get("projects", [])

    # Check if priority weights cover all priorities used in projects
    priority_weights = scoring.get("priority_weights", {})
    project_priorities = {p.get("priority", "unknown") for p in projects}
    missing_priorities = project_priorities - set(priority_weights.keys())
    if missing_priorities:
        observations.append(Observation(
            id=gen_id("obs"), category="efficiency", source="efficiency_observer",
            description=f"Projects use priorities not in scoring weights: {missing_priorities}",
            severity="warning",
            evidence=[f"Missing weights for: {missing_priorities}"]
        ))

    # Check decay rate sanity
    decay = rules.get("correction_decay", {})
    rate = decay.get("decay_weight_per_day", 0)
    if rate > 0.05:
        observations.append(Observation(
            id=gen_id("obs"), category="efficiency", source="efficiency_observer",
            description=f"Correction decay rate ({rate}/day) seems aggressive — corrections may expire too fast",
            severity="warning",
            evidence=[f"At {rate}/day, a correction reaches min weight in {int((1.0 - decay.get('min_weight', 0.1)) / rate)} days"]
        ))

    log(f"  Efficiency rules: checked")
    return observations

# ── PHASE 2: ANALYZE ────────────────────────────────────────────────────────

def analyze(observations: list[Observation]) -> list[Proposal]:
    """Score observations and generate proposals for actionable ones."""
    proposals = []
    amendment_config = load_json(SELF_AMENDMENT)
    categories = amendment_config.get("amendment_categories", {})

    for obs in observations:
        if obs.severity != "action_needed":
            continue

        proposal = observation_to_proposal(obs, categories)
        if proposal and proposal.confidence >= 0.5:
            proposals.append(proposal)

    # Sort by confidence descending
    proposals.sort(key=lambda p: -p.confidence)
    log(f"  Analysis: {len(observations)} observations → {len(proposals)} proposals")
    return proposals

def observation_to_proposal(obs: Observation, categories: dict) -> Optional[Proposal]:
    """Convert an actionable observation into a structured proposal."""

    # Recurring corrections → process restructuring
    if "recurring correction" in obs.description.lower():
        match = re.search(r"'([^']+)' appeared (\d+) times", obs.description)
        topic = match.group(1) if match else "unknown"
        count = int(match.group(2)) if match else 0
        return Proposal(
            id=gen_id("prop"),
            amendment_category="process_restructuring",
            what=f"Create or update skill to address recurring '{topic}' corrections",
            why=f"The same correction topic appeared {count} times, indicating a systemic gap",
            current_value=f"No dedicated skill or rule for '{topic}'",
            proposed_value=f"New skill or rule addition targeting '{topic}' pattern",
            risk="Low — adding a skill doesn't remove existing behavior",
            confidence=min(0.5 + (count * 0.1), 0.95),
            evidence=obs.evidence,
            file_target=str(SKILLS_DIR / f"{topic.lower().replace(' ', '-')}.md")
        )

    # No git repo → parameter tuning (initialize it)
    if "no git repository" in obs.description.lower():
        return Proposal(
            id=gen_id("prop"),
            amendment_category="parameter_tuning",
            what="Initialize git repository for framework change tracking",
            why="Git is required for NSOS snapshot-before-change protocol and full audit trail",
            current_value="No git repo",
            proposed_value="Initialized repo with baseline commit",
            risk="None — adds tracking without changing any files",
            confidence=0.99,
            evidence=obs.evidence,
            file_target=str(FRAMEWORK_ROOT / ".git")
        )

    # Unregistered project directory → process restructuring
    if "isn't in projects.json" in obs.description.lower():
        match = re.search(r"'([^']+)' exists but", obs.description)
        dirname = match.group(1) if match else "unknown"
        return Proposal(
            id=gen_id("prop"),
            amendment_category="process_restructuring",
            what=f"Register '{dirname}' in projects.json or archive it",
            why="Untracked project directories create blind spots in orchestration",
            current_value=f"Directory exists at Active Projects/{dirname} but not in projects.json",
            proposed_value=f"Add entry to projects.json or move to archive",
            risk="Low — registration is additive",
            confidence=0.7,
            evidence=obs.evidence,
            file_target=str(PROJECTS_JSON)
        )

    return None

# ── PHASE 3: PROPOSE ────────────────────────────────────────────────────────

def save_proposals(proposals: list[Proposal]) -> list[dict]:
    """Write proposals to disk and return serialized list."""
    saved = []
    for p in proposals:
        proposal_dict = asdict(p)
        # Save individual proposal file
        proposal_file = PROPOSALS_DIR / f"{p.id}.json"
        save_json(proposal_file, proposal_dict)
        saved.append(proposal_dict)
        log(f"  📋 Proposal {p.id}: [{p.amendment_category}] {p.what}")
        log(f"     Confidence: {p.confidence:.0%} | Risk: {p.risk[:60]}")

    return saved

def filter_by_authority(proposals: list[Proposal]) -> tuple[list[Proposal], list[Proposal]]:
    """Split proposals into auto-applicable and needs-review based on authority."""
    amendment_config = load_json(SELF_AMENDMENT)
    categories = amendment_config.get("amendment_categories", {})
    graduation = amendment_config.get("graduation_rules", {}).get("bounds_after_graduation", {})

    auto = []
    review = []

    for p in proposals:
        cat_config = categories.get(p.amendment_category, {})
        authority = cat_config.get("current_authority", "propose_only")

        if authority == "propose_only":
            # Check if graduated (would need amendment log analysis)
            review.append(p)
        elif authority == "autonomous_within_bounds":
            auto.append(p)
        else:
            review.append(p)

    return auto, review

# ── PHASE 4: APPLY ──────────────────────────────────────────────────────────

def apply_proposal(proposal: Proposal, force: bool = False) -> bool:
    """Apply a single proposal with git snapshot protocol."""
    amendment_config = load_json(SELF_AMENDMENT)
    categories = amendment_config.get("amendment_categories", {})
    cat_config = categories.get(proposal.amendment_category, {})
    authority = cat_config.get("current_authority", "propose_only")

    # Gate check: unless forced, only apply if autonomous
    if authority == "propose_only" and not force:
        log(f"  ⏸ {proposal.id} requires review (category: {proposal.amendment_category})")
        proposal.status = "pending_review"
        # Update proposal file
        save_json(PROPOSALS_DIR / f"{proposal.id}.json", asdict(proposal))
        return False

    # IMMUTABLE: Git snapshot before every modification
    tag = git_snapshot(proposal.what[:80])
    if not tag:
        log(f"  ✗ Cannot apply {proposal.id} — snapshot failed")
        return False

    # Apply the change based on type
    applied = execute_proposal(proposal)
    if not applied:
        log(f"  ✗ Execution failed for {proposal.id}")
        return False

    # Commit with structured message
    git_hash = git_commit_change(
        category=proposal.amendment_category,
        description=proposal.what,
        evidence=proposal.evidence,
        confidence=proposal.confidence,
        approved_by="autonomous" if not force else "operator-dispatch"
    )

    # Log to amendment trail (IMMUTABLE: append-only)
    amendment_entry = {
        "id": proposal.id,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "category": proposal.amendment_category,
        "proposal": proposal.what,
        "evidence": proposal.evidence[0] if proposal.evidence else "",
        "self_confidence": proposal.confidence,
        "status": "applied_autonomous" if not force else "applied_approved",
        "git_hash": git_hash or "no-commit",
        "snapshot_tag": tag,
        "file_changed": proposal.file_target,
        "revert_cmd": f"git revert {git_hash}" if git_hash else f"git checkout {tag} -- .",
        "operator_response": "",
        "reasoning_value": 0.5
    }
    AMENDMENT_LOG.parent.mkdir(parents=True, exist_ok=True)
    append_jsonl(AMENDMENT_LOG, amendment_entry)

    proposal.status = "applied"
    save_json(PROPOSALS_DIR / f"{proposal.id}.json", asdict(proposal))
    log(f"  ✓ Applied {proposal.id} → {git_hash[:8] if git_hash else 'no-commit'}")
    return True

def execute_proposal(proposal: Proposal) -> bool:
    """Execute the actual change described by a proposal. Returns success."""
    # Git initialization proposal
    if "initialize git" in proposal.what.lower():
        return ensure_git()

    # For all other proposals, we write a placeholder action file
    # Real execution would be done by Claude Code reading the proposal
    action_file = PROPOSALS_DIR / f"{proposal.id}.action.md"
    action_file.write_text(
        f"# Action Required: {proposal.what}\n\n"
        f"**Category:** {proposal.amendment_category}\n"
        f"**Confidence:** {proposal.confidence:.0%}\n"
        f"**Target:** {proposal.file_target}\n\n"
        f"## What to do\n{proposal.proposed_value}\n\n"
        f"## Why\n{proposal.why}\n\n"
        f"## Evidence\n" + "\n".join(f"- {e}" for e in proposal.evidence) + "\n"
    )
    log(f"  📝 Action file written: {action_file.name}")
    return True

# ── PHASE 5: LEARN ──────────────────────────────────────────────────────────

def learn(observations: list[Observation], proposals: list[Proposal],
          applied_count: int, deferred_count: int):
    """Record iteration outcomes for future learning."""
    iteration_entry = {
        "id": gen_id("nsos-iter"),
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "observations_count": len(observations),
        "observations_by_severity": {
            "info": sum(1 for o in observations if o.severity == "info"),
            "warning": sum(1 for o in observations if o.severity == "warning"),
            "action_needed": sum(1 for o in observations if o.severity == "action_needed"),
        },
        "proposals_generated": len(proposals),
        "proposals_above_threshold": sum(1 for p in proposals if p.confidence >= 0.7),
        "proposals_applied": applied_count,
        "proposals_deferred": deferred_count,
        "session_trigger": "manual",
        "observers_run": [
            "corrections", "skills", "projects",
            "amendments", "git_hygiene", "efficiency_rules"
        ]
    }
    append_jsonl(ITERATION_LOG, iteration_entry)
    log(f"  📊 Iteration logged: {iteration_entry['id']}")

    # Write a human-readable summary
    summary_file = LOGS_DIR / f"iteration-{datetime.now().strftime('%Y%m%d-%H%M%S')}.md"
    summary_file.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        f"# NSOS Iteration — {datetime.now().strftime('%Y-%m-%d %H:%M')}",
        "",
        f"## Observations ({len(observations)})",
    ]

    for obs in observations:
        icon = {"info": "ℹ️", "warning": "⚠️", "action_needed": "🔴"}.get(obs.severity, "•")
        lines.append(f"- {icon} **[{obs.category}]** {obs.description}")
        for e in obs.evidence:
            lines.append(f"  - {e}")

    lines.append("")
    lines.append(f"## Proposals ({len(proposals)})")
    for p in proposals:
        status_icon = {"applied": "✅", "pending_review": "⏸", "pending": "📋"}.get(p.status, "•")
        lines.append(f"- {status_icon} **{p.id}** [{p.amendment_category}] {p.what}")
        lines.append(f"  - Confidence: {p.confidence:.0%} | Status: {p.status}")

    lines.append("")
    lines.append(f"## Summary")
    lines.append(f"- Observations: {len(observations)}")
    lines.append(f"- Proposals: {len(proposals)} generated, {applied_count} applied, {deferred_count} deferred")
    lines.append(f"- Next iteration: on next manual run or scheduled Monday 10 AM")

    summary_file.write_text("\n".join(lines) + "\n")
    log(f"  📄 Summary: {summary_file.name}")

# ── MAIN ORCHESTRATION ──────────────────────────────────────────────────────

def run_full_iteration():
    """Execute the complete Observe → Analyze → Propose → Apply → Learn loop."""
    log("=" * 60)
    log("NSOS ITERATION — FULL CYCLE")
    log("=" * 60)

    # Ensure directories exist
    for d in [LOGS_DIR, METRICS_DIR, PROPOSALS_DIR, SNAPSHOTS_DIR]:
        d.mkdir(parents=True, exist_ok=True)
    AMENDMENT_LOG.parent.mkdir(parents=True, exist_ok=True)

    # Phase 1: OBSERVE
    log("\n📡 PHASE 1: OBSERVE")
    observations = []
    observers = [
        ("corrections", observe_corrections),
        ("skills", observe_skills),
        ("projects", observe_projects),
        ("amendments", observe_amendments),
        ("git_hygiene", observe_git_hygiene),
        ("efficiency_rules", observe_efficiency_rules),
    ]
    for name, observer_fn in observers:
        try:
            obs = observer_fn()
            observations.extend(obs)
        except Exception as e:
            log(f"  ⚠ Observer '{name}' failed: {e}")

    log(f"\n  Total observations: {len(observations)}")

    # Phase 2: ANALYZE
    log("\n🔬 PHASE 2: ANALYZE")
    proposals = analyze(observations)

    # Phase 3: PROPOSE
    log("\n📋 PHASE 3: PROPOSE")
    if proposals:
        save_proposals(proposals)
        auto, review = filter_by_authority(proposals)
        log(f"  Auto-applicable: {len(auto)} | Needs review: {len(review)}")
    else:
        auto, review = [], []
        log("  No proposals generated — framework is healthy")

    # Phase 4: APPLY (only auto-applicable)
    log("\n⚡ PHASE 4: APPLY")
    applied_count = 0
    if auto:
        ensure_git()
        for p in auto:
            if apply_proposal(p):
                applied_count += 1
    else:
        log("  No auto-applicable proposals this iteration")

    # Mark review items
    for p in review:
        p.status = "pending_review"
        save_json(PROPOSALS_DIR / f"{p.id}.json", asdict(p))

    # Phase 5: LEARN
    log("\n📊 PHASE 5: LEARN")
    learn(observations, proposals, applied_count, len(review))

    # Final report
    log("\n" + "=" * 60)
    log(f"ITERATION COMPLETE")
    log(f"  Observed: {len(observations)} | Proposed: {len(proposals)}")
    log(f"  Applied: {applied_count} | Deferred: {len(review)}")
    log("=" * 60)

    return observations, proposals

def run_observe_only():
    """Run only the observation phase and print findings."""
    log("NSOS — OBSERVE ONLY MODE")
    for d in [LOGS_DIR, METRICS_DIR, PROPOSALS_DIR, SNAPSHOTS_DIR]:
        d.mkdir(parents=True, exist_ok=True)
    observations = []
    for name, fn in [("corrections", observe_corrections), ("skills", observe_skills),
                     ("projects", observe_projects), ("amendments", observe_amendments),
                     ("git_hygiene", observe_git_hygiene), ("efficiency_rules", observe_efficiency_rules)]:
        try:
            observations.extend(fn())
        except Exception as e:
            log(f"  ⚠ Observer '{name}' failed: {e}")
    log(f"\nTotal: {len(observations)} observations")
    for obs in observations:
        icon = {"info": "ℹ️", "warning": "⚠️", "action_needed": "🔴"}.get(obs.severity, "•")
        log(f"  {icon} [{obs.category}] {obs.description}")
    return observations

def run_status():
    """Print current NSOS health dashboard."""
    log("NSOS — STATUS DASHBOARD")
    log("-" * 40)

    # Iteration history
    iterations = load_jsonl(ITERATION_LOG)
    log(f"Iterations run: {len(iterations)}")
    if iterations:
        last = iterations[-1]
        log(f"  Last run: {last.get('timestamp', 'unknown')}")
        log(f"  Observations: {last.get('observations_count', 0)}")
        log(f"  Proposals applied: {last.get('proposals_applied', 0)}")

    # Amendment history
    amendments = load_jsonl(AMENDMENT_LOG)
    log(f"\nAmendments: {len(amendments)} total")
    applied = [a for a in amendments if "applied" in a.get("status", "")]
    reverted = [a for a in amendments if a.get("reverted", False)]
    log(f"  Applied: {len(applied)} | Reverted: {len(reverted)}")

    # Pending proposals
    pending = list(PROPOSALS_DIR.glob("*.json"))
    pending_review = 0
    for pf in pending:
        try:
            p = json.loads(pf.read_text())
            if p.get("status") == "pending_review":
                pending_review += 1
        except:
            continue
    log(f"\nPending proposals: {pending_review} awaiting review")

    # Git status
    ok, _ = run_git("rev-parse", "--git-dir")
    if ok:
        _, log_out = run_git("log", "--oneline", "-5")
        log(f"\nGit: active")
        log(f"  Recent commits:\n    " + log_out.replace("\n", "\n    "))
    else:
        log(f"\nGit: not initialized")

    # Change outcomes
    outcomes = load_jsonl(OUTCOMES_LOG)
    if outcomes:
        positive = sum(1 for o in outcomes if o.get("net_effect") == "positive")
        log(f"\nChange outcomes: {len(outcomes)} measured, {positive} positive")

def run_apply(proposal_id: str, force: bool = False):
    """Apply a specific proposal by ID."""
    proposal_file = PROPOSALS_DIR / f"{proposal_id}.json"
    if not proposal_file.exists():
        log(f"✗ Proposal not found: {proposal_id}")
        # Try partial match
        matches = [f for f in PROPOSALS_DIR.glob("*.json") if proposal_id in f.stem]
        if matches:
            log(f"  Did you mean: {', '.join(f.stem for f in matches)}")
        return False

    data = json.loads(proposal_file.read_text())
    proposal = Proposal(**{k: v for k, v in data.items() if k in Proposal.__dataclass_fields__})

    ensure_git()
    return apply_proposal(proposal, force=force)

def run_revert(amendment_id: str):
    """Revert a specific amendment by ID."""
    amendments = load_jsonl(AMENDMENT_LOG)
    target = None
    for a in amendments:
        if a.get("id") == amendment_id:
            target = a
            break

    if not target:
        log(f"✗ Amendment not found: {amendment_id}")
        return False

    snapshot_tag = target.get("snapshot_tag", "")
    git_hash = target.get("git_hash", "")

    log(f"Reverting amendment: {amendment_id}")
    log(f"  Snapshot tag: {snapshot_tag}")
    log(f"  Git hash: {git_hash}")

    if git_hash and git_hash != "no-commit":
        ok, out = run_git("revert", "--no-edit", git_hash)
        if ok:
            log(f"  ✓ Reverted via git revert")
            # Log the reversion
            revert_entry = {
                "id": gen_id("revert"),
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "category": "revert",
                "proposal": f"Revert of {amendment_id}",
                "evidence": f"Manual revert requested",
                "self_confidence": 1.0,
                "status": "reverted",
                "git_hash": git_hash,
                "original_amendment": amendment_id,
                "reverted": True
            }
            append_jsonl(AMENDMENT_LOG, revert_entry)
            return True
        else:
            log(f"  ✗ Git revert failed: {out}")
            log(f"  Try manually: git checkout {snapshot_tag} -- .")
            return False
    else:
        log(f"  No git hash available. Manual revert needed.")
        if snapshot_tag:
            log(f"  Try: git checkout {snapshot_tag} -- .")
        return False

# ── CLI ─────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="NSOS Self-Iteration Engine",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python3 iterate.py --mode=full        Full iteration loop
  python3 iterate.py --mode=observe     Observe only (no changes)
  python3 iterate.py --mode=propose     Generate proposals without applying
  python3 iterate.py --mode=apply ID    Apply a specific proposal
  python3 iterate.py --mode=revert ID   Revert a specific amendment
  python3 iterate.py --mode=status      Show NSOS health dashboard
  python3 iterate.py --mode=init-git    Initialize git repo only
        """
    )
    parser.add_argument("--mode", required=True,
                        choices=["full", "observe", "propose", "apply", "revert", "status", "init-git"],
                        help="Operation mode")
    parser.add_argument("id", nargs="?", help="Proposal or amendment ID (for apply/revert)")
    parser.add_argument("--force", action="store_true",
                        help="Force-apply a proposal that would normally need review")

    args = parser.parse_args()

    if args.mode == "full":
        run_full_iteration()
    elif args.mode == "observe":
        run_observe_only()
    elif args.mode == "propose":
        observations = run_observe_only()
        proposals = analyze(observations)
        if proposals:
            save_proposals(proposals)
    elif args.mode == "apply":
        if not args.id:
            log("✗ --mode=apply requires a proposal ID")
            sys.exit(1)
        run_apply(args.id, force=args.force)
    elif args.mode == "revert":
        if not args.id:
            log("✗ --mode=revert requires an amendment ID")
            sys.exit(1)
        run_revert(args.id)
    elif args.mode == "status":
        run_status()
    elif args.mode == "init-git":
        ensure_git()

if __name__ == "__main__":
    main()
