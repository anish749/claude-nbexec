#!/usr/bin/env bash
set -euo pipefail

REPO_DIR="$(cd "$(dirname "$0")" && pwd)"
NBEXEC_PATH="$REPO_DIR/.venv/bin/nbexec"
SKILL_SRC="$REPO_DIR/.claude/skills/nbexec/SKILL.md.template"
CLAUDE_DIR="${CLAUDE_CONFIG_DIR:-$HOME/.claude}"
CLAUDE_DIR="${CLAUDE_DIR%/}"
SKILL_DST="$CLAUDE_DIR/skills/nbexec"

mkdir -p "$SKILL_DST"
sed "s|__NBEXEC_PATH__|$NBEXEC_PATH|g" "$SKILL_SRC" > "$SKILL_DST/SKILL.md"
echo "Installed skill to $SKILL_DST/SKILL.md (nbexec path: $NBEXEC_PATH)"
