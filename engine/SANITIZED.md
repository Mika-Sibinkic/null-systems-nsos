# Engine Sanitization Log

Source: `null-systems-business-framework/taipei/Active Projects/NSOS/`
Destination: `null-systems-nsos/engine/`

All eight target source files (plus the `handlers/` directory) were copied
into this `engine/` tree and then edited in-place to strip operator-specific
identity, paths, and provider-specific assumptions. The originals were not
modified.

## Identity tokens

Operator and company identity are now parameterized via env vars across the
engine. Defaults are intentionally generic.

| Variable | Default |
|---|---|
| `OPERATOR_NAME` | `Operator` (or `operator` in modules where the lowercase reads better) |
| `COMPANY_NAME` | `the firm` |

Embedded prompt strings either use these variables directly or carry the
`<OPERATOR>` / `<COMPANY>` template tokens for later substitution.

## Per-file changes

### `engine/gauntlets/gauntlet.py` (1402 lines)
- Renamed function `load_mika_patterns` -> `load_operator_patterns`.
- Renamed function `predict_mika_response` -> `predict_operator_response`.
- Renamed JSON keys `mika_patterns`, `what_mika_wanted`, `mika_exact_words`
  -> `operator_patterns`, `what_operator_wanted`, `operator_exact_words`.
- `WWMD` -> `WWOD` ("What Would Operator Do") across header, prompts,
  scenario categories, and architectural-principles block.
- Replaced literal `"Mika"`, `"Mika Sibinkic"`, `"Null Systems"` with
  `<OPERATOR>` / `<COMPANY>` template tokens in prompt strings.
- Replaced hardcoded client project list (a lending client, a marketing client, a consulting client, Branch
  Cam Testing, Sourcing Specialist, TuneDropAI) with `ProjectAlpha` ...
  `ProjectFoxtrot` placeholders, loadable from
  `NSOS_DIR/knowledge/project_contexts.json`.
- Updated all comments + docstrings that referenced "Mika" to "operator".

### `engine/router/llm_adapter.py` (697 lines)
- Extracted embedded `NSOS_SYSTEM` prompt into
  `engine/router/prompts/system_default.txt` and added `_load_system_prompt()`
  with `{OPERATOR_NAME}` / `{COMPANY_NAME}` substitution.
- Added `OPERATOR_NAME` and `COMPANY_NAME` env-var loading.
- Renamed `classify_mika_message()` -> `classify_operator_message()` and
  rewrote its prompt to refer to "the operator" instead of "Mika".
- Updated docstrings and prompt strings in `analyze_correction()` and
  `synthesize_learning_session()` to use "operator".

### `engine/router/meta_router.py` (387 lines)
- File contained no operator-specific identity references beyond the NSOS
  brand itself (which is the engine's own name and stays). Routing taxonomy
  + auditing logic is generic. No sanitization edits required.

### `engine/reasoning/task_decomposer.py` (775 lines)
- Stripped `Mika`/`a marketing client`/`Null Systems` from header docstring,
  decomposition prompt, optimization prompt, and CLI defaults.
- Added `OPERATOR_NAME` / `COMPANY_NAME` env-var loading and used them in
  the inline LLM system prompt and the two task prompts.
- Made tier mapping config-loadable: introduced `_load_tier_config()` reading
  `engine/reasoning/tier_config.json` (falls back to defaults if absent).
  Both `MODEL_TIERS` and `TIER_DEFINITIONS` are overridable.
- `--operator` CLI flag default switched from hardcoded `"mika"` to
  `OPERATOR_NAME`.

### `engine/gauntlets/eval_harness.py` (426 lines)
- Replaced hardcoded `~/Desktop/Null Systems/...` paths with env-driven
  `NSOS_DATA_DIR`, `NSOS_DIR`, and `NSOS_HARNESS_DIR`.
- Renamed metric `mika_alignment` -> `operator_alignment` (also in
  `JUDGE_PROMPT` schema).
- Updated `JUDGE_PROMPT` to refer to "the operator" instead of
  "Mika Sibinkic".
- Renamed "Mika's HARD RULE" comment to "Operator HARD RULE".
- Replaced "take care of a marketing client" example task with "take care of <project>".

### `engine/gauntlets/iterate.py` (995 lines)
- Stripped `Null Systems LLC` author tag and product-tagline language.
- Replaced hardcoded `~/Desktop/Null Systems/...` paths with env-driven
  `NSOS_FRAMEWORK_ROOT`, `NSOS_BIZ_ROOT`, `NSOS_ORCHESTRATOR_DIR`, and
  `NSOS_DIR`.
- Renamed `approved_by="mika-dispatch"` -> `"operator-dispatch"`.
- Renamed amendment-log key `mika_response` -> `operator_response`.

### `engine/gauntlets/quality_judge.py` (466 lines)
- Extracted rubric, dimensions, calibration note, thresholds, and judge-call
  parameters into `engine/gauntlets/quality_rules.json`.
- Added `_load_rules()` + `_build_rubric_prompt()` that compose the system
  prompt with `{OPERATOR_NAME}` / `{COMPANY_NAME}` substitution.
- Renamed SQLite column `mika_response` -> `operator_response` (table is
  created on first run, no migration needed).
- Genericized header docstring: "Groq" -> "fast-tier LLM"; "Mika response"
  -> "operator response".
- Genericized inline comments mentioning "Groq" to "the configured fast
  tier" / "provider".

### `engine/router/handlers/` directory
- **take_care.py**: rewrote header docstring as `project_dispatch`, removed
  hardcoded `PROJECT_MAP` (16 personal client folders) and replaced with
  `_load_project_map()` reading `NSOS_DIR/knowledge/project_map.json`.
  Replaced hardcoded `Active Projects/` path with `PROJECTS_DIR`
  (`NSOS_PROJECTS_DIR` env var). Renamed `WWMD_SYSTEM` -> `WWOD_SYSTEM` and
  rewrote prompt to refer to "the operator". Renamed JSON key
  `needs_mika` -> `needs_operator` (kept handler logic but cleared the
  back-compat fallback). Replaced hardcoded
  `~/.claude/projects/-Users-operator-...` framework-memory path with
  env-driven `NSOS_MEMORY_PATHS`. Updated reply text "NEEDS MIKA" ->
  "NEEDS OPERATOR".
- **take.py**: only docstring change ("When Mika texts..." -> "When the
  operator addresses...").
- **ask.py**: extracted `_detect_projects()` to consume the same
  `knowledge/project_map.json`, removed the hardcoded 13-project mapping.
  Replaced hardcoded `Active Projects/` and Desktop framework-memory paths
  with env-driven equivalents. Identity in `ASK_SYSTEM` parameterized via
  `OPERATOR_NAME` / `COMPANY_NAME`. Conversation log label "Mika:" ->
  "Operator:".
- **ingest_youtube.py**: replaced "background batch on Dell" comment with
  "background batch on the host machine".
- All other handlers (`improve.py`, `ingest_instagram.py`, `judge.py`,
  `regression.py`, `status.py`, `thread.py`, `verbs.py`, `__init__.py`) had
  no operator-specific references and were copied verbatim.

## Verification

Every sanitized file was syntax-checked:
```
python3 -c "import ast; ast.parse(open('<path>').read())"
```
All 11 files (8 + 3 handler files touched) parse cleanly.

Residual grep across the engine tree for `mika | null systems | dell |
rustdesk | sibinkic`:
- ZERO matches in the eight target files and the handlers covered above.
- Three OTHER files in `engine/reasoning/` (`agent_tracker.py`,
  `prompt_evolver.py`, `reasoning_engine.py`) and one in
  `engine/cascade-handler/cascade_handler.py` still contain the word
  "Mika" but those files were NOT in the sanitization scope for this pass.
  They were copied into the destination tree by a prior step and remain
  untouched.

## Companion config files written

- `engine/router/prompts/system_default.txt` (27 lines) — system prompt
  template for `llm_adapter.NSOS_SYSTEM`.
- `engine/gauntlets/quality_rules.json` (26 lines) — rubric + thresholds
  for `quality_judge`.

## Optional knowledge files (not created — load if you want richer behavior)

These are read with safe fallbacks if absent. Create them to inject real
project context without code edits:
- `engine/router/knowledge/project_map.json` — `{ "lowercase_keyword":
  "Folder Name" }` for project resolution in `take_care.py` / `ask.py`.
- `engine/router/knowledge/project_contexts.json` — list of
  `{project, context, tech}` records used by `gauntlet.py` scenario
  generation.
- `engine/reasoning/tier_config.json` — `{ "model_tiers": {...},
  "tier_definitions": {...} }` overrides for `task_decomposer.py`.

## Follow-up pass: re-sanitize four previously-untouched files

A second sanitization pass was run on the four files flagged at the end of
the first pass (residual `Mika` mentions). All edits were surgical
identifier/string swaps with no logic changes; line counts unchanged.

### `engine/reasoning/agent_tracker.py` (474 lines, unchanged)
- Docstring: `"Generate a weekly agent performance report for Mika."` ->
  `"... for the operator."` (1 change, comments/docstrings).

### `engine/reasoning/prompt_evolver.py` (640 lines, unchanged)
- `specialize` strategy prompt string: `"Mika Sibinkic's"` -> `"<OPERATOR>'s"`,
  `"Mika-specific"` -> `"operator-specific"` (2 changes, prompt strings).

### `engine/reasoning/reasoning_engine.py` (580 lines, unchanged)
- `extract_pattern()` docstring: `"Extract pattern from Mika correction."` ->
  `"... from operator correction."` (1 change, docstring).
- Schema reference in docstring: `what_mika_wanted` -> `what_operator_wanted`
  (1 change, docstring).
- Dict-key lookup: `correction_data.get("what_mika_wanted", "")` ->
  `correction_data.get("what_operator_wanted", "")` (1 change, JSON key —
  matches the `gauntlet.py` rename in the first pass).

### `engine/cascade-handler/cascade_handler.py` (536 lines, unchanged)
- Recovery-strategy docstring: `"Escalate to human (Mika)"` ->
  `"Escalate to human (the operator)"` (1 change, docstring).

### Verification (this pass)
All four files re-checked:
- `python3 -c "import ast; ast.parse(...)"` -> OK on all four.
- `grep -i "mika\|null systems\|dell\|rustdesk\|nashville\|cloudflare"` ->
  ZERO matches on all four.
- Line counts pre/post: 474/474, 640/640, 580/580, 536/536 (no logic loss).

Aggregate this pass: 6 string/identifier replacements across 4 files.
The engine tree is now clean of all listed identity tokens across every
sanitized file.
