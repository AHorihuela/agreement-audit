#!/usr/bin/env bash
# Install /agreement-audit GLOBALLY so it works in any Claude Code or Cowork session, from any folder.
#
# It copies the skill (with its bundled scripts) to ~/.claude/skills/ and the script-free workflow to
# ~/.claude/workflows/ (which Claude Code discovers by name in every session), then installs the Python
# deps the local parser + grounding gate + Word report need. Re-run any time to update.
set -euo pipefail

SRC="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SKILL_DST="$HOME/.claude/skills/agreement-audit"
WF_DST="$HOME/.claude/workflows"

echo "Installing the agreement-audit skill globally…"

# Skill (SKILL.md + bundled scripts/). The scripts self-locate via ${CLAUDE_SKILL_DIR} at runtime.
rm -rf "$SKILL_DST"
mkdir -p "$SKILL_DST"
cp -R "$SRC/.claude/skills/agreement-audit/." "$SKILL_DST/"
find "$SKILL_DST" -name "__pycache__" -type d -prune -exec rm -rf {} + 2>/dev/null || true

# Workflow — script-free, so it runs from any cwd. ~/.claude/workflows/ is name-discovered everywhere.
mkdir -p "$WF_DST"
cp "$SRC/.claude/workflows/agreement-audit.js" "$WF_DST/agreement-audit.js"

# Python deps (parser + grounding gate + Word report) — into a venv BUNDLED WITH THE SKILL. Modern
# system Pythons (Homebrew/Debian, PEP 668 "externally managed") refuse bare `pip install`, which used
# to leave a fresh global install broken. The skill prefers this venv at runtime and falls back to
# `python3` only if it's absent.
VENV="$SKILL_DST/.venv"
if python3 -m venv "$VENV" && "$VENV/bin/python" -m pip install --quiet --upgrade pip python-docx PyMuPDF; then
  echo "  deps installed into bundled venv ($VENV)"
else
  rm -rf "$VENV"
  if python3 -m pip install --quiet --upgrade python-docx PyMuPDF 2>/dev/null; then
    echo "  deps installed into python3 (no venv available)"
  else
    echo "  ⚠ could not install deps — create a venv and install python-docx + PyMuPDF, e.g.:"
    echo "      python3 -m venv \"$VENV\" && \"$VENV/bin/pip\" install python-docx PyMuPDF"
  fi
fi

echo "Done. Open Claude Code or Cowork in ANY folder and run:  /agreement-audit"
echo "  skill    -> $SKILL_DST"
echo "  workflow -> $WF_DST/agreement-audit.js"
