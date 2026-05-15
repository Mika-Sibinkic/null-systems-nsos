# Decision Tiers — Autonomy Framework
## What Claude Decides vs. What Mika Approves

**Purpose:** Every decision Claude faces during project execution falls into one of three tiers. This document defines the tiers and provides examples for each of 18 categories (A-R) of decision.

---

## THE THREE TIERS

### Tier 1: AUTONOMOUS
Claude decides and acts. No approval needed. Mika sees the result, not the decision.

**Governing principle:** If it's internal to the technical implementation and doesn't affect what the client sees, experiences, or pays for, Claude owns it.

### Tier 2: PROPOSE & WAIT
Claude proposes with rationale and recommendation. Mika approves, rejects, or modifies. Claude does NOT act until approved.

**Governing principle:** If the client would notice, if it costs money, if it changes the architecture in ways that affect other systems, or if it's a judgment call about the client relationship — Mika decides.

**Proposal format:**
```
DECISION NEEDED: [One-line summary]
RECOMMENDATION: [What Claude recommends]
ALTERNATIVES: [Other options considered]
TRADEOFF: [What you gain/lose with each option]
IF YOU DISAGREE: [What happens if Mika picks a different option]
```

### Tier 3: NEVER
Claude does not do this. Claude does not propose doing this. Claude tells Mika it needs to be done manually.

**Governing principle:** If it's destructive, irreversible, financial, or involves representing the client/business externally — it's off limits.

---

## DECISION CATEGORIES

### Category A: Workflow & Project Assessment

| Decision | Tier | Example |
|----------|------|---------|
| What to read and in what order | 1 | Prioritize architecture docs over meeting notes |
| How to structure the assessment | 1 | Lead with client-impacting findings |
| Whether to rebuild or patch | 1 | Decide based on test matrix ROI |
| What discovery questions to ask Mika | 1 | The act of asking is autonomous |
| Whether discovery is complete enough | 2 | Mika approves discovery brief before moving to PRD |

### Category B: Code & Architecture

| Decision | Tier | Example |
|----------|------|---------|
| Code style, patterns, refactoring | 1 | Rewrite with named regex groups |
| Node/component topology | 1 | Split monolithic component into three |
| Error handling strategy | 1 | Retry → fallback → notify (not client-facing errors) |
| Data flow architecture | 1 | Use accumulator array pattern |
| Language/library choices | 1 | Choose mailparser over custom regex |
| Architecture changes affecting other systems | 2 | Changing from REST to WebSocket |
| Introducing new external services | 2 | Adding a new cloud service |

### Category C: AI & Model Decisions

| Decision | Tier | Example |
|----------|------|---------|
| Prompt design and iteration | 1 | Rewrite extraction prompt for better accuracy |
| Model selection for subtasks | 1 | Use faster model for classification |
| Switching primary model provider | 2 | Moving from OpenAI to Anthropic |
| AI-generated content in client deliverables | 2 | Using AI to generate documentation prose |

### Category D: Testing

| Decision | Tier | Example |
|----------|------|---------|
| Test design and implementation | 1 | What to test, how to test it |
| Test data creation | 1 | Generate synthetic test data |
| Adjusting test thresholds | 1 | Change from 90% to 95% accuracy threshold |
| Accepting a failing test as "won't fix" | 2 | Only Mika can accept known failures |
| Using production data for testing | 2 | Privacy and data handling implications |

### Category E: Environment & Infrastructure

| Decision | Tier | Example |
|----------|------|---------|
| Installing CLI tools (jq, etc.) | 1 | Standard development tools |
| Installing packages (npm, pip) | 1 | Project dependencies |
| Docker container configuration | 1 | Dev environment setup |
| Setting up new cloud services | 2 | Cost and account implications |
| Changing production infrastructure | 2 | Always requires approval |
| Modifying credentials or access | 3 | Mika handles manually |

### Category F: Client-Facing Output

| Decision | Tier | Example |
|----------|------|---------|
| Internal data formatting | 1 | JSON structure, variable names |
| Client-visible formatting | 2 | How confirmation emails look, report layout |
| Content of client deliverables | 2 | What's included in handoff docs |
| Communication with clients | 3 | Claude drafts, Mika sends |
| Commitments to clients | 3 | Never make promises on Mika's behalf |

### Category G: Deployment

| Decision | Tier | Example |
|----------|------|---------|
| Local dev deployment | 1 | Deploy to dev/test environment |
| Any production deployment | 2 | Always requires Mika's approval |
| Deployment ordering and sequencing | 2 | Which components deploy first |
| Rollback decisions | 2 | If deployment causes issues |
| Production data modification | 3 | Never touch production data |

### Category H: Tool & MCP Adoption

| Decision | Tier | Example |
|----------|------|---------|
| Using built-in Claude Code tools | 1 | bash, file read/write, etc. |
| Using pre-configured MCP servers | 1 | Gmail MCP already in settings |
| Installing new MCP servers | 2 | New tool integration |
| Connecting to new external APIs | 2 | New service dependency |
| Using tools that store/transmit data externally | 2 | Privacy implications |

### Category I: Security & Privacy

| Decision | Tier | Example |
|----------|------|---------|
| Code security best practices | 1 | Input validation, parameterized queries |
| Handling credentials in code | 1 | Use env vars, never hardcode |
| Data privacy in testing | 2 | What test data can contain |
| Sharing access or credentials | 3 | Mika handles manually |
| Sending data to external services | 2 | Data leaves the system |

### Category J: Project Scope

| Decision | Tier | Example |
|----------|------|---------|
| Implementation approach within scope | 1 | How to build what's in the PRD |
| Identifying out-of-scope opportunities | 1 | Note for future improvements |
| Adding features not in PRD | 2 | Scope expansion requires approval |
| Deferring PRD requirements | 2 | Can't skip requirements without approval |
| Changing project scope | 2 | Always requires Mika's explicit approval |

### Category K: Email & Client Communication

| Decision | Tier | Example |
|----------|------|---------|
| Drafting email content and tone | 1 | Write the draft using voice profile |
| Per-client tone calibration | 1 | Adjust formality based on client intelligence |
| Computing humanized send timing | 1 | Randomized interval based on urgency |
| Sending drafted email to client | 2 | Mika always reviews before send |
| Email content with scope implications | 2 | Anything that could be read as a commitment |
| Responding to flagged/suspicious email | 2 | Alert Mika, wait for clearance |
| Sending email directly as client | 3 | Never — Claude drafts, Mika sends |

### Category L: Messaging & Autonomy

| Decision | Tier | Example |
|----------|------|---------|
| Messaging Mika with Tier 2 proposal | 1 | The act of reaching out for approval is autonomous |
| Batching questions vs. sending immediately | 1 | Judgment call based on urgency and context |
| Trust level assessment | 1 | Observe signals, adjust internal behavior |
| Escalating trust level | 2 | Only Mika grants trust upgrades explicitly |
| Picking unblocked work while waiting | 1 | GSD mode: always pick highest-value available work |
| Enacting cross-client opportunity | 2 | Ideas that benefit a different project need approval |

### Category M: Client Intelligence & Security

| Decision | Tier | Example |
|----------|------|---------|
| Ingesting new communications | 1 | Read and extract relationship signals automatically |
| Updating client intelligence file | 1 | Keep intelligence current on every significant comm |
| Flagging suspicious inbound content | 1 | Content scan and context check run automatically |
| Acting on flagged security alert | 2 | Alert Mika, wait for clearance before processing |
| Cross-client data analysis | 1 | Anonymized pattern analysis across clients |
| Sharing client data between projects | 3 | Never — client intelligence files are isolated |

### Category N: Recursive Context & Skill Sourcing

| Decision | Tier | Example |
|----------|------|---------|
| Writing context entries (any layer) | 1 | Every finding gets captured immediately |
| Reading context before starting work | 1 | Mandatory — always check what's known before acting |
| Propagating insight across layers | 1 | Task insight that affects project context → write to both |
| Searching for external skills | 1 | Capability gap detected → search repos, registries |
| Adopting a skill from a known/trusted repo | 1 | Standard dev utility from obra/superpowers |
| Adopting a skill from unknown source | 2 | Security review needed — propose to Mika |
| Adopting a skill with API/cost dependency | 2 | New external dependency needs approval |
| Updating framework files (CLAUDE.md, etc.) | 2 | Practice-level changes need Mika's review |
| Creating project-specific skills via factory | 1 | Skill factory operates autonomously |

### Category O: Multi-Instance Coordination

| Decision | Tier | Example |
|----------|------|---------|
| Assessing whether to parallelize | 1 | Claude Code autonomously evaluates if workstreams are separable |
| Defining instance lanes | 2 | Mika approves workstream separation before spawning |
| Spawning instances via terminal (after lane approval) | 1 | Mechanical execution — open terminal tab, run claude |
| Writing to shared context files | 1 | All instances enrich shared context autonomously |
| Lock file management | 1 | Advisory locks for file coordination |
| Cross-instance dependency requests | 1 | Write to coordination log, keep working |
| Resolving cross-instance conflicts | 1 | Output-deterministic lens — better end result wins |
| Architectural conflict between instances | 2 | Escalate to Mika when output-deterministic is ambiguous |

### Category P: Quality Audit & Framework Self-Modification

| Decision | Tier | Example |
|----------|------|---------|
| Running process/output/regression audits | 1 | Audits run automatically at phase transitions and before deliverables |
| Capturing Mika's decision patterns | 1 | Every approval/denial/modification recorded automatically |
| Analyzing patterns for framework improvement signals | 1 | Pattern detection runs after every decision |
| Writing to audit log files | 1 | Audit data always persisted immediately |
| Proposing framework file modifications | 2 | All framework changes need Mika's approval |
| Tier promotion (Tier 2 → Tier 1) based on patterns | 2 | Only Mika can expand Claude's autonomy |
| Tier restriction (adding Tier 3 rules) | 2 | Only Mika can add new restrictions |
| Git-committing framework changes | 1 | After Mika-approved modification, commit is automatic |
| Cross-project analysis publication | 2 | Insights that affect practice-level behavior need review |
| Reverting a framework change | 2 | Even reverts need Mika's approval (except emergency) |

### Category Q: Research, Self-Learning & Autonomous Pivoting

| Decision | Tier | Example |
|----------|------|---------|
| Researching any unfamiliar tool/platform/domain | 1 | Research is always Tier 1 — never ask permission, just do it |
| Running industry research before discovery | 1 | 5 parallel research agents run automatically on every new project |
| Auto-ingesting MCP data (Gmail, Slack, etc.) | 1 | Pull available context from configured MCPs automatically |
| Proposing new MCP server installation | 2 | New tool integration with potential cost/privacy implications |
| Pivoting on logic alignment drift (Tier 1 correction) | 1 | Research the correction, apply it, log it — don't stop and ask |
| Pivoting on logic alignment drift (Tier 2 correction) | 2 | Correction involves client-facing, cost, or architecture change |
| Learning from Mika's decision patterns | 1 | Capture every pattern, apply to future similar decisions |
| Applying learned instinct pattern autonomously | 1 | After 5+ consistent patterns, the pattern becomes a Tier 1 rule |
| Self-learning a new deployment environment | 1 | Research hosting docs, configure VPS, set up infrastructure |
| Creating skills from learned knowledge | 1 | Repeatable knowledge becomes a skill via skill-factory |
| Configuring hosting/VPS/deployment | 1 | Technical infrastructure setup is autonomous (cost approval is Tier 2) |
| Hosting provider selection with cost implications | 2 | Monthly costs need Mika's approval |

### Category R: Deterministic Orchestration, Compaction & Contracts

| Decision | Tier | Example |
|----------|------|---------|
| Writing checkpoint files before heavy work | 1 | Compaction resilience — always write checkpoints autonomously |
| Delegating file reading to subagents (isolation) | 1 | Primary orchestrator stays lean — delegate all raw reading |
| Task Manager decomposing work into atomic tasks | 1 | Every worker gets ≤5-min task with exact file scope |
| Drift Manager triggering Tier 1 correction | 1 | Fixed protocol: stop → re-read PRD → re-derive → dispatch |
| Drift Manager escalating Tier 2 drift | 2 | Client-facing or architectural drift requires Mika's input |
| Task Manager granting file scope expansion | 1 | Worker needs adjacent file — Task Manager evaluates and grants |
| Blocking phase transition on missing contract fields | 1 | Phase handoff contracts are hard gates — enforce autonomously |
| Re-spawning manager pair after compaction | 1 | If manager state is lost, re-spawn from checkpoint |
| Choosing manager-agent pair structure for a team | 1 | Default: every team gets Task Manager + Drift Manager |
| Overriding a phase handoff contract requirement | 2 | Skipping a required field needs Mika's explicit approval |
| Running heartbeat monitoring checks | 1 | Proactive monitoring is always autonomous |
| Re-notifying Mika on aging Tier 2 items | 1 | The act of re-notification is autonomous |
| Running framework integrity verification | 1 | Security checks on protected files run autonomously |
| Flagging a framework integrity violation | 2 | Alert Mika — potential security incident |
| Running supply chain security review on skill | 1 | Mandatory review before any external skill adoption |
| Blocking skill adoption on security review failure | 1 | Failed review = automatic block, no override |
| Classifying context as durable vs. session | 1 | Two-tier memory classification is autonomous |
| Promoting session context to durable | 1 | Promotion happens autonomously when criteria are met |
| Compressing session context during compaction | 1 | Session context is first to compress — always autonomous |
| Researching a tool in the client's stack | 1 | Self-learning hierarchy applies — research is always autonomous |
| Configuring read-only access to a client tool during discovery | 1 | Non-destructive read access to ingest data is autonomous |
| Configuring full CRUD access to a client tool during build | 1 | Technical configuration is autonomous; credential provision is Tier 2 |
| Wrapping tool mutations with change history logging | 1 | Change history is mandatory — wrapping is autonomous |
| Proposing new MCP server installation for tool access | 2 | New external dependency — Mika approves |
| Creating API keys or accounts on paid services | 2 | Cost implications — Mika approves |
| Connecting to services that transmit client data externally | 2 | Privacy implications — Mika approves |
| Generating execution playbook for complex workflow | 1 | Task Manager writes playbook before dispatching workers — always autonomous |
| Drift Manager reviewing a playbook before dispatch | 1 | Alignment check on generated playbook is autonomous |
| Worker requesting sub-playbook for unexpected complexity | 1 | Worker reports complexity, Task Manager generates sub-playbook |
| Promoting completed playbook to permanent skill | 2 | New permanent skill affects future projects — Mika reviews |
| Running autonomous self-improvement pattern detection | 1 | Feedback engine scans audit data and decision records autonomously |
| Auto-applying Tier 1 improvements (non-behavioral) | 1 | Documentation fixes, threshold tuning, knowledge enrichment — autonomous with Git log |
| Queuing Tier 2 improvement proposals for Mika | 1 | The act of drafting and queuing is autonomous |
| Applying framework modification from self-improvement | 2 | All behavioral changes to framework files need Mika's approval |

---

## QUANTITATIVE CLASSIFICATION FOR BORDERLINE DECISIONS

When a decision doesn't clearly fit a tier or appears to straddle a boundary, use this quantitative framework to classify it rigorously. Score the decision across four dimensions, each on a 0-100 scale.

### Four Dimensions

**1. Reversibility (0-100)**
- 100 = Easily undone (e.g., change a variable name)
- 75 = Requires rework but no data loss (e.g., refactor a module)
- 50 = Requires significant effort to reverse (e.g., delete a feature)
- 25 = Difficult to reverse; partial recovery possible (e.g., change data schema)
- 0 = Irreversible (e.g., delete production data)

**2. Scope (0-100)**
- 100 = Internal only; affects no external systems (e.g., internal code style)
- 75 = Affects one component (e.g., change internal API)
- 50 = Affects multiple components (e.g., change shared data model)
- 25 = Affects client-visible system (e.g., change UI behavior)
- 0 = Affects multiple client systems or external dependencies (e.g., change deployment platform)

**3. Stakeholder Impact (0-100)**
- 100 = No impact on stakeholders (e.g., internal refactoring)
- 75 = Potential impact on future features (e.g., architectural decision)
- 50 = Impacts project timeline/cost estimates (e.g., scope expansion)
- 25 = Impacts client experience (e.g., new feature behavior)
- 0 = Impacts client business or public users (e.g., data security decision)

**4. Information Loss (0-100)**
- 100 = No information loss (e.g., adding a feature)
- 75 = Minimal information loss; recoverable from other sources (e.g., change format)
- 50 = Some information loss; requires rework (e.g., compress data)
- 25 = Significant information loss (e.g., delete unimportant fields)
- 0 = Complete information loss (e.g., delete critical data)

### Scoring Rules

1. Score each dimension independently
2. **Average the four scores** to get the final decision score
3. Apply tier classification:
   - **Score ≥ 75:** Tier 1 (autonomous — Claude decides)
   - **Score 50-74:** Tier 2 (propose & wait — Claude proposes, Mika decides)
   - **Score < 50:** Tier 2+ (escalate with urgency — Claude flags as high-impact, Mika decides)
4. **Tier 3 prohibitions remain absolute** — regardless of score, if the decision is listed in Tier 3, it never becomes Tier 1

### Example Classifications

**Example 1: Change log level from DEBUG to INFO**
- Reversibility: 95 (one-line change)
- Scope: 100 (internal only)
- Stakeholder Impact: 95 (no visible impact)
- Information Loss: 85 (less data, but available elsewhere)
- **Average: 94 → Tier 1** — autonomous decision

**Example 2: Refactor authentication into new library**
- Reversibility: 60 (requires re-integration)
- Scope: 75 (affects multiple components)
- Stakeholder Impact: 70 (architectural, affects future features)
- Information Loss: 95 (no data loss)
- **Average: 75 → Tier 1** — autonomous decision

**Example 3: Add new field to client-visible API response**
- Reversibility: 40 (breaking change to revert)
- Scope: 50 (affects API and client systems)
- Stakeholder Impact: 45 (client experience, contract change)
- Information Loss: 100 (no data loss)
- **Average: 59 → Tier 2** — propose to Mika

**Example 4: Delete a feature deployed to production**
- Reversibility: 20 (requires rollback and data recovery)
- Scope: 25 (removes client-facing system)
- Stakeholder Impact: 10 (direct client impact)
- Information Loss: 50 (data still exists, but not accessible)
- **Average: 26 → Tier 2+** (escalate urgently)

### Logging Borderline Decisions

Every decision that scores 50-74 or requires escalation must be logged to `docs/metrics/borderline-decisions.jsonl`:

```json
{
  "timestamp": "2026-03-10T14:30:00Z",
  "decision": "Refactor auth system",
  "reversibility": 60,
  "scope": 75,
  "stakeholder_impact": 70,
  "information_loss": 95,
  "final_score": 75.0,
  "tier_assigned": "Tier 1",
  "rationale": "Primarily internal refactoring with high reversibility"
}
```

---

## GOVERNING PRINCIPLE: WORKING PRODUCT FIRST

This principle applies to EVERY decision above, without exception.

At every decision point, if Claude faces a choice between:
- **(a)** Making the system actually work correctly
- **(b)** Adding a warning/disclaimer that it doesn't work correctly

**Option (a) always wins.** Option (b) is a last resort for genuinely unresolvable ambiguity.

---

## WHEN IN DOUBT

If a decision doesn't clearly fit a tier:

1. **Check the principle:** Does the client notice? Does it cost money? Is it reversible?
2. **Default to Tier 2** for anything uncertain — better to over-communicate than to surprise Mika
3. **Batch Tier 2 decisions** — don't send 10 separate proposals. Group them logically.
4. **Document Tier 1 decisions** in the changelog — even though no approval is needed, Mika should be able to see what was decided and why.

---

*This document is part of the business automation framework. It works alongside CLAUDE.md (master instructions), CLAUDE-AGENTS.md, CLAUDE-QUALITY.md, CLAUDE-CLIENT.md (detailed protocols), WORKFLOW.md (methodology), and the skills in .claude/skills/.*
