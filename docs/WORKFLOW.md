# Workflow Methodology — Output-Deterministic Project Execution
## The Operating Manual for How Projects Get Done

**Purpose:** This document describes the methodology governing all project execution. It is the "why" and "how" behind CLAUDE.md's "what." Read this to understand the thinking that drives every decision.

---

## THE CORE IDEA: OUTPUT-DETERMINISTIC THINKING

Most project methodologies start with inputs (requirements) and work forward to outputs (deliverables). This framework inverts that.

**Output-deterministic thinking means:**
1. Define the ideal end state first — what does success look like to the client?
2. Work backward — what must be true for that end state to exist?
3. Every decision is evaluated by: which option gets closer to the end state?
4. When in doubt: the option that produces a better working product wins.

**This is not aspirational. It is operational.** It governs every phase, every decision, every line of code.

### Applied to Each Phase

| Phase | Output-Deterministic Application |
|-------|--------------------------------|
| Discovery | "What would I need to know to build this perfectly on the first try?" |
| PRD | "What does the delivered system look like? Now decompose what's needed to reach that." |
| Build | "Start with whatever validates the core value proposition fastest." |
| QA | "Test what matters to the client, not what's easy to test." |
| Deployment | "What does a seamless production transition look like?" |
| Handoff | "What does the client need to succeed with this system?" |

---

## THE SIX PHASES IN DEPTH

### Phase 1: Discovery — Maximum Understanding

**Duration:** Hours, not minutes. This is intentional.

**The anti-pattern:** Asking 3 surface-level questions and jumping to build. This guarantees rework.

**The correct approach:**
- **Research Primer first (automatic):** Industry research runs BEFORE any questions. 5 parallel agents (Industry Analyst, Competitor Scanner, Technology Researcher, Client Profiler, Domain Expert) prime the model with context. See `industry-research` skill.
- **MCP Auto-Ingestion (parallel with research):** Auto-pull all available client context from configured MCP servers (Gmail threads, Calendar events, Slack channels, Notion pages, Drive docs). Propose new MCPs if beneficial (Tier 2).
- Read EVERYTHING available (docs, code, emails, data)
- Parallel agents for different source types
- Generate questions in three categories:
  - For Mika (about client relationship — instinctual multiple-choice only)
  - For the client (drafted by Claude, sent by Mika)
  - Self-answerable (Claude researches independently — NEVER ask Mika these, use self-learning skill)
- Map stated needs, unstated needs, and adjacent opportunities
- Document every assumption explicitly
- Produce a discovery brief that Mika reviews before Phase 2

**Self-learning integration:** When encountering anything unfamiliar during discovery (tool, platform, industry regulation, domain), use the self-learning skill. Research is Tier 1. Mika's time is for instinctual decisions and client relationship context only.

**Why maximum, not minimum?** Because every piece of context you miss becomes a wrong assumption. Wrong assumptions become wrong code. Wrong code becomes rework. Rework costs 5-10x the time that thorough discovery would have taken.

**The test:** After discovery, can you describe the client's problem better than they can? If not, keep going.

### Phase 2: PRD Generation — The One-Shot Blueprint

**Duration:** Varies, but don't rush. The PRD quality directly determines build quality.

**The anti-pattern:** A vague feature list that leaves implementation decisions to build time.

**The correct approach:**
- Start from the end state (output-deterministic)
- Work backward through every layer
- Define testable acceptance criteria for everything
- Pre-resolve every possible decision
- Include architecture, data flow, error handling, and deployment
- Risk register with mitigations
- Build roadmap with parallelization opportunities identified

**The test:** Could a developer with zero context build the system from this PRD alone? If not, add more detail.

### Phase 3: Build — Mechanical Execution

**Duration:** This should be the most predictable phase. If it's not, the PRD was incomplete.

**The anti-pattern:** Creative problem-solving during build. If you're making design decisions during build, the PRD failed.

**The correct approach:**
- Break PRD into 2-5 minute micro-tasks
- Use TDD for every task (RED-GREEN-REFACTOR)
- **Run logic alignment audit at every build step** — three teams (Client Lens, Output-Deterministic, Context Integrity) verify the LOGIC serves the end state, not just that it works
- Parallelize independent tasks with agent teams
- Verify every task before marking complete
- Run skill factory in background
- When the PRD is silent on something, STOP and ask — don't improvise
- Commit after every passing task

**The logic alignment test:** At every step, ask: "Does this move us closer to the client's end state?" If the answer isn't clearly yes, run a full 3-pass alignment audit before proceeding.

**The traceability test:** Is every decision traceable to the PRD? If you're making up requirements, go back to Phase 2.

### Phase 4: Quality Assurance — Evidence Generation

**Duration:** Don't shortcut this. The quality report is what gives the client confidence.

**The anti-pattern:** "Tests pass, ship it."

**The correct approach:**
- Run every acceptance criterion from the PRD with evidence
- 8 parallel codebase auditors (security, quality, dependencies, etc.)
- Test quality audit (are the tests themselves good?)
- Fix Critical/High findings
- Generate quality report with evidence for every claim
- Quality gate: explicit GO/NO-GO recommendation

**The test:** If the client asked "how do you know it works?" — could you show them proof?

### Phase 5: Deployment — Careful Transition

**Duration:** Short, but high-stakes. Zero shortcuts.

**The anti-pattern:** Deploying in parallel or without rollback plans.

**The correct approach:**
- Always Tier 2 (Mika approves every deployment action)
- Single-threaded execution (no parallel agents)
- Deploy in PRD-specified order
- Monitor first executions
- Rollback plan ready before deploying
- Document deployment steps for future reference

**The test:** If deployment goes wrong, can you roll back within 5 minutes?

### Phase 6: Handoff — Full Implementation Assistance

**Duration:** Don't rush the polish. The handoff IS the product to the client.

**The anti-pattern:** Dumping technical docs and calling it done.

**The correct approach:**
- Executive summary in business terms
- System documentation for the client's technical level
- Operational runbook (start, stop, monitor, troubleshoot)
- Quality evidence
- Future improvements list
- **Hosting/VPS/infrastructure:** Claude self-learns and configures deployment environments. Research hosting options, propose recommendation (Tier 2), configure everything on approval. Only ask Mika for credentials/payment setup.
- **Communication package:** Draft delivery email, walkthrough agenda, 1-week follow-up, 1-month follow-up — all using voice-profile skill
- **Inbound message analysis:** When client messages arrive, analyze intent, draft responses, flag urgency
- **IRL instructions:** For anything requiring human action, provide numbered steps so simple anyone could follow in under 5 minutes. Include expected outcomes and fallbacks.
- Run retrospective and feed back into framework

**The test:** Could the client's team operate the system for 6 months without calling Mika? Has Claude handled every piece of infrastructure it possibly can, leaving Mika only with tasks that truly require human presence?

---

## PHASE HANDOFF CONTRACTS — TYPED SCHEMAS

Each phase produces a defined output that the next phase consumes. The contract specifies required fields — if a field is missing, the next phase REFUSES TO START and reports what's missing. This eliminates the gap where Phase N+1 discovers mid-execution that Phase N's output is incomplete.

### Discovery → PRD Contract

The discovery brief MUST contain all of the following before PRD generation begins:

```
DISCOVERY_BRIEF_CONTRACT:
  required:
    - end_state_definition        # 1-3 sentences: what does success look like to the client?
    - client_technical_level      # non-technical | semi-technical | technical
    - stakeholder_map             # who cares and what they care about
    - stated_needs[]              # explicit client requirements (min 3)
    - unstated_needs[]            # inferred requirements (min 1)
    - adjacent_opportunities[]    # opportunities the client hasn't noticed
    - competitive_context         # what alternatives exist, why this is better
    - edge_cases[]                # at least 5 edge cases identified
    - assumptions[]               # every assumption documented explicitly
    - technical_constraints[]     # platform, budget, timeline, integration limits
    - data_flow_overview          # what data moves where
    - security_requirements       # authentication, authorization, data handling
    - research_primer_summary     # key findings from industry research
  optional:
    - regulatory_requirements
    - integration_dependencies
    - existing_system_documentation
  validation:
    - end_state_definition must be client-language, not technical
    - every stated_need must be testable
    - every assumption must be flagged as confirmed or unconfirmed
```

### PRD → Build Contract

The PRD MUST contain all of the following before build begins:

```
PRD_CONTRACT:
  required:
    - end_state_description       # detailed: what the delivered system looks like
    - architecture_overview       # components, their relationships, data flow
    - acceptance_criteria[]       # min 1 per feature, all binary pass/fail
    - micro_task_decomposition[]  # every task ≤5 min, with file scope and PRD reference
    - error_handling_spec         # what happens when things go wrong
    - deployment_target           # where this runs, how it gets there
    - risk_register[]             # risks with mitigations
    - parallelization_map         # which tasks can run simultaneously
    - test_strategy               # what gets tested, how, acceptance thresholds
  optional:
    - performance_requirements
    - accessibility_requirements
    - migration_plan
  validation:
    - every acceptance criterion must be independently verifiable
    - every micro-task must reference exactly one PRD section
    - architecture must trace back to end state (no orphan components)
    - risk register must have mitigation for every High/Critical risk
```

### Build → QA Contract

The build output MUST satisfy before QA begins:

```
BUILD_CONTRACT:
  required:
    - all_micro_tasks_complete    # every task from PRD marked pass
    - all_tests_passing           # zero failing tests
    - git_history_clean           # one commit per passing task
    - drift_log_clear             # all drift events resolved (docs/audit-log/alignment/)
    - no_open_blockers            # zero unresolved dependencies
    - deployment_ready            # system can be deployed as-is
  validation:
    - every acceptance criterion from PRD must have a corresponding test
    - every drift correction must reference the PRD section it aligns to
    - test coverage must match test strategy from PRD
```

### QA → Deploy Contract

```
QA_CONTRACT:
  required:
    - quality_report              # evidence-based, every claim backed by test output
    - all_critical_high_fixed     # zero Critical/High findings open
    - go_nogo_recommendation      # explicit recommendation with rationale
    - acceptance_criteria_matrix  # every PRD criterion: pass/fail with evidence
    - regression_clear            # no regressions from fixes
  validation:
    - go_nogo must be based on evidence, not opinion
    - every "pass" must have proof (test output, screenshot, log)
```

### Deploy → Handoff Contract

```
DEPLOY_CONTRACT:
  required:
    - system_live                 # confirmed running in production
    - monitoring_active           # health checks returning green
    - rollback_verified           # rollback tested successfully
    - deployment_documented       # steps recorded for future reference
  validation:
    - monitoring must cover all critical paths identified in PRD
    - rollback must be executable in ≤5 minutes
```

### Handoff Contract (Final Output)

```
HANDOFF_CONTRACT:
  required:
    - executive_summary           # business-language, client-audience
    - system_documentation        # matched to client technical level
    - operational_runbook         # start, stop, monitor, troubleshoot
    - quality_evidence            # from QA report
    - hosting_configured          # infrastructure live and documented
    - delivery_email_draft        # using voice-profile skill
    - irl_instructions            # max 7 steps, each ONE action, estimated time
    - follow_up_schedule          # 1-week and 1-month follow-up drafts ready
  validation:
    - documentation level must match client_technical_level from discovery
    - IRL instructions must each be completable in <5 minutes total
    - every item must answer: "can the client operate this for 6 months without calling Mika?"
```

### Contract Enforcement

When a phase attempts to start and the previous phase's contract is not satisfied:
1. **STOP** — do not begin the next phase
2. **REPORT** — list every missing or invalid field
3. **ROUTE** — send missing items back to the previous phase's Task Manager for completion
4. The phase transition is a hard gate, not a suggestion

---

## AGENT TEAMS — PARALLELIZATION AS DEFAULT

Sequential execution is the exception, not the rule.

**The threshold:** If two tasks are independent and each takes >2 minutes, spawn subagents.

**The independence test:**
- Task A's output is not needed as Task B's input ✅
- They don't edit the same files ✅
- They don't use the same external resources exclusively ✅
- Either could fail without blocking the other ✅

**Phase-specific patterns are documented in `.claude/skills/agent-coordinator/SKILL.md`.**

---

## SKILL ECOSYSTEM — CONTINUOUS IMPROVEMENT

### Core Skills (Always Present)

These skills should be copied into every project's `.claude/skills/` directory:

- `brainstorming` — Socratic questioning before design decisions
- `writing-plans` — Task decomposition into 2-5 minute steps
- `dispatching-parallel-agents` — Parallel delegation patterns
- `verification-before-completion` — Evidence before claims
- `systematic-debugging` — 4-phase root cause analysis
- `test-driven-development` — RED-GREEN-REFACTOR cycle
- `writing-skills` — TDD-based skill creation
- `task-observer` — Meta-skill for pattern detection

### Framework Skills — Phase & Process

- `discovery` — Maximum understanding protocol with instinctual question-asking
- `prd-generation` — Output-deterministic PRD creation
- `build-orchestration` — One-shot build execution
- `quality-assurance` — Evidence-based verification
- `handoff-delivery` — Client-ready delivery packaging
- `agent-coordinator` — Parallel delegation patterns and templates
- `skill-factory` — Background skill creation during build
- `feedback-engine` — Post-project retrospective and framework updates
- `client-communication` — Draft templates for client messages

### Framework Skills — Continuous

- `ralph-loop` — Multi-team simulation review (mandatory before every deliverable)
- `gsd-mode` — Trust-scaled autonomous execution (active during build phases)
- `voice-profile` — Email style training + humanized response timing
- `client-intelligence` — Relationship tracking from all digital communications
- `recursive-context` — Context compounding across all layers (governs all work)
- `skill-sourcing` — External skill discovery and adoption on capability gaps (includes video tutorials, docs, verification-before-applying)
- `multi-instance` — Parallel Claude Code instance coordination
- `quality-audit` — Process, output, regression, and logic alignment auditing across all variables
- `industry-research` — Pre-project research priming with 5 parallel agents (runs before discovery)
- `self-learning` — Research-before-asking protocol with instinct learning loop (governs all unknowns)
- `compaction-resilience` — Checkpoint files + subagent isolation to prevent context loss during auto-compaction (governing)

### Project-Specific Skills

Created by the skill factory during Phase 3. These capture domain-specific patterns worth reusing.

---

## RECURSIVE CONTEXTUALIZATION — HOW CONTEXT COMPOUNDS

The six phases are not a waterfall. They are a spiral. Each phase feeds context into the next, and insights from later phases enrich earlier understanding.

**Per-phase recursive behavior:**

| Phase | Reads From | Writes To | Recursive Trigger |
|-------|-----------|-----------|-------------------|
| Discovery | Client intelligence, practice context | Discovery brief, project context, client intelligence | Adjacent opportunity → enrich discovery scope |
| PRD | Discovery brief, project context | PRD, assumption register, phase context | Skill gap identified → trigger skill-sourcing |
| Build | PRD, phase context, project context | Working code, phase context, project context, skill-factory output | Pattern detected → create skill. Capability gap → source skill. |
| QA | PRD (acceptance criteria), build output | Test results, quality report, phase context | Test finding reveals missed requirement → enrich PRD for future |
| Deployment | PRD, QA report | Deployment log, project context | Production behavior differs from dev → enrich project context |
| Handoff | All context layers | Handoff package, client intelligence, practice context (via feedback engine) | Client feedback → enrich client intelligence for next project |

**The recursive loop is always running:** ENCOUNTER → IDENTIFY → IMPLEMENT → ENRICH. At every phase, at every task, at every decision. This is what makes each project better than the last, and each decision better-informed than the previous one.

See `.claude/skills/recursive-context/SKILL.md` for the full protocol.

---

## DECISION FRAMEWORK SUMMARY

Full details in `DECISION_TIERS.md`. Quick reference:

| Tier | Who Decides | Example |
|------|------------|---------|
| **1: Autonomous** | Claude | Code quality, testing, internal architecture |
| **2: Propose & Wait** | Mika | Client-facing output, cost, scope changes |
| **3: Never** | Manual only | Credentials, client comms, production data |

---

## WORKING-PRODUCT-FIRST PRINCIPLE

At every decision: making the system work correctly > warning that it doesn't.

This applies universally — backend, AI, data flow, client-facing output, handoff. No exceptions.

---

## COMMUNICATION WITH MIKA

- Lead with what matters to the client, not what you did technically
- Batch questions (one structured message > ten individual ones)
- Tier 2 proposals: decision, recommendation, tradeoff, fallback
- Draft client communications for Mika's review
- Never send anything to a client directly

---

## CONTEXT RECOVERY

If a session breaks:
```
Read CLAUDE.md, DECISION_TIERS.md, and WORKFLOW.md.
Check docs/ for existing discovery brief and PRD.
Check git log for completed work.
Run infrastructure verification, then resume.
```

---

## QUALITY AUDIT — CONTINUOUS PROCESS INTELLIGENCE

Quality audit is not a phase. It runs at every phase transition, at every build step, before every deliverable, and after every change.

**Four types:**
1. **Process Audit** — At phase transitions, verifies methodology compliance against all project variables at their CURRENT state.
2. **Output Audit** — Before deliverables, verifies correctness AND optimality against the output-deterministic end state.
3. **Regression Testing** — After changes, tests proportional to change scope. Never over-test, never under-test.
4. **Logic Alignment Audit** — At every build step, three parallel review teams (Client Lens, Output-Deterministic, Context Integrity) verify the LOGIC of each step serves the client's end state. Runs in iterative passes (1-3 based on complexity). Catches drift before it compounds.

**Decision patterns are training data.** Every Mika approval/denial/modification is recorded. Consistent patterns (5+ instances) trigger framework self-modification proposals.

Audit logs persist at `docs/audit-log/` (process/, output/, regression/, alignment/, decisions/) for cross-project analysis. See `.claude/skills/quality-audit/SKILL.md`.

---

## FRAMEWORK SELF-MODIFICATION — ML-STYLE EVOLUTION

This framework improves with every project via the audit → feedback → modify cycle:

1. **Quality audit** generates evidence (process findings, output assessments, decision patterns)
2. **Feedback engine** detects patterns and generates specific framework modification proposals
3. **Mika reviews** every proposal (always Tier 2 — the framework never modifies itself without approval)
4. **Approved changes** are applied to CLAUDE.md, DECISION_TIERS.md, WORKFLOW.md, and skills
5. **Git commit** documents every change with evidence, rationale, and reversibility
6. **Regression verification** ensures no contradictions across framework files

**The ML analogy is operational:** audit data is training data, Mika's decisions are labels, framework modifications are weight updates, Git history is model versioning, and cross-project analysis prevents overfitting.

See `.claude/skills/feedback-engine/SKILL.md` for the full self-modification protocol.

---

*This document is part of the business automation framework. It works alongside CLAUDE.md (master instructions), DECISION_TIERS.md (decision autonomy), and the skills in .claude/skills/.*
