#!/bin/bash
# Install Cold Eyes Reviewer to ~/.claude/scripts/
set -euo pipefail

SCRIPTS_DIR="$HOME/.claude/scripts"
SRC_DIR="$(cd "$(dirname "$0")" && pwd)"

echo "Cold Eyes Reviewer — install"
echo "Source:  $SRC_DIR"
echo "Target:  $SCRIPTS_DIR"
echo ""

mkdir -p "$SCRIPTS_DIR/cold_eyes"

# Copy shell shim + prompt template
cp "$SRC_DIR/cold-review.sh" "$SCRIPTS_DIR/"
cp "$SRC_DIR/cold-review-prompt.txt" "$SCRIPTS_DIR/"
cp "$SRC_DIR/cold-review-prompt-shallow.txt" "$SCRIPTS_DIR/"

# Copy Python package — top-level modules
cp "$SRC_DIR"/cold_eyes/*.py "$SCRIPTS_DIR/cold_eyes/"

# Copy v2 sub-packages
for pkg in session contract gates retry noise runner; do
  mkdir -p "$SCRIPTS_DIR/cold_eyes/$pkg"
  cp "$SRC_DIR"/cold_eyes/$pkg/*.py "$SCRIPTS_DIR/cold_eyes/$pkg/"
done

# Verify
echo "Verifying installation..."
python "$SCRIPTS_DIR/cold_eyes/cli.py" doctor

echo ""
echo "Done. Add the Stop hook to ~/.claude/settings.json if not already present:"
echo '  "hooks": { "Stop": [{ "type": "command", "command": "bash ~/.claude/scripts/cold-review.sh" }] }'
