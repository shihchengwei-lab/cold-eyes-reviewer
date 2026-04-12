#!/bin/bash
# Uninstall Cold Eyes Reviewer from ~/.claude/scripts/
set -euo pipefail

SCRIPTS_DIR="$HOME/.claude/scripts"

echo "Cold Eyes Reviewer — uninstall"
echo "Removing from: $SCRIPTS_DIR"
echo ""

rm -f "$SCRIPTS_DIR/cold-review.sh"
rm -f "$SCRIPTS_DIR/cold-review-prompt.txt"
rm -f "$SCRIPTS_DIR/cold-review-prompt-shallow.txt"
rm -rf "$SCRIPTS_DIR/cold_eyes"

echo "Done. Remember to remove the Stop hook from ~/.claude/settings.json if present."
