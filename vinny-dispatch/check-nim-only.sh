#!/usr/bin/env bash
# check-nim-only.sh — lint guard enforcing the Claude/NIM separation rule.
#
# Fails (exit 1) if any file outside the whitelist imports an LLM client.
# Whitelist:
#   engine/router/nim_client.py        — the NIM client itself
#   vinny-dispatch/router/orchestrator.py — only place that may invoke `claude -p`
#   vinny-dispatch/router/nim_worker.py   — only place that imports nim_client
#
# Run before any commit. Wire into pre-commit when ready.

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
WHITELIST=(
  "engine/router/nim_client.py"
  "vinny-dispatch/router/orchestrator.py"
  "vinny-dispatch/router/nim_worker.py"
)

# Patterns that indicate an LLM client import
PATTERNS=(
  "from anthropic"
  "import anthropic"
  "from openai"
  "import openai"
  "from groq"
  "import groq"
  "from nim_client"
  "from engine\\.router\\.nim_client"
  "subprocess.*claude"
  "os\\.system.*claude"
)

violations=0
for pat in "${PATTERNS[@]}"; do
  while IFS= read -r line; do
    file="${line%%:*}"
    rel="${file#$REPO_ROOT/}"
    # Skip whitelist
    in_whitelist=0
    for w in "${WHITELIST[@]}"; do
      [[ "$rel" == "$w" ]] && in_whitelist=1 && break
    done
    [[ $in_whitelist -eq 1 ]] && continue
    # Skip test, doc, __pycache__, _archive, _deprecated, and this script itself
    case "$rel" in
      tests/*|*.md|*__pycache__*|_archive/*|engine/_deprecated/*|.git/*) continue ;;
      vinny-dispatch/check-nim-only.sh) continue ;;
    esac
    echo "✗ violation: $rel matches /$pat/"
    echo "    $line"
    violations=$((violations + 1))
  done < <(grep -rEn "$pat" "$REPO_ROOT" --include="*.py" --include="*.sh" 2>/dev/null || true)
done

if [[ $violations -eq 0 ]]; then
  echo "✓ nim-only check passed — no LLM client imports outside whitelist"
  exit 0
else
  echo ""
  echo "✗ $violations violation(s) — see above"
  exit 1
fi
