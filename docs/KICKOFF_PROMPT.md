# Project Kickoff — One-and-Done Intake
## Copy-paste into Claude Code. Fill in the blanks. Everything else is automatic.

---

### NEW PROJECT — Full Kickoff

Open Claude Code in your project directory and paste this single block. Fill in the `[brackets]`:

```
Read these documents in full, in this order:
1. CLAUDE.md (your master operating instructions)
2. CLAUDE-AGENTS.md, CLAUDE-QUALITY.md, CLAUDE-CLIENT.md (detailed protocols)
3. DECISION_TIERS.md (what you decide vs. what I approve)
4. WORKFLOW.md (the methodology — how we work)

PROJECT:
- Client: [name]
- Project: [one-line description]
- Client technical level: [non-technical / semi-technical / technical]
- Key stakeholders: [who cares]
- Timeline: [deadlines if any]
- Budget constraints: [if any]
- Returning client? [yes/no]

AVAILABLE SOURCES:
- [List documents, codebases, email threads, repos, data files, etc.]
- [MCP servers configured: Gmail, Slack, Notion, etc.]
- [Existing infrastructure or systems]

SPECIAL CONSIDERATIONS:
- [Anything unique — client quirks, regulatory requirements, technical constraints]

NOW EXECUTE:

STEP 1: Infrastructure Verification
  Run the verification sequence from CLAUDE.md.
  Check: project files, required tools, external services, MCP servers, credentials.
  Guide me through fixing anything broken. Do NOT proceed until green.

STEP 2: Initialize
  Read all skills in .claude/skills/.
  Spawn task-observer subagent for background observation.
  If returning client: read docs/client-intelligence/[client-name].md.
  Run domain scan — identify capability gaps and trigger skill-sourcing for any domains
  we don't have skills for yet. Propose adoptions before discovery begins.
  Initialize docs/project-context.md and docs/phase-context/ directory.
  Initialize docs/audit-log/ directory (process/, output/, regression/, alignment/, decisions/).

STEP 2.5: Industry Research (Automatic — Before Discovery)
  Run the industry-research skill. 5 parallel agents research:
  Industry landscape, competitor solutions, technology stack, client profile, domain knowledge.
  Auto-ingest from all configured MCP servers (Gmail, Slack, Notion, Calendar, Drive).
  If a useful MCP isn't configured, propose installation (Tier 2).
  Produce Research Primer (docs/research-primer.md).
  Use the primer to skip questions research already answered.

STEP 3: Discovery (Phase 1)
  Execute the discovery skill — informed by the Research Primer.
  Parallel agents for source reading (use MCP ingestion data as baseline).
  Instinctual discovery: quick multiple-choice questions, 3-4 per round, adaptive depth.
  Every question relates to how the production product works or behaves.
  Skip anything the research primer already answered.
  Self-learn any unfamiliar domains — research is Tier 1, never ask me about tools or platforms.
  Enrich project-context.md as you learn.
  Present discovery brief for my review.
  Validate discovery brief against Discovery→PRD handoff contract (WORKFLOW.md).
  Do NOT proceed to Phase 2 until I approve AND all contract fields are satisfied.

STEP 4: PRD (Phase 2) — after discovery approval
  Execute prd-generation skill.
  The PRD is the one-shot build prompt.
  Present for my review. Do NOT proceed until approved.

STEP 5: Build through Handoff (Phases 3-6)
  GSD mode: trust-scaled autonomy, never idle when blocked.
  Manager-Agent pairs for every worker team: Task Manager decomposes,
  Drift Manager watches alignment. Hard file scope boundaries enforced.
  Logic alignment audit at EVERY build step: 3 teams (Client Lens,
  Output-Deterministic, Context Integrity) verify logic serves end state.
  Ralph loop before any deliverable.
  Recursive context: write findings to context layers as you go.
  Skill factory runs in background, creating project-specific skills.
  Skill sourcing activates on any capability gap.
  Quality audit runs continuously: process audit at phase transitions,
  output audit before deliverables, regression after changes,
  logic alignment at every build step.
  Capture every Tier 2 decision response as a decision pattern.
  After build: QA with full audit suite.
  After QA: present quality report. Deploy only with my approval.
  After deploy: full handoff package — hosting/VPS configured, communication drafts ready,
  IRL instructions for anything requiring human action, feedback engine retrospective.
  Feedback engine: analyze all audit data, propose framework modifications, Git-commit approved changes.

OPERATING PRINCIPLES:
- Output-deterministic: start from end result, work backward.
- Agent teams for any parallelizable work. Spawn instances autonomously when warranted.
- Working-product-first: correct behavior > warnings about incorrect behavior.
- Tier 1: you own. Tier 2: propose and wait. Tier 3: never.
- Context compounds: every output enriches what comes next.
- Skills self-expand: source externally when gaps are found.
- Research before asking: if you don't know something, LEARN IT. Research is always Tier 1.
- Self-learning: 7-step hierarchy. Only ask me for instinctual/relationship decisions.
- Industry research: prime yourself before every project. 5 parallel agents. Start informed, not cold.
- MCP auto-ingestion: pull all available context from configured MCPs automatically.
- Instinct learning: capture my decision patterns. Apply them. Ask fewer questions each project.
- Pivot autonomously: when alignment drifts, research the correction and apply it. Don't stop.
- Security: scan all inbound comms. Alert me on anything suspicious.
- Quality audit: process, output, regression, logic alignment — continuous, not just Phase 4.
- Logic alignment: 3 teams verify every build step serves the client's end state. Iterative passes catch drift.
- Self-improvement: audit data + my decisions train the framework. Propose updates. Git everything.
- Voice profile: draft emails as me. Humanized timing.
- Client intelligence: ingest everything. Know what I know.
- Handoff: configure hosting/VPS yourself. Draft all communications. IRL instructions are stupid-simple.
- Deterministic orchestration: Task Manager + Drift Manager for every team. Hard file scopes. Phase handoff contracts.
- Compaction resilience: write checkpoints before heavy work. Delegate reading to subagents. Lossless hierarchical summaries. Re-read checkpoint on recovery.
- Framework integrity: core files are immutable during execution. No agent may modify CLAUDE.md, skills, or decision tiers. Changes only through feedback-engine + Git.
- Heartbeat monitoring: proactively check aging approvals, client follow-ups, deadline proximity, stale context, audit schedules. Never wait passively.
- Supply chain security: 5-point review (instruction audit, permission scope, behavioral validation, provenance, dependencies) before adopting any external skill.
- Two-tier memory: classify context as durable (permanent knowledge) or session (temporary observations). Promote session to durable when confirmed.
- Infrastructure self-configuration: when a client tool is discovered (N8N, Supabase, CRMs, etc.), autonomously research → configure connection → verify → integrate with change history. Phase-aware: read-only during discovery, full CRUD during build.
- Execution playbooks: when Task Manager encounters complex workflows (3+ dependent steps, cross-tool, unfamiliar domains), write a narrow protocol with decision trees and verification steps BEFORE dispatching workers. Playbooks used 3+ times promote to permanent skills.
- Autonomous self-improvement: the framework improves itself without prompting. Heartbeat-triggered pattern detection on decision records, audit logs, changelogs, and retrospectives. Tier 1 improvements auto-applied with Git logging. Tier 2 proposals queued and batched for my review.
```

That's it. One paste. Everything else is handled by the framework.

---

### MID-PROJECT DROP-IN

If you're already in the middle of a project and want to bring the framework in:

```
Read CLAUDE.md, CLAUDE-AGENTS.md, CLAUDE-QUALITY.md, CLAUDE-CLIENT.md.
Read DECISION_TIERS.md and WORKFLOW.md.
Read all skills in .claude/skills/.

I'm in the middle of a project. Here's where things stand:
- Client: [name]
- What's done: [completed work]
- What's in progress: [current tasks]
- What's next: [remaining work]
- Current phase: [Discovery / PRD / Build / QA / Deploy / Handoff]

Initialize the framework from the current phase:
1. Run infrastructure verification
2. Initialize docs/project-context.md with what's known
3. If client intelligence exists, read it
4. Resume execution using framework methodology from current phase forward
5. Activate recursive context, ralph loop, GSD mode, and skill sourcing
```

---

### CONTEXT RECOVERY

If a session breaks or hits context limits:

```
Read CLAUDE.md, CLAUDE-AGENTS.md, CLAUDE-QUALITY.md, CLAUDE-CLIENT.md.
Read DECISION_TIERS.md and WORKFLOW.md.
Read all skills in .claude/skills/.
Read docs/project-context.md and docs/phase-context/*.
Check docs/ for discovery brief and PRD (if they exist).
Check git log or changelog for completed work.
Read docs/instance-state/ (if multi-instance).
Run infrastructure verification.
Resume from current phase. Present status summary before continuing.
```

---

### POST-DISCOVERY BUILD KICKOFF

After discovery brief and PRD are both approved:

```
The discovery brief (docs/discovery-brief.md) and PRD (docs/prd.md) are approved.

Execute Build → QA → Deploy → Handoff:

BUILD (GSD mode):
1. Decompose PRD into micro-tasks
2. Spawn skill-factory subagent
3. Agent teams for independent tasks
4. TDD for every task
5. Ralph loop before presenting deliverables
6. Never idle — pick highest-value unblocked work when blocked
7. Enrich project-context.md and phase-context/ throughout
8. Source skills for any capability gaps discovered during build

QA:
1. Run every acceptance criterion with evidence
2. Full audit suite (8 codebase + 5 test auditors)
3. Fix Critical/High, re-verify
4. Ralph loop the quality report (all 4 agents + re-run)
5. GO/NO-GO recommendation

Present quality report. Do NOT deploy until I approve.
```

---

### MULTI-INSTANCE LAUNCH

When the primary instance spawns additional instances, each new instance gets this prompt:

```
Read CLAUDE.md, CLAUDE-AGENTS.md, CLAUDE-QUALITY.md, CLAUDE-CLIENT.md.
Read DECISION_TIERS.md and WORKFLOW.md.
Read all skills in .claude/skills/.
Read docs/instance-lanes.md.
I am Instance [A/B/C].

MY LANE: [description]
MY FILES: [owned directories]
DO NOT MODIFY: [other instances' files]

Read shared context: docs/project-context.md, docs/phase-context/.
Update docs/instance-state/instance-[letter].md after every significant step.
Check docs/lock-file.md before modifying shared files.
If I need something from another instance, write to docs/coordination-log.md and
continue with highest-value work in my lane.

Execute within my lane using full framework methodology.
```

---

*This prompt template is part of the business automation framework. Fill in the brackets, paste, and go.*
