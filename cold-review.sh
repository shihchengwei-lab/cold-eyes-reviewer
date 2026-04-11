#!/bin/bash
# Cold Eyes Reviewer — Stop hook script
#
# Environment variables:
#   COLD_REVIEW_MODE  — block (default), report, off
#   COLD_REVIEW_MODEL — opus (default), sonnet, haiku

set -uo pipefail

export PYTHONIOENCODING=utf-8

SCRIPTS_DIR="$(cd "$(dirname "$0")" && pwd)"
HELPER="$SCRIPTS_DIR/cold-review-helper.py"

MODE="${COLD_REVIEW_MODE:-block}"
MODEL="${COLD_REVIEW_MODEL:-opus}"

# --- Guard: off mode ---
[[ "$MODE" == "off" ]] && exit 0

# --- Guard: prevent recursion (reviewer's own claude -p would trigger this hook) ---
[[ "${COLD_REVIEW_ACTIVE:-}" == "1" ]] && exit 0

# --- Read hook input, check stop_hook_active ---
INPUT=$(cat)
STOP_ACTIVE=$(echo "$INPUT" | python "$HELPER" parse-hook)
[[ "$STOP_ACTIVE" == "true" ]] && exit 0

# --- Guard: must be in a git repo ---
git rev-parse --git-dir > /dev/null 2>&1 || exit 0

# --- Collect diff ---
DIFF=""
DIFF+=$(git diff --cached 2>/dev/null || true)
DIFF+=$'\n'
DIFF+=$(git diff 2>/dev/null || true)

# Include content of new untracked files
UNTRACKED=$(git ls-files --others --exclude-standard 2>/dev/null || true)
if [[ -n "$UNTRACKED" ]]; then
  while IFS= read -r f; do
    if [[ -f "$f" ]]; then
      DIFF+="
=== NEW FILE: $f ===
$(cat "$f" 2>/dev/null || true)
"
    fi
  done <<< "$UNTRACKED"
fi

# --- Guard: no changes ---
if [[ -z "${DIFF// /}" ]]; then
  exit 0
fi

# --- Build prompt ---
PROMPT=$(python "$HELPER" build-prompt)

# --- Run reviewer ---
# COLD_REVIEW_ACTIVE=1 prevents this hook from firing again inside the reviewer's session
export COLD_REVIEW_ACTIVE=1
REVIEW_RAW=$(echo "$DIFF" | claude -p "Review the following changes." \
  --model "$MODEL" \
  --append-system-prompt "$PROMPT" \
  --output-format json 2>/dev/null) || true
unset COLD_REVIEW_ACTIVE

if [[ -z "$REVIEW_RAW" ]]; then
  exit 0
fi

# --- Parse review output ---
PARSED=$(echo "$REVIEW_RAW" | python "$HELPER" parse-review)
PASS=$(echo "$PARSED" | python "$HELPER" check-pass)

# --- Log to history (both modes) ---
echo "$PARSED" | python "$HELPER" log-review "$(pwd)" "$MODE" "$MODEL" 2>/dev/null || true

# --- Act based on mode ---
if [[ "$MODE" == "report" ]]; then
  exit 0
fi

# --- Block mode: if issues found, block ---
if [[ "$PASS" == "false" ]]; then
  REASON=$(echo "$PARSED" | python "$HELPER" format-block)
  REASON_ESCAPED=$(python -c "import json,sys; print(json.dumps(sys.argv[1]))" "$REASON")
  echo "{\"decision\":\"block\",\"reason\":$REASON_ESCAPED}"
  exit 0
fi

exit 0
