#!/bin/bash
# Uninstall Cold Eyes Reviewer from ~/.claude/scripts/
set -euo pipefail

SCRIPTS_DIR="$HOME/.claude/scripts"
if [[ -n "${WSL_INTEROP:-}" ]] && command -v cmd.exe >/dev/null 2>&1 && command -v wslpath >/dev/null 2>&1; then
  WIN_HOME="$(cmd.exe /c "echo %USERPROFILE%" 2>/dev/null | tr -d '\r')"
  if [[ -n "$WIN_HOME" ]]; then
    WIN_HOME_UNIX="$(wslpath "$WIN_HOME" 2>/dev/null || true)"
    if [[ -n "$WIN_HOME_UNIX" ]]; then
      SCRIPTS_DIR="$WIN_HOME_UNIX/.claude/scripts"
    fi
  fi
fi

echo "Cold Eyes Reviewer — uninstall"
echo "Removing from: $SCRIPTS_DIR"
echo ""

if [[ -f "$SCRIPTS_DIR/cold_eyes/cli.py" ]]; then
  if command -v python >/dev/null 2>&1; then
    python "$SCRIPTS_DIR/cold_eyes/cli.py" remove-health-schedule --scripts-dir "$SCRIPTS_DIR" >/dev/null 2>&1 || true
  elif command -v python3 >/dev/null 2>&1; then
    python3 "$SCRIPTS_DIR/cold_eyes/cli.py" remove-health-schedule --scripts-dir "$SCRIPTS_DIR" >/dev/null 2>&1 || true
  fi
fi

rm -f "$SCRIPTS_DIR/cold-review.sh"
rm -f "$SCRIPTS_DIR/cold-review-prompt.txt"
rm -f "$SCRIPTS_DIR/cold-review-prompt-shallow.txt"
rm -f "$SCRIPTS_DIR/cold-review-health-notice.cmd"
rm -rf "$SCRIPTS_DIR/cold_eyes"

echo "Done. Remember to remove the Stop hook from ~/.claude/settings.json if present."
