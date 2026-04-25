#!/bin/bash
# Install Cold Eyes Reviewer to ~/.claude/scripts/
set -euo pipefail

SRC_DIR="$(cd "$(dirname "$0")" && pwd)"
SCRIPTS_DIR="$HOME/.claude/scripts"
SETTINGS_PATH="$HOME/.claude/settings.json"
if [[ -n "${WSL_INTEROP:-}" ]] && command -v cmd.exe >/dev/null 2>&1 && command -v wslpath >/dev/null 2>&1; then
  WIN_HOME="$(cmd.exe /c "echo %USERPROFILE%" 2>/dev/null | tr -d '\r')"
  if [[ -n "$WIN_HOME" ]]; then
    WIN_HOME_UNIX="$(wslpath "$WIN_HOME" 2>/dev/null || true)"
    if [[ -n "$WIN_HOME_UNIX" ]]; then
      SCRIPTS_DIR="$WIN_HOME_UNIX/.claude/scripts"
      SETTINGS_PATH="$WIN_HOME_UNIX/.claude/settings.json"
    fi
  fi
fi
PYTHON_CMD="${PYTHON:-}"
if [[ -z "$PYTHON_CMD" ]]; then
  if command -v python >/dev/null 2>&1; then
    PYTHON_CMD="python"
  elif command -v python3 >/dev/null 2>&1; then
    PYTHON_CMD="python3"
  else
    echo "python or python3 is required for install verification" >&2
    exit 1
  fi
fi

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

# Copy support packages used by unified local checks
for pkg in gates; do
  mkdir -p "$SCRIPTS_DIR/cold_eyes/$pkg"
  cp "$SRC_DIR"/cold_eyes/$pkg/*.py "$SCRIPTS_DIR/cold_eyes/$pkg/"
done

# Remove retired v2-only packages from previous installs.
for pkg in session contract retry noise runner; do
  rm -rf "$SCRIPTS_DIR/cold_eyes/$pkg"
done

# Create/update the low-noise Agent health notice schedule by default.
# Override with:
#   COLD_REVIEW_HEALTH_SCHEDULE=off
#   COLD_REVIEW_HEALTH_INTERVAL_DAYS=14
#   COLD_REVIEW_HEALTH_TIME=09:00
if [[ "${COLD_REVIEW_HEALTH_SCHEDULE:-on}" != "off" ]]; then
  echo "Configuring Agent health notice schedule..."
  "$PYTHON_CMD" "$SCRIPTS_DIR/cold_eyes/cli.py" install-health-schedule \
    --repo-root "$SRC_DIR" \
    --scripts-dir "$SCRIPTS_DIR" \
    --every-days "${COLD_REVIEW_HEALTH_INTERVAL_DAYS:-7}" \
    --time "${COLD_REVIEW_HEALTH_TIME:-09:00}" || true
  echo ""
fi

# Verify
echo "Verifying installation..."
"$PYTHON_CMD" - "$SCRIPTS_DIR" "$SETTINGS_PATH" <<'PY'
import json
import sys

scripts_dir = sys.argv[1]
settings_path = sys.argv[2]
sys.path.insert(0, scripts_dir)

from cold_eyes.doctor import run_doctor

print(json.dumps(
    run_doctor(scripts_dir=scripts_dir, settings_path=settings_path),
    ensure_ascii=False,
))
PY

echo ""
echo "Done. Add the Stop hook to ~/.claude/settings.json if not already present:"
echo '  "hooks": { "Stop": [{ "type": "command", "command": "bash ~/.claude/scripts/cold-review.sh" }] }'
