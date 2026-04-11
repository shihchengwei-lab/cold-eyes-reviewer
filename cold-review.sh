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

# --- Guard: prevent recursion (env var) ---
if [[ "${COLD_REVIEW_ACTIVE:-}" == "1" ]]; then
  exit 0
fi

# --- Guard: lockfile with stale detection ---
if [[ -f "$LOCKFILE" ]]; then
  LOCK_PID=$(head -1 "$LOCKFILE" 2>/dev/null || echo "")
  if [[ -n "$LOCK_PID" ]] && kill -0 "$LOCK_PID" 2>/dev/null; then
    echo "cold-review: skipped (another review in progress, pid=$LOCK_PID)" >&2
    exit 0
  else
    echo "cold-review: removing stale lockfile (pid=$LOCK_PID no longer alive)" >&2
    rm -f "$LOCKFILE"
  fi
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

# --- Collect diff (truncate at pipe level to avoid large shell variables) ---
DIFF=""
STAGED=$(git diff --cached 2>/dev/null | head -n "$MAX_LINES" || true)
DIFF+="$STAGED"

REMAINING=$((MAX_LINES - $(echo "$STAGED" | wc -l)))
if [[ "$REMAINING" -gt 0 ]]; then
  UNSTAGED=$(git diff 2>/dev/null | head -n "$REMAINING" || true)
  DIFF+=$'\n'"$UNSTAGED"
  REMAINING=$((REMAINING - $(echo "$UNSTAGED" | wc -l)))
fi

# Include content of new untracked files (within line budget)
if [[ "$REMAINING" -gt 0 ]]; then
  UNTRACKED=$(git ls-files --others --exclude-standard 2>/dev/null || true)
  if [[ -n "$UNTRACKED" ]]; then
    while IFS= read -r f; do
      if [[ -f "$f" ]] && [[ "$REMAINING" -gt 0 ]]; then
        CONTENT=$(cat "$f" 2>/dev/null | head -n "$REMAINING" || true)
        CONTENT_LINES=$(echo "$CONTENT" | wc -l)
        DIFF+=$'\n'"=== NEW FILE: $f ==="$'\n'"$CONTENT"$'\n'
        REMAINING=$((REMAINING - CONTENT_LINES - 2))
      fi
    done <<< "$UNTRACKED"
  fi
fi

# Check if we hit the limit
TOTAL_LINES=$(echo "$DIFF" | wc -l)
if [[ "$TOTAL_LINES" -ge "$MAX_LINES" ]]; then
  DIFF+=$'\n\n'"[Cold Eyes: diff truncated at ~$MAX_LINES lines. Review may be incomplete.]"
  echo "cold-review: diff truncated at $MAX_LINES lines" >&2
fi

# --- Guard: no changes ---
if [[ -z "${DIFF// /}" ]]; then
  echo "cold-review: skipped (no changes)" >&2
  exit 0
fi

# --- Build prompt to temp file ---
TMPFILE=$(mktemp)
trap 'rm -f "$TMPFILE"' EXIT
python "$HELPER" build-prompt > "$TMPFILE"

# --- Acquire lock (after tmpfile, so trap order is clean) ---
echo $$ > "$LOCKFILE"
trap 'rm -f "$TMPFILE" "$LOCKFILE"' EXIT

# --- Run reviewer ---
export COLD_REVIEW_ACTIVE=1
REVIEW_EXIT=0
REVIEW_RAW=$(echo "$DIFF" | claude -p "Review the following changes." \
  --model "$MODEL" \
  --append-system-prompt-file "$TMPFILE" \
  --output-format json 2>/dev/null) || REVIEW_EXIT=$?
unset COLD_REVIEW_ACTIVE

# --- Release lock early (trap also handles this) ---
rm -f "$LOCKFILE"
trap 'rm -f "$TMPFILE"' EXIT

# --- Handle claude CLI errors ---
if [[ "$REVIEW_EXIT" -ne 0 ]]; then
  echo "cold-review: claude exited with code $REVIEW_EXIT" >&2
  exit 0
fi

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
