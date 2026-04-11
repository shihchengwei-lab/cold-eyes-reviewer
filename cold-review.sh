#!/bin/bash
# Cold Eyes Reviewer — Stop hook script
#
# Environment variables:
#   COLD_REVIEW_MODE      — block (default), report, off
#   COLD_REVIEW_MODEL     — opus (default), sonnet, haiku
#   COLD_REVIEW_MAX_LINES — max diff lines to review (default: 500)

set -uo pipefail

export PYTHONIOENCODING=utf-8

SCRIPTS_DIR="$(cd "$(dirname "$0")" && pwd)"
HELPER="$SCRIPTS_DIR/cold-review-helper.py"
LOCKFILE="$HOME/.claude/.cold-review-lock"

MODE="${COLD_REVIEW_MODE:-block}"
MODEL="${COLD_REVIEW_MODEL:-opus}"
MAX_LINES="${COLD_REVIEW_MAX_LINES:-500}"

# --- Guard: off mode ---
[[ "$MODE" == "off" ]] && exit 0

# --- Guard: prevent recursion (env var from parent + lockfile as backup) ---
if [[ "${COLD_REVIEW_ACTIVE:-}" == "1" ]]; then
  exit 0
fi
if [[ -f "$LOCKFILE" ]]; then
  echo "cold-review: skipped (lockfile exists, another review in progress)" >&2
  exit 0
fi

# --- Read hook input, check stop_hook_active ---
INPUT=$(cat)
STOP_ACTIVE=$(echo "$INPUT" | python "$HELPER" parse-hook)
if [[ "$STOP_ACTIVE" == "true" ]]; then
  echo "cold-review: skipped (stop_hook_active, revision pass)" >&2
  exit 0
fi

# --- Guard: must be in a git repo ---
if ! git rev-parse --git-dir > /dev/null 2>&1; then
  echo "cold-review: skipped (not a git repo)" >&2
  exit 0
fi

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
      DIFF+=$'\n'"=== NEW FILE: $f ==="$'\n'
      DIFF+=$(cat "$f" 2>/dev/null || true)
    fi
  done <<< "$UNTRACKED"
fi

# --- Guard: no changes ---
if [[ -z "${DIFF// /}" ]]; then
  echo "cold-review: skipped (no changes)" >&2
  exit 0
fi

# --- Truncate large diffs ---
LINE_COUNT=$(echo "$DIFF" | wc -l)
if [[ "$LINE_COUNT" -gt "$MAX_LINES" ]]; then
  DIFF=$(echo "$DIFF" | head -n "$MAX_LINES")
  DIFF+=$'\n\n'"[Cold Eyes: diff truncated at $MAX_LINES lines out of $LINE_COUNT. Review may be incomplete.]"
  echo "cold-review: diff truncated from $LINE_COUNT to $MAX_LINES lines" >&2
fi

# --- Build prompt to temp file (avoids shell interpretation of special chars) ---
TMPFILE=$(mktemp)
trap 'rm -f "$TMPFILE" "$LOCKFILE"' EXIT
python "$HELPER" build-prompt > "$TMPFILE"

# --- Acquire lock ---
echo $$ > "$LOCKFILE"

# --- Run reviewer ---
export COLD_REVIEW_ACTIVE=1
REVIEW_RAW=$(echo "$DIFF" | claude -p "Review the following changes." \
  --model "$MODEL" \
  --append-system-prompt-file "$TMPFILE" \
  --output-format json 2>/dev/null) || true
unset COLD_REVIEW_ACTIVE

# --- Release lock (trap also handles this) ---
rm -f "$LOCKFILE"

if [[ -z "$REVIEW_RAW" ]]; then
  echo "cold-review: reviewer returned empty output" >&2
  exit 0
fi

# --- Parse review output ---
PARSED=$(echo "$REVIEW_RAW" | python "$HELPER" parse-review)
PASS=$(echo "$PARSED" | python "$HELPER" check-pass)

# --- Log to history (both modes) ---
echo "$PARSED" | python "$HELPER" log-review "$(pwd)" "$MODE" "$MODEL" 2>/dev/null || true

# --- Act based on mode ---
if [[ "$MODE" == "report" ]]; then
  echo "cold-review: report logged (pass=$PASS)" >&2
  exit 0
fi

# --- Block mode: if issues found, block ---
if [[ "$PASS" == "false" ]]; then
  REASON=$(echo "$PARSED" | python "$HELPER" format-block)
  REASON_ESCAPED=$(python -c "import json,sys; print(json.dumps(sys.argv[1]))" "$REASON")
  echo "cold-review: blocking (issues found)" >&2
  echo "{\"decision\":\"block\",\"reason\":$REASON_ESCAPED}"
  exit 0
fi

echo "cold-review: pass" >&2
exit 0
