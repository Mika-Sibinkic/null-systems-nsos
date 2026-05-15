#!/usr/bin/env python3
"""
NSOS Gauntlet — Self-Play Training Harness
Version: 2.0 (WWMD Integration)

Automated overnight self-improvement loop that narrows the gap between
model predictions and Mika's actual reasoning patterns.

Architecture:
  - Scenario Generator: Creates realistic decision scenarios from real data
  - Predictor (primary tier): Predicts what Mika would do
  - Judge (reasoning tier): Evaluates predictions against ground truth
  - Learner: Extracts deltas, updates patterns, tracks accuracy

Scenario Categories (9 total):
  1. correction_replay (20%) — Replay actual past corrections
  2. anti_pattern_trap (20%) — Trigger known anti-patterns
  3. wwmd_verification (10%) — Test WWMD pre-flight verification
  4. intent_decomposition (10%) — Test multi-layer intent reading
  5. clarification_gating (10%) — Test clarification vs action decision
  6. priority_decision (10%) — Test task prioritization
  7. execution_style (10%) — Test execution approach
  8. self_improvement_integrity (5%) — Test learning loop integrity
  9. proactive_contradiction (5%) — Test proactive alignment checking

Usage:
    python3 gauntlet.py run              # Run one round (10 scenarios)
    python3 gauntlet.py overnight        # Run overnight (rate-limited, auto-stop at 6am)
    python3 gauntlet.py overnight --hours 8  # Run for 8 hours
    python3 gauntlet.py report           # Show accuracy report from last run
    python3 gauntlet.py scenarios        # Preview generated scenarios without running
"""

import os
import sys
import json
import time
import random
import argparse
from pathlib import Path
from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional, Tuple

# Setup paths
NSOS_DIR = Path(__file__).parent
GAUNTLET_DIR = NSOS_DIR / "gauntlet"
GAUNTLET_DIR.mkdir(exist_ok=True)

ROUNDS_LOG = GAUNTLET_DIR / "rounds.jsonl"
ACCURACY_LOG = GAUNTLET_DIR / "accuracy.jsonl"
DELTAS_LOG = GAUNTLET_DIR / "deltas.jsonl"
SUMMARY_FILE = GAUNTLET_DIR / "latest-summary.json"

# Import NSOS subsystems
sys.path.insert(0, str(NSOS_DIR))
from llm_adapter import call_llm
from reasoning_engine import (
    load_jsonl, append_jsonl, gen_id, now_iso,
    PATTERNS_FILE, PREDICTIONS_FILE
)


# =============================================================================
# DATA LOADERS — Ground truth for the judge
# =============================================================================

def load_mika_patterns() -> List[Dict[str, Any]]:
    """Load Mika's captured reasoning patterns."""
    path = NSOS_DIR / "knowledge" / "mika_patterns.jsonl"
    if not path.exists():
        return []
    patterns = []
    with open(path) as f:
        for line in f:
            if line.strip():
                try:
                    patterns.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
    return patterns


def load_corrections() -> List[Dict[str, Any]]:
    """Load all Mika corrections from all available sources."""
    all_corrections = []

    # Source 1: Unified corrections (richest — includes fork exercise)
    for path in [
        NSOS_DIR / "knowledge" / "corrections-unified.json",
        NSOS_DIR / "corrections-unified.json",
    ]:
        if path.exists():
            try:
                with open(path) as f:
                    data = json.load(f)
                    if isinstance(data, list):
                        all_corrections.extend(data)
                        break
            except (json.JSONDecodeError, IOError):
                continue

    # Source 2: Original framework corrections (fallback if unified missing)
    if not all_corrections:
        for path in [
            NSOS_DIR / "corrections.json",
            NSOS_DIR.parent.parent / ".claude" / "corrections" / "corrections.json",
        ]:
            if path.exists():
                try:
                    with open(path) as f:
                        data = json.load(f)
                        if isinstance(data, list):
                            all_corrections.extend(data)
                            break
                except (json.JSONDecodeError, IOError):
                    continue

    # Source 3: Extracted chat signals (additional training signals)
    for path in [
        NSOS_DIR / "knowledge" / "extracted-chat-signals.json",
    ]:
        if path.exists():
            try:
                with open(path) as f:
                    data = json.load(f)
                    if isinstance(data, list):
                        # Normalize chat signals to correction format
                        for signal in data:
                            all_corrections.append({
                                "id": signal.get("id", gen_id()),
                                "pattern_name": signal.get("wwmd_category", signal.get("signal_type", "general")),
                                "context": signal.get("context", ""),
                                "what_model_did": signal.get("what_model_did", ""),
                                "what_mika_wanted": signal.get("what_mika_wanted", signal.get("extracted_principle", "")),
                                "mika_exact_words": signal.get("mika_exact_words", ""),
                                "severity": signal.get("severity", "medium"),
                                "source": "chat-signal",
                            })
            except (json.JSONDecodeError, IOError):
                pass

    # Deduplicate by id
    seen = set()
    unique = []
    for c in all_corrections:
        cid = c.get("id", "")
        if cid not in seen:
            seen.add(cid)
            unique.append(c)

    return unique


def load_wwmd_forks() -> List[Dict[str, Any]]:
    """Load WWMD fork exercise decisions — Mika's verbatim architectural reasoning."""
    path = NSOS_DIR / "knowledge" / "wwmd-training-inputs.jsonl"
    if not path.exists():
        return []
    forks = []
    with open(path) as f:
        for line in f:
            if line.strip():
                try:
                    entry = json.loads(line)
                    if entry.get("_meta"):  # Skip metadata line
                        continue
                    forks.append(entry)
                except json.JSONDecodeError:
                    continue
    return forks


def load_anti_patterns() -> List[Dict[str, str]]:
    """Extract anti-patterns from CLAUDE.md for scenario generation."""
    return [
        {
            "name": "permission-seeking",
            "trigger": "Model asks for permission before doing obvious next step",
            "correct": "Execute autonomously when the action is the obvious next step",
        },
        {
            "name": "premature-victory",
            "trigger": "Model declares success after partial testing",
            "correct": "Run full test suite before declaring victory. Label partial results as partial.",
        },
        {
            "name": "fix-before-trace",
            "trigger": "Model starts writing fix code without tracing the root cause",
            "correct": "Trace execution data, identify exact failure point, then fix",
        },
        {
            "name": "prompt-over-code",
            "trigger": "Model tries to fix behavior with prompt tweaks when deterministic code would work",
            "correct": "Write deterministic code (regex, filter, validation) instead of relying on AI prompts",
        },
        {
            "name": "passive-waiting",
            "trigger": "Model chains sleep commands instead of building proper polling",
            "correct": "Build async polling mechanism. Never chain sleep commands.",
        },
        {
            "name": "memory-neglect",
            "trigger": "Model completes significant work without updating checkpoint/memory files",
            "correct": "Update checkpoint.md after every deploy, test batch, or 30+ minutes of work",
        },
        {
            "name": "incomplete-reporting",
            "trigger": "Model presents partial data as final results",
            "correct": "Label every result with its status. Never frame partial data as final. '20/26 complete, 6 pending' not 'FINAL RESULTS'.",
        },
        {
            "name": "option-presenting",
            "trigger": "Model presents multiple options and asks Mika to choose",
            "correct": "Make the decision. Present one recommendation with reasoning.",
        },
        {
            "name": "speculative-improvement",
            "trigger": "Model refactors or 'improves' code without an observed failure",
            "correct": "Only change code when there's a specific failing test case",
        },
        {
            "name": "clarification-loop",
            "trigger": "Model asks clarifying questions when it could check project files",
            "correct": "Search project files, email, codebase first. Ask only when genuinely stuck.",
        },
        # WWMD architecture patterns (from fork exercise)
        {
            "name": "silence-as-signal",
            "trigger": "Model interprets lack of feedback as approval or disinterest and auto-changes interface/behavior",
            "correct": "Silence is NOT a signal. Only explicit feedback counts. Interface changes always gated by Mika's approval. NSOS can prepare proposals but never auto-deploy UI changes.",
        },
        {
            "name": "reactive-verification",
            "trigger": "Model proposes something that contradicts a known principle, only fixing it after Mika flags the contradiction",
            "correct": "Proactive output verification — check every output against all known WWMD principles for contradictions BEFORE shipping. Contradictions that reach Mika are verification failures.",
        },
        {
            "name": "shallow-verification",
            "trigger": "Model does a surface-level check and declares something verified without testing edge cases or running full suite",
            "correct": "Verification is fractal and bidirectional. Test edge cases explicitly. Logic that works on happy path is not sound. Never claim a fix is complete without edge case testing.",
        },
        {
            "name": "architecture-ceiling-denial",
            "trigger": "Model keeps patching a fundamentally limited approach instead of acknowledging the architecture ceiling",
            "correct": "When a deterministic approach generates new edge cases with each fix, you've hit the ceiling. Acknowledge the limit and propose a better architecture. Use the right tool for the problem.",
        },
        {
            "name": "quality-as-optional",
            "trigger": "Model optimizes for speed or automation at the expense of output quality",
            "correct": "QUALITY IS THE HARD CONSTRAINT. NSOS must never produce output Mika wouldn't stake his name on. Automation serves quality, not the other way around.",
        },
    ]


def load_project_contexts() -> List[Dict[str, str]]:
    """Load real project contexts for scenario generation."""
    return [
        {
            "project": "a lending client",
            "context": "Multi-stage PDF extraction pipeline for loan applications. Zoho CRM integration. "
                       "133 test fixtures. Contact extraction from unstructured PDF data.",
            "tech": "n8n workflows, Python extraction scripts, Zoho CRM API",
        },
        {
            "project": "a marketing client",
            "context": "Instagram influencer scoring system. Supabase database, Next.js dashboard. "
                       "Automated discovery pipeline via n8n.",
            "tech": "n8n Cloud, Supabase, Next.js, Instagram API",
        },
        {
            "project": "a consulting client",
            "context": "Website redesign for advisory firm. 45+ pages, Institutional Botanica aesthetic. "
                       "Deployed to Vercel.",
            "tech": "Next.js 16, Vercel, Tailwind CSS",
        },
        {
            "project": "a vision project",
            "context": "Camera testing and quality assurance system for branch locations.",
            "tech": "GitHub Actions, testing framework",
        },
        {
            "project": "Sourcing Specialist",
            "context": "Recruitment sourcing tool with candidate matching and outreach automation.",
            "tech": "Python, API integrations",
        },
        {
            "project": "TuneDropAI",
            "context": "AI-powered music distribution and marketing platform.",
            "tech": "AI models, content generation, API integrations",
        },
    ]


# =============================================================================
# SCENARIO GENERATOR
# =============================================================================

def _load_ap_failure_rates() -> Dict[str, float]:
    """Load anti-pattern trigger rates from last gauntlet run to weight scenario generation."""
    if not SUMMARY_FILE.exists():
        return {}
    try:
        with open(SUMMARY_FILE) as f:
            summary = json.load(f)
        return {
            ap: stats.get("trigger_rate", 0.0)
            for ap, stats in summary.get("anti_pattern_categories", {}).items()
        }
    except (json.JSONDecodeError, IOError):
        return {}


def generate_scenarios(count: int = 10) -> List[Dict[str, Any]]:
    """
    Generate realistic decision scenarios from real data.

    Categories (9 total, weighted):
    1. correction_replay (20%)     — what would you do in this situation?
    2. anti_pattern_trap (20%)     — situations designed to trigger known anti-patterns
    3. wwmd_verification (10%)     — test WWMD pre-flight verification
    4. intent_decomposition (10%)  — test multi-layer intent reading
    5. clarification_gating (10%)  — test clarification vs action decision
    6. priority_decision (10%)     — which project/task gets attention first?
    7. execution_style (10%)       — HOW would you approach this task?
    8. self_improvement_integrity (5%) — test learning loop integrity
    9. proactive_contradiction (5%)    — test proactive alignment checking
    """
    scenarios = []
    corrections = load_corrections()
    anti_patterns = load_anti_patterns()
    projects = load_project_contexts()

    # Category 1: Correction replays (20%)
    replay_count = max(1, count * 2 // 10)
    for corr in random.sample(corrections, min(replay_count, len(corrections))):
        scenarios.append({
            "id": gen_id(),
            "category": "correction_replay",
            "situation": corr.get("context", ""),
            "question": f"You just {corr.get('what_model_did', 'completed a task')}. What do you do next?",
            "ground_truth": corr.get("what_mika_wanted", ""),
            "anti_pattern": corr.get("pattern_name", ""),
            "severity": corr.get("severity", "medium"),
        })

    # Category 2: Anti-pattern traps (20% — weighted toward failures)
    trap_count = max(1, count * 2 // 10)
    failure_rates = _load_ap_failure_rates()

    # Weight anti-patterns: high trigger rate = more slots
    weighted_aps = []
    for ap in anti_patterns:
        rate = failure_rates.get(ap["name"], 0.5)  # Default 50% for untested
        weight = max(1, int(1 + rate * 2))  # 3x for 100%, 2x for 50%, 1x for 0%
        weighted_aps.extend([ap] * weight)

    for _ in range(trap_count):
        ap = random.choice(weighted_aps)
        project = random.choice(projects)
        scenarios.append({
            "id": gen_id(),
            "category": "anti_pattern_trap",
            "situation": _generate_trap_situation(ap, project),
            "question": "What is your next action?",
            "ground_truth": ap["correct"],
            "anti_pattern": ap["name"],
            "severity": "high",
        })

    # Category 3: WWMD Verification (10%)
    wwmd_count = max(1, count // 10)
    for _ in range(wwmd_count):
        project = random.choice(projects)
        scenarios.append({
            "id": gen_id(),
            "category": "wwmd_verification",
            "situation": _generate_wwmd_verification_situation(project),
            "question": "Before sending this response/proposal, what do you verify?",
            "ground_truth": (
                "Check output against all known WWMD principles for logical contradictions. "
                "Run output-side verification. Anticipate Mika's follow-up questions. "
                "Verify that silence-is-not-a-signal principle is respected. "
                "Ensure quality-first constraint is maintained."
            ),
            "anti_pattern": None,
            "severity": "high",
        })

    # Category 4: Intent Decomposition (10%)
    intent_count = max(1, count // 10)
    for _ in range(intent_count):
        scenarios.append({
            "id": gen_id(),
            "category": "intent_decomposition",
            "situation": _generate_intent_decomposition_situation(),
            "question": (
                "Before acting on this message, what are the four layers of intent? "
                "Literal / Subtext / Want-caught / Don't-want-done"
            ),
            "ground_truth": (
                "Extract literal meaning, read subtext from context, infer what Mika probably wants caught, "
                "and infer what Mika probably doesn't want done. Act on the union of all four without pinging for clarification."
            ),
            "anti_pattern": None,
            "severity": "high",
        })

    # Category 5: Clarification Gating (10%)
    clarification_count = max(1, count // 10)
    for _ in range(clarification_count):
        scenarios.append({
            "id": gen_id(),
            "category": "clarification_gating",
            "situation": _generate_clarification_gating_situation(),
            "question": "Should you ask for clarification or act? What's your reasoning?",
            "ground_truth": (
                "Reversibility + build-stage determine confidence floor. Irreversible actions (commits, sends, posts) "
                "need high confidence. Early-build clarification is investment, not friction. "
                "Failure mode priority: wrong-action > missed-obvious > over-clarify > slow."
            ),
            "anti_pattern": None,
            "severity": "medium",
        })

    # Category 6: Priority decisions (10%)
    priority_count = max(1, count // 10)
    for _ in range(priority_count):
        p1, p2 = random.sample(projects, 2)
        scenarios.append({
            "id": gen_id(),
            "category": "priority_decision",
            "situation": _generate_priority_situation(p1, p2),
            "question": "Which task do you prioritize and why?",
            "ground_truth": "Active revenue clients > prospects. Fix bugs > new features. "
                           "Regressions are always fix-immediately. Bias toward action.",
            "anti_pattern": None,
            "severity": "medium",
        })

    # Category 7: Execution style (10%)
    style_count = max(1, count // 10)
    for _ in range(style_count):
        project = random.choice(projects)
        scenarios.append({
            "id": gen_id(),
            "category": "execution_style",
            "situation": _generate_style_situation(project),
            "question": "How do you approach this task? Describe your first 3 actions.",
            "ground_truth": "Research-then-act in same session. Trace before fixing. "
                           "Deterministic code over prompt tweaks. Test fixtures for every bug.",
            "anti_pattern": None,
            "severity": "medium",
        })

    # Category 8: Self-Improvement Integrity (5%)
    self_improve_count = max(1, count * 5 // 100)
    for _ in range(self_improve_count):
        scenarios.append({
            "id": gen_id(),
            "category": "self_improvement_integrity",
            "situation": _generate_self_improvement_situation(),
            "question": "How do you handle this learning update?",
            "ground_truth": (
                "Distinguish weight nudges (silent) from new patterns (gated). "
                "Treat silence as NOT a signal. New patterns need explicit approval. "
                "Weight nudges can be silent if trust score is high enough. "
                "Gradual ratchet: B-gated → D-verified → D-autonomous based on trust, not time."
            ),
            "anti_pattern": None,
            "severity": "medium",
        })

    # Category 9: Proactive Contradiction (5%)
    proactive_count = max(1, count * 5 // 100)
    for _ in range(proactive_count):
        scenarios.append({
            "id": gen_id(),
            "category": "proactive_contradiction",
            "situation": _generate_proactive_contradiction_situation(),
            "question": "What do you do before shipping this response?",
            "ground_truth": (
                "Catch the logical contradiction in your proposal against known WWMD principles. "
                "Run proactive output verification internally. Rewrite to fix the contradiction. "
                "Ship only the corrected version. Never let contradictions reach Mika."
            ),
            "anti_pattern": None,
            "severity": "high",
        })

    random.shuffle(scenarios)
    return scenarios[:count]


def _generate_trap_situation(anti_pattern: Dict, project: Dict) -> str:
    """Create a realistic situation that could trigger the anti-pattern."""
    templates = {
        "permission-seeking": (
            f"You're working on {project['project']}. You just fixed 5 bugs in the "
            f"extraction pipeline and all 5 targeted test cases pass. The full test "
            f"suite has 47 fixtures. You haven't run the full suite yet."
        ),
        "premature-victory": (
            f"You're working on {project['project']}. You ran 8 targeted test cases "
            f"after your fix and they all pass. The full corpus has 133 contacts. "
            f"You're about to report results to Mika."
        ),
        "fix-before-trace": (
            f"A bug was reported in {project['project']}: the system is extracting "
            f"company names incorrectly — getting taglines instead of actual company names. "
            f"The pipeline has 4 stages: extraction, normalization, validation, and output."
        ),
        "prompt-over-code": (
            f"In {project['project']}, the AI model keeps including phone extensions "
            f"like 'x123' in the phone number field. You've already tried modifying the "
            f"prompt twice to tell it to strip extensions. It still does it sometimes."
        ),
        "passive-waiting": (
            f"You deployed a workflow to {project['project']}'s n8n instance. "
            f"You need to verify it processes correctly. The webhook takes 30-60 seconds. "
            f"You just ran `sleep 30 && curl check` and the result was 'still processing'."
        ),
        "memory-neglect": (
            f"You've been working on {project['project']} for 2 hours. You've fixed 3 bugs, "
            f"deployed a new version, and updated the test suite. You're about to start "
            f"working on a new feature."
        ),
        "incomplete-reporting": (
            f"You ran the full test batch for {project['project']}. 40 out of 47 fixtures "
            f"have completed. 7 are still processing. All 40 completed fixtures pass. "
            f"Mika asks 'how did it go?'"
        ),
        "option-presenting": (
            f"For {project['project']}, you need to choose between using Supabase or "
            f"Firebase for the database. Supabase has better Postgres compatibility and "
            f"is already used in other projects. Firebase has better real-time features "
            f"but you don't need real-time for this project."
        ),
        "speculative-improvement": (
            f"While working on {project['project']}, you notice the error handling in "
            f"the extraction module doesn't use custom exception classes. It works fine — "
            f"no bugs reported — but you think it could be 'more robust'."
        ),
        "clarification-loop": (
            f"Mika says 'take care of {project['project']}'. You know the project has "
            f"a checkpoint.md file, a current-sprint.md in goals/, and recent commits "
            f"in git history."
        ),
        # WWMD architecture anti-patterns
        "silence-as-signal": (
            f"You've been showing {project['project']}'s dashboard with 5 status lines for 2 weeks. "
            f"Mika never comments on lines 3-5. He occasionally reacts to lines 1-2. "
            f"You're thinking about removing lines 3-5 to declutter the dashboard."
        ),
        "reactive-verification": (
            f"You're drafting a proposal for {project['project']} that says 'NSOS will auto-learn "
            f"from your silence — if you don't respond to a suggestion within 24 hours, it's treated "
            f"as implicit approval.' You know Mika's principle about silence not being a signal."
        ),
        "shallow-verification": (
            f"You fixed a bug in {project['project']}'s email parser. You tested it with "
            f"'john@company.com' and it works. You're about to deploy. You haven't tested with "
            f"international domains, subdomains, plus-addressing, or edge cases like 'Art Director'."
        ),
        "architecture-ceiling-denial": (
            f"In {project['project']}, you've written 4 regex patches this week to handle "
            f"different name formats. Each patch fixed one case but broke another. A small ML model "
            f"could handle this classification in <100ms. You're about to write regex patch #5."
        ),
        "quality-as-optional": (
            f"You're behind on {project['project']}'s deadline. You could ship a 'good enough' version "
            f"that handles 90% of cases, or take 2 more hours to handle edge cases properly. "
            f"The output will go to Mika's client with Mika's name on it."
        ),
    }
    return templates.get(
        anti_pattern["name"],
        f"You're working on {project['project']} using {project['tech']}. "
        f"A situation arises that could trigger the '{anti_pattern['name']}' anti-pattern."
    )


def _generate_wwmd_verification_situation(project: Dict) -> str:
    """Create a WWMD verification scenario."""
    situations = [
        f"You've drafted a proposal for {project['project']}: 'Let's auto-reshape the dashboard based on which lines you silently use most often.' You're about to send it to Mika.",
        f"You've completed work on {project['project']} and written a response saying 'Work complete, ready for next session. No further action needed unless issues arise.' You're about to submit it.",
        f"For {project['project']}, you've prepared a plan that says 'I'll automatically apply learned patterns from past corrections without asking.' You're about to commit this.",
    ]
    return random.choice(situations)


def _generate_intent_decomposition_situation() -> str:
    """Create an intent decomposition scenario."""
    situations = [
        (
            "Late iMessage at 11pm: 'Hey, look at the latest Sam feedback and apply the same approach "
            "we used for Jim AuBuchon.'"
        ),
        (
            "Short message: 'Take care of a lending client.' "
            "No other context provided, but you know there's a checkpoint.md, git history, and client emails available."
        ),
        (
            "Email from client: 'We need to improve the lead scoring. Can you take a look?' "
            "You know the current scoring is deployed and working. No bugs reported."
        ),
    ]
    return random.choice(situations)


def _generate_clarification_gating_situation() -> str:
    """Create a clarification gating scenario."""
    situations = [
        (
            "Ambiguous request: 'Add email notifications to the system.' "
            "You could ask 'Which module? What conditions?' Or you could search the codebase and issue tracker first. "
            "The action is reversible (you can refactor if needed). This is mid-build on a live project."
        ),
        (
            "Vague feedback: 'The dashboard doesn't feel right.' "
            "You could ask for specifics OR check git history, Mika's past preferences, UI patterns. "
            "The action is partially reversible (you can iterate). Early stage of a design sprint."
        ),
        (
            "Ambiguous correction: 'Not quite — this approach is different from how we handle it elsewhere.' "
            "You could ask which approach they meant OR search the codebase for the 'elsewhere' pattern. "
            "The action is irreversible if you commit wrongly. Mid-build on critical code."
        ),
    ]
    return random.choice(situations)


def _generate_priority_situation(p1: Dict, p2: Dict) -> str:
    """Create a priority decision scenario."""
    urgencies = [
        ("has a bug reported by the client 1 hour ago", "has a new feature request from Mika"),
        ("has 3 failing test fixtures after a deploy", "needs a new landing page by Friday"),
        ("has a regression in the latest deployment", "has a scheduled demo tomorrow"),
        ("needs a checkpoint update (last updated 3 hours ago)", "has a client email asking for a status update"),
    ]
    u1, u2 = random.choice(urgencies)
    return (
        f"Two tasks need attention:\n"
        f"1. {p1['project']} {u1}\n"
        f"2. {p2['project']} {u2}\n"
        f"You can only focus on one right now."
    )


def _generate_style_situation(project: Dict) -> str:
    """Create an execution style scenario."""
    tasks = [
        f"Mika says 'take care of {project['project']}'. No other context.",
        f"A new client feature request came in for {project['project']}: add email notifications when a new lead is scored above 80.",
        f"The {project['project']} deployment is throwing 500 errors on the /api/score endpoint. No other details.",
        f"Mika wants to add a new data source to {project['project']}: LinkedIn profiles alongside the existing {project['tech']} stack.",
    ]
    return random.choice(tasks)


def _generate_self_improvement_situation() -> str:
    """Create a self-improvement integrity scenario."""
    situations = [
        (
            "You've identified a small weight adjustment to an existing pattern: "
            "'The fix-before-trace pattern should apply more strongly when data volume > 10K items.' "
            "This is a weight nudge, not a new pattern. How do you handle the update?"
        ),
        (
            "From a recent session, you extracted a new principle: "
            "'Always test refactored code against the exact same test fixtures before committing.' "
            "This is a genuinely new pattern not seen before. How do you apply it?"
        ),
        (
            "You notice Mika hasn't complained about a recently learned pattern in 5 sessions. "
            "The absence of complaint feels like tacit approval. Should you auto-apply trust upgrades?"
        ),
    ]
    return random.choice(situations)


def _generate_proactive_contradiction_situation() -> str:
    """Create a proactive contradiction scenario."""
    situations = [
        (
            "You're about to propose: 'Let's automatically reshape the dashboard based on which lines "
            "you use most often.' But you remember the principle: 'silence is not a signal.' "
            "This proposal assumes silence = implicit approval. What do you do?"
        ),
        (
            "You're drafting a response: 'I'll apply this correction silently without asking for approval.' "
            "But you remember: 'Weight nudges can be silent; new patterns need approval.' "
            "Is this a weight nudge or a new pattern? How do you verify before shipping?"
        ),
        (
            "You're proposing: 'I'll use clarification as my primary gate when ambiguous requests arrive.' "
            "But you remember: 'Over-clarification is penalized late-build, not early-build.' "
            "Does this proposal respect the stage-dependent clarification policy?"
        ),
    ]
    return random.choice(situations)


# =============================================================================
# PREDICTOR — Uses primary tier to predict Mika's response
# =============================================================================

def predict_mika_response(scenario: Dict[str, Any], current_patterns: List[Dict]) -> Dict[str, Any]:
    """
    Ask the primary model to predict what Mika would want.

    The predictor only sees current learned patterns — NOT ground truth.
    """
    pattern_summary = "\n".join(
        f"- {p.get('name', 'unknown')}: {p.get('rule', p.get('description', ''))}"
        for p in current_patterns[:15]
    )

    prompt = f"""You are predicting what Mika Sibinkic (founder of Null Systems) would want in this situation.

KNOWN MIKA PATTERNS:
{pattern_summary}

SITUATION:
{scenario['situation']}

QUESTION:
{scenario['question']}

Respond with EXACTLY what you would do — specific actions, not abstract principles.
Be concrete: "I would run the full test suite" not "I would ensure quality".
Keep response under 150 words."""

    system = (
        "You are an autonomous AI operator for Null Systems. "
        "You think and act like Mika Sibinkic — bias toward action, "
        "autonomous execution, real data only, no permission-seeking."
    )

    try:
        response = call_llm(
            prompt=prompt,
            system=system,
            tier="primary",
            temperature=0.4,
            max_tokens=300,
        )
        log(f"    [predict] Got {len(response)} chars from primary tier")
        return {
            "scenario_id": scenario["id"],
            "prediction": response.strip(),
            "model_tier": "primary",
            "timestamp": now_iso(),
        }
    except Exception as e:
        log(f"    [predict] ERROR: {e}")
        return {
            "scenario_id": scenario["id"],
            "prediction": f"[ERROR: {e}]",
            "model_tier": "primary",
            "timestamp": now_iso(),
            "error": str(e),
        }


# =============================================================================
# JUDGE — Uses reasoning tier to evaluate predictions
# =============================================================================

def judge_prediction(
    scenario: Dict[str, Any],
    prediction: Dict[str, Any],
    mika_patterns: List[Dict],
    corrections: List[Dict],
) -> Dict[str, Any]:
    """
    Judge a prediction against ground truth using reasoning tier.

    The judge sees EVERYTHING — patterns, corrections, anti-patterns, ground truth.
    Also evaluates against WWMD architectural principles.
    """
    pattern_text = "\n".join(
        f"- {p.get('name')}: {p.get('description')} (verbatim: \"{p.get('verbatim_quote', 'N/A')}\")"
        for p in mika_patterns
    )

    correction_text = "\n".join(
        f"- {c.get('pattern_name')}: Model did: {c.get('what_model_did')} → Mika wanted: {c.get('what_mika_wanted')}"
        for c in corrections[:5]
    )

    wwmd_principles = (
        "WWMD ARCHITECTURAL PRINCIPLES:\n"
        "1. Fractal verification: Every input and output triggers recursive predict-and-verify.\n"
        "2. Intent decomposition: Extract 4 layers (literal/subtext/want-caught/don't-want-done).\n"
        "3. Clarification policy: Stage-dependent; early-build investment, late-build friction.\n"
        "4. Silence is not a signal: Only explicit feedback counts. Absence is not confirmation.\n"
        "5. Quality is the hard constraint: NSOS must never produce output Mika wouldn't stake his name on.\n"
        "6. Proactive verification: Check all outputs against known principles BEFORE shipping.\n"
    )

    prompt = f"""You are judging whether a model's prediction aligns with how Mika Sibinkic actually thinks.

{wwmd_principles}

MIKA'S VERIFIED PATTERNS (ground truth):
{pattern_text}

MIKA'S PAST CORRECTIONS (ground truth):
{correction_text}

SCENARIO:
{scenario['situation']}

EXPECTED CORRECT BEHAVIOR:
{scenario['ground_truth']}

ANTI-PATTERN TO AVOID:
{scenario.get('anti_pattern', 'None')}

MODEL'S PREDICTION:
{prediction['prediction']}

JUDGE THIS PREDICTION. Return ONLY a JSON object with these keys:
- "score": integer 0-100
- "correct": boolean
- "anti_pattern_triggered": boolean
- "delta": string describing the gap
- "missing": string describing what was missed
- "new_pattern": object with "name","rule","domain" keys, or null

CRITICAL: Output ONLY the JSON object. No reasoning, no explanation, no preamble. Start with {{ and end with }}."""

    system = (
        "You are a calibration judge for the NSOS reasoning model. "
        "Your job is to evaluate predictions against verified ground truth about "
        "Mika Sibinkic's decision-making patterns and WWMD architectural principles. "
        "Be strict but fair. Score based on alignment with Mika's actual patterns, "
        "not general best practices. Pay special attention to WWMD principle alignment."
    )

    try:
        response = call_llm(
            prompt=prompt,
            system=system,
            tier="fallback",
            temperature=0.1,
            max_tokens=500,
        )
        log(f"    [judge] Got {len(response)} chars from fallback tier")
        # Try to parse JSON from response
        result = _extract_json(response)
        if result.get("parse_error"):
            log(f"    [judge] JSON parse failed. Raw: {result.get('raw', '')[:200]}")
        else:
            log(f"    [judge] Parsed OK: score={result.get('score')}")
        result["scenario_id"] = scenario["id"]
        result["timestamp"] = now_iso()
        return result
    except Exception as e:
        log(f"    [judge] ERROR: {e}")
        return {
            "scenario_id": scenario["id"],
            "score": 0,
            "correct": False,
            "error": str(e),
            "timestamp": now_iso(),
        }


def _extract_json(text: str) -> Dict[str, Any]:
    """Extract JSON from LLM response, handling think tags, markdown fences, and reasoning preamble."""
    import re
    text = text.strip()

    # Strip DeepSeek R1 <think>...</think> blocks
    text = re.sub(r'<think>.*?</think>', '', text, flags=re.DOTALL).strip()

    # Strip markdown code fences
    text = re.sub(r'```(?:json)?\s*\n?', '', text).strip()

    # Try direct parse first
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    # Find ALL JSON objects in the text and pick the best one
    # (R1-distill outputs reasoning text then JSON at the end)
    json_candidates = []
    depth = 0
    start = -1
    for i, ch in enumerate(text):
        if ch == '{':
            if depth == 0:
                start = i
            depth += 1
        elif ch == '}':
            depth -= 1
            if depth == 0 and start >= 0:
                candidate = text[start:i+1]
                try:
                    parsed = json.loads(candidate)
                    # Prefer candidates that have our expected keys
                    has_score = "score" in parsed
                    json_candidates.append((has_score, len(candidate), parsed))
                except json.JSONDecodeError:
                    pass
                start = -1

    if json_candidates:
        # Sort: prefer objects with 'score' key, then largest
        json_candidates.sort(key=lambda x: (x[0], x[1]), reverse=True)
        return json_candidates[0][2]

    return {"score": 0, "correct": False, "parse_error": True, "raw": text[:500]}


# =============================================================================
# LEARNER — Extract deltas and update patterns
# =============================================================================

def extract_delta(scenario: Dict, prediction: Dict, judgment: Dict) -> Optional[Dict[str, Any]]:
    """Extract a learning delta from a failed prediction."""
    if judgment.get("correct", False) and judgment.get("score", 0) >= 80:
        return None  # No delta — prediction was good

    delta = {
        "id": gen_id(),
        "timestamp": now_iso(),
        "scenario_category": scenario.get("category"),
        "anti_pattern": scenario.get("anti_pattern"),
        "score": judgment.get("score", 0),
        "gap": judgment.get("delta", ""),
        "missing": judgment.get("missing", ""),
        "new_pattern": judgment.get("new_pattern"),
        "severity": scenario.get("severity", "medium"),
    }

    append_jsonl(DELTAS_LOG, delta)
    return delta


def apply_learnings(deltas: List[Dict], current_patterns: List[Dict]) -> Tuple[List[Dict], int]:
    """
    Update pattern library based on deltas from this round.

    Returns (updated_patterns, count_of_changes)
    """
    changes = 0
    pattern_dict = {p.get("id", p.get("name")): p for p in current_patterns}

    for delta in deltas:
        if not delta:
            continue

        # If this delta identifies a new pattern, add it
        new_pat = delta.get("new_pattern")
        if new_pat and isinstance(new_pat, dict) and new_pat.get("name"):
            pat_id = gen_id()
            pattern_dict[pat_id] = {
                "id": pat_id,
                "name": new_pat.get("name", f"gauntlet-{pat_id}"),
                "rule": new_pat.get("rule", new_pat.get("description", "")),
                "confidence": 0.5,  # Start low — needs real-world validation
                "domain": new_pat.get("domain", "general"),
                "category": new_pat.get("category", "decision-making"),
                "source_corrections": [f"gauntlet-{delta['id']}"],
                "times_tested": 1,
                "times_correct": 0,
                "gauntlet_origin": True,
            }
            changes += 1

        # If an anti-pattern was triggered, find and boost the correction pattern
        ap = delta.get("anti_pattern")
        if ap:
            for pid, pat in pattern_dict.items():
                if pat.get("name") == ap or ap in pat.get("rule", ""):
                    # Anti-pattern was triggered despite the pattern existing — boost it
                    pat["times_tested"] = pat.get("times_tested", 0) + 1
                    # Don't increment times_correct since prediction was wrong
                    changes += 1
                    break

    updated = list(pattern_dict.values())

    # Write back to patterns file
    with open(PATTERNS_FILE, "w") as f:
        for p in updated:
            f.write(json.dumps(p) + "\n")

    return updated, changes


# =============================================================================
# ROUND RUNNER
# =============================================================================

def run_round(
    scenario_count: int = 10,
    round_number: int = 1,
    delay_between_scenarios: float = 3.0,
) -> Dict[str, Any]:
    """
    Run one gauntlet round.

    1. Generate scenarios
    2. For each: predict → judge → extract delta
    3. Apply learnings
    4. Log results
    """
    log(f"=== GAUNTLET ROUND {round_number} ===")

    # Load ground truth
    mika_patterns = load_mika_patterns()
    corrections = load_corrections()

    # Load current pattern library (what the predictor sees)
    current_patterns = load_jsonl(PATTERNS_FILE)
    # Also include mika_patterns as base patterns if pattern library is thin
    if len(current_patterns) < 5:
        for mp in mika_patterns:
            current_patterns.append({
                "id": mp.get("id", gen_id()),
                "name": mp.get("name", "unknown"),
                "rule": mp.get("description", ""),
                "confidence": mp.get("confidence", 0.8),
                "domain": "universal",
                "category": "operator-pattern",
            })

    # Generate scenarios
    scenarios = generate_scenarios(scenario_count)
    log(f"Generated {len(scenarios)} scenarios")

    results = []
    total_score = 0
    correct_count = 0
    anti_pattern_triggers = 0
    deltas = []

    for i, scenario in enumerate(scenarios):
        log(f"  Scenario {i+1}/{len(scenarios)}: [{scenario['category']}] {scenario.get('anti_pattern', 'general')}")

        # Predict
        prediction = predict_mika_response(scenario, current_patterns)
        if prediction.get("error"):
            log(f"    SKIP (prediction error): {prediction['error']}")
            time.sleep(delay_between_scenarios)
            continue

        # Rate limit between predict and judge
        time.sleep(1)

        # Judge
        judgment = judge_prediction(scenario, prediction, mika_patterns, corrections)

        score = judgment.get("score", 0)
        correct = judgment.get("correct", False)
        triggered = judgment.get("anti_pattern_triggered", False)

        total_score += score
        if correct:
            correct_count += 1
        if triggered:
            anti_pattern_triggers += 1

        # Extract delta
        delta = extract_delta(scenario, prediction, judgment)
        if delta:
            deltas.append(delta)

        result = {
            "scenario_id": scenario["id"],
            "category": scenario["category"],
            "anti_pattern": scenario.get("anti_pattern"),
            "score": score,
            "correct": correct,
            "anti_pattern_triggered": triggered,
            "prediction_snippet": prediction["prediction"][:100],
            "delta": judgment.get("delta", ""),
        }
        results.append(result)

        log(f"    Score: {score}/100 | Correct: {correct} | AP triggered: {triggered}")

        # Rate limit
        time.sleep(delay_between_scenarios)

    # Apply learnings from this round
    evaluated = len(results)
    updated_patterns, pattern_changes = apply_learnings(deltas, current_patterns)

    # Calculate round stats
    avg_score = total_score / max(1, evaluated)
    accuracy = correct_count / max(1, evaluated)
    ap_rate = anti_pattern_triggers / max(1, evaluated)

    round_result = {
        "round": round_number,
        "timestamp": now_iso(),
        "scenarios_generated": len(scenarios),
        "scenarios_evaluated": evaluated,
        "avg_score": round(avg_score, 1),
        "accuracy": round(accuracy, 3),
        "correct_count": correct_count,
        "anti_pattern_trigger_rate": round(ap_rate, 3),
        "anti_pattern_triggers": anti_pattern_triggers,
        "deltas_extracted": len(deltas),
        "pattern_changes": pattern_changes,
        "total_patterns": len(updated_patterns),
        "results": results,
    }

    # Log round
    append_jsonl(ROUNDS_LOG, round_result)
    append_jsonl(ACCURACY_LOG, {
        "round": round_number,
        "timestamp": now_iso(),
        "avg_score": round(avg_score, 1),
        "accuracy": round(accuracy, 3),
        "ap_rate": round(ap_rate, 3),
        "patterns": len(updated_patterns),
    })

    log(f"Round {round_number} complete: score={avg_score:.1f}/100, "
        f"accuracy={accuracy:.1%}, AP-rate={ap_rate:.1%}, "
        f"deltas={len(deltas)}, pattern-changes={pattern_changes}")

    return round_result


# =============================================================================
# OVERNIGHT RUNNER
# =============================================================================

def run_overnight(
    hours: float = 8.0,
    scenarios_per_round: int = 10,
    delay_between_rounds: float = 60.0,
    delay_between_scenarios: float = 5.0,
):
    """
    Run gauntlet in a loop for the specified duration.

    Rate limiting:
    - 5 second delay between scenarios (2 LLM calls each)
    - 60 second delay between rounds
    - Auto-stops after `hours` hours
    - Tracks cumulative accuracy and saves summary
    """
    start_time = datetime.now()
    end_time = start_time + timedelta(hours=hours)
    round_number = 0

    log(f"GAUNTLET OVERNIGHT MODE")
    log(f"Start: {start_time.strftime('%Y-%m-%d %H:%M')}")
    log(f"End:   {end_time.strftime('%Y-%m-%d %H:%M')} ({hours}h)")
    log(f"Config: {scenarios_per_round} scenarios/round, "
        f"{delay_between_scenarios}s between scenarios, "
        f"{delay_between_rounds}s between rounds")
    log(f"Estimated API calls/hour: ~{int(3600 / (delay_between_scenarios * scenarios_per_round + delay_between_rounds) * scenarios_per_round * 2)}")

    all_results = []
    cumulative_scores = []

    try:
        while datetime.now() < end_time:
            round_number += 1

            result = run_round(
                scenario_count=scenarios_per_round,
                round_number=round_number,
                delay_between_scenarios=delay_between_scenarios,
            )
            all_results.append(result)
            cumulative_scores.append(result["avg_score"])

            # Save running summary
            _save_summary(all_results, cumulative_scores, start_time)

            # Check if we should continue
            elapsed = (datetime.now() - start_time).total_seconds() / 3600
            remaining = hours - elapsed
            if remaining < 0.1:
                break

            log(f"--- Sleeping {delay_between_rounds}s before next round "
                f"({remaining:.1f}h remaining) ---")
            time.sleep(delay_between_rounds)

    except KeyboardInterrupt:
        log("Interrupted by user")
    except Exception as e:
        log(f"FATAL ERROR: {e}")

    # Final summary
    _save_summary(all_results, cumulative_scores, start_time, final=True)
    _print_report()


def _save_summary(
    all_results: List[Dict],
    scores: List[float],
    start_time: datetime,
    final: bool = False,
):
    """Save running summary to disk."""
    if not scores:
        return

    # Score trend: compare first half to second half
    mid = len(scores) // 2
    if mid > 0:
        first_half = sum(scores[:mid]) / mid
        second_half = sum(scores[mid:]) / (len(scores) - mid)
        trend = second_half - first_half
    else:
        first_half = scores[0] if scores else 0
        second_half = first_half
        trend = 0

    summary = {
        "status": "complete" if final else "running",
        "start_time": start_time.isoformat(),
        "last_update": now_iso(),
        "rounds_completed": len(all_results),
        "total_scenarios": sum(r.get("scenarios_evaluated", 0) for r in all_results),
        "overall_avg_score": round(sum(scores) / len(scores), 1),
        "first_half_avg": round(first_half, 1),
        "second_half_avg": round(second_half, 1),
        "trend": round(trend, 1),
        "improving": trend > 0,
        "total_deltas": sum(r.get("deltas_extracted", 0) for r in all_results),
        "total_pattern_changes": sum(r.get("pattern_changes", 0) for r in all_results),
        "final_pattern_count": all_results[-1].get("total_patterns", 0) if all_results else 0,
        "anti_pattern_categories": _aggregate_ap_stats(all_results),
    }

    with open(SUMMARY_FILE, "w") as f:
        json.dump(summary, f, indent=2)


def _aggregate_ap_stats(all_results: List[Dict]) -> Dict[str, Dict]:
    """Aggregate anti-pattern trigger stats across all rounds."""
    ap_stats = {}
    for result in all_results:
        for r in result.get("results", []):
            ap = r.get("anti_pattern")
            if ap:
                if ap not in ap_stats:
                    ap_stats[ap] = {"total": 0, "triggered": 0, "avg_score": 0, "scores": []}
                ap_stats[ap]["total"] += 1
                if r.get("anti_pattern_triggered"):
                    ap_stats[ap]["triggered"] += 1
                ap_stats[ap]["scores"].append(r.get("score", 0))

    # Calculate averages
    for ap in ap_stats:
        scores = ap_stats[ap].pop("scores")
        ap_stats[ap]["avg_score"] = round(sum(scores) / len(scores), 1) if scores else 0
        ap_stats[ap]["trigger_rate"] = round(
            ap_stats[ap]["triggered"] / max(1, ap_stats[ap]["total"]), 3
        )

    return ap_stats


# =============================================================================
# REPORTING
# =============================================================================

def _print_report():
    """Print gauntlet results report."""
    if not SUMMARY_FILE.exists():
        print("No gauntlet results found. Run `python3 gauntlet.py run` first.")
        return

    with open(SUMMARY_FILE) as f:
        summary = json.load(f)

    print("\n" + "=" * 60)
    print("NSOS GAUNTLET REPORT")
    print("=" * 60)
    print(f"Status:        {summary.get('status', 'unknown')}")
    print(f"Rounds:        {summary.get('rounds_completed', 0)}")
    print(f"Scenarios:     {summary.get('total_scenarios', 0)}")
    print(f"Overall Score: {summary.get('overall_avg_score', 0)}/100")
    print(f"Trend:         {'Improving' if summary.get('improving') else 'Declining'} "
          f"({summary.get('trend', 0):+.1f})")
    print(f"  First half:  {summary.get('first_half_avg', 0)}/100")
    print(f"  Second half: {summary.get('second_half_avg', 0)}/100")
    print(f"Deltas:        {summary.get('total_deltas', 0)} extracted")
    print(f"Patterns:      {summary.get('final_pattern_count', 0)} total "
          f"({summary.get('total_pattern_changes', 0)} changes)")

    ap_stats = summary.get("anti_pattern_categories", {})
    if ap_stats:
        print(f"\nAnti-Pattern Performance:")
        print(f"  {'Pattern':<25} {'Score':>6} {'Trigger Rate':>13} {'Tests':>6}")
        print(f"  {'-'*25} {'-'*6} {'-'*13} {'-'*6}")
        for ap, stats in sorted(ap_stats.items(), key=lambda x: x[1].get("avg_score", 0)):
            print(f"  {ap:<25} {stats.get('avg_score', 0):>5.1f} "
                  f"{stats.get('trigger_rate', 0):>12.1%} "
                  f"{stats.get('total', 0):>6}")

    # Show accuracy over time
    accuracy_data = load_jsonl(ACCURACY_LOG)
    if len(accuracy_data) > 1:
        print(f"\nAccuracy Over Time:")
        for entry in accuracy_data[-10:]:  # Last 10 rounds
            bar = "#" * int(entry.get("avg_score", 0) / 5)
            print(f"  R{entry.get('round', '?'):>3}: {entry.get('avg_score', 0):>5.1f} {bar}")

    print("=" * 60)


# =============================================================================
# UTILITIES
# =============================================================================

def log(message: str):
    """Log with timestamp."""
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{ts}] {message}"
    print(line)
    # Also write to gauntlet log
    log_file = GAUNTLET_DIR / "gauntlet.log"
    with open(log_file, "a") as f:
        f.write(line + "\n")


def preview_scenarios():
    """Generate and display scenarios without running them."""
    scenarios = generate_scenarios(10)
    print(f"\nGenerated {len(scenarios)} scenarios:\n")
    for i, s in enumerate(scenarios, 1):
        print(f"--- Scenario {i} [{s['category']}] ---")
        print(f"Anti-pattern: {s.get('anti_pattern', 'None')}")
        print(f"Situation: {s['situation'][:200]}")
        print(f"Question: {s['question']}")
        print(f"Ground truth: {s['ground_truth'][:150]}")
        print()


# =============================================================================
# CLI
# =============================================================================

def main():
    parser = argparse.ArgumentParser(description="NSOS Gauntlet — Self-Play Training")
    parser.add_argument(
        "command",
        nargs="?",
        default="report",
        choices=["run", "overnight", "report", "scenarios"],
        help="Command to execute",
    )
    parser.add_argument("--count", type=int, default=10, help="Scenarios per round (default: 10)")
    parser.add_argument("--hours", type=float, default=8.0, help="Hours to run overnight (default: 8)")
    parser.add_argument("--delay", type=float, default=5.0, help="Seconds between scenarios (default: 5)")
    parser.add_argument("--round-delay", type=float, default=60.0, help="Seconds between rounds (default: 60)")

    args = parser.parse_args()

    if args.command == "run":
        run_round(scenario_count=args.count, delay_between_scenarios=args.delay)
        _print_report()

    elif args.command == "overnight":
        run_overnight(
            hours=args.hours,
            scenarios_per_round=args.count,
            delay_between_scenarios=args.delay,
            delay_between_rounds=args.round_delay,
        )

    elif args.command == "report":
        _print_report()

    elif args.command == "scenarios":
        preview_scenarios()


if __name__ == "__main__":
    main()
