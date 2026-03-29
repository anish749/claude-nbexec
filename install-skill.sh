#!/usr/bin/env bash
set -euo pipefail

REPO_DIR="$(cd "$(dirname "$0")" && pwd)"
SKILL_SRC="$REPO_DIR/.claude/skills/nbexec/SKILL.md.template"
CLAUDE_DIR="${CLAUDE_CONFIG_DIR:-$HOME/.claude}"
CLAUDE_DIR="${CLAUDE_DIR%/}"
SKILL_DST="$CLAUDE_DIR/skills/nbexec"

# Find nbexec: prefer PATH, fall back to local .venv
if command -v nbexec &>/dev/null; then
    NBEXEC_PATH="$(command -v nbexec)"
elif [ -x "$REPO_DIR/.venv/bin/nbexec" ]; then
    NBEXEC_PATH="$REPO_DIR/.venv/bin/nbexec"
else
    echo "Error: nbexec not found. Install with: pip install claude-nbexec" >&2
    exit 1
fi

mkdir -p "$SKILL_DST"
sed "s|__NBEXEC_PATH__|$NBEXEC_PATH|g" "$SKILL_SRC" > "$SKILL_DST/SKILL.md"
echo "Installed skill to $SKILL_DST/SKILL.md (nbexec path: $NBEXEC_PATH)"
