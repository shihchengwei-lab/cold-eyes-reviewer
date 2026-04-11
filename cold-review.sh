#!/bin/bash
# Cold Eyes Reviewer — Stop hook script
#
# Environment variables:
#   COLD_REVIEW_MODE            — block (default), report, off
#   COLD_REVIEW_MODEL           — opus (default), sonnet, haiku
#   COLD_REVIEW_MAX_LINES       — max diff lines to review (default: 500)
#   COLD_REVIEW_BLOCK_THRESHOLD — critical (default), major
#   COLD_REVIEW_ALLOW_ONCE      — set to 1 to skip block once (logged as override)

set -uo pipefail

export PYTHONIOENCODING=utf-8

SCRIPTS_DIR="$(cd "$(dirname "$0")" && pwd)"
HELPER="$SCRIPTS_DIR/cold-review-helper.py"
LOCKFILE="$HOME/.claude/.cold-review-lock"

MODE="${COLD_REVIEW_MODE:-block}"
MODEL="${COLD_REVIEW_MODEL:-opus}"
MAX_LINES="${COLD_REVIEW_MAX_LINES:-500}"
THRESHOLD="${COLD_REVIEW_BLOCK_THRESHOLD:-critical}"

# --- Helper: log state to history ---
log_state() {
  local state="$1"
  local reason="${2:-}"
  python "$HELPER" log-state "$(pwd)" "$MODE" "$MODEL" "$state" "$reason" 2>/dev/null || true
}

# --- Guard: off mode (no logging — off means off) ---
[[ "$MODE" == "off" ]] && exit 0

# --- Guard: prevent recursion (no logging — internal mechanism) ---
if [[ "${COLD_REVIEW_ACTIVE:-}" == "1" ]]; then
  exit 0
fi

# --- Guard: lockfile with stale detection ---
if [[ -f "$LOCKFILE" ]]; then
  LOCK_PID=$(head -1 "$LOCKFILE" 2>/dev/null || echo "")
  if [[ -n "$LOCK_PID" ]] && kill -0 "$LOCK_PID" 2>/dev/null; then
    echo "cold-review: skipped (another review in progress, pid=$LOCK_PID)" >&2
    log_state "skipped" "another review in progress"
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
  log_state "skipped" "not a git repo"
  exit 0
fi

# --- Collect file lists ---
REPO_ROOT=$(git rev-parse --show-toplevel 2>/dev/null)
IGNORE_FILE="$REPO_ROOT/.cold-review-ignore"
UNTRACKED_TMP=$(mktemp)

STAGED_FILES=$(git diff --cached --name-only 2>/dev/null || true)
UNSTAGED_FILES=$(git diff --name-only 2>/dev/null || true)
UNTRACKED_FILES=$(git ls-files --others --exclude-standard 2>/dev/null || true)

# Save untracked list for rank-files to use
echo "$UNTRACKED_FILES" > "$UNTRACKED_TMP"

# Merge, deduplicate, filter ignore patterns, then rank by risk
ALL_FILES=$(printf '%s\n%s\n%s' "$STAGED_FILES" "$UNSTAGED_FILES" "$UNTRACKED_FILES" | sort -u | grep -v '^$' || true)

if [[ -z "$ALL_FILES" ]]; then
  rm -f "$UNTRACKED_TMP"
  echo "cold-review: skipped (no changes)" >&2
  log_state "skipped" "no changes"
  exit 0
fi

FILTERED=$(echo "$ALL_FILES" | python "$HELPER" filter-files "$IGNORE_FILE")
if [[ -z "$FILTERED" ]]; then
  rm -f "$UNTRACKED_TMP"
  echo "cold-review: skipped (all files ignored)" >&2
  log_state "skipped" "all files ignored"
  exit 0
fi

RANKED=$(echo "$FILTERED" | python "$HELPER" rank-files "$UNTRACKED_TMP")
rm -f "$UNTRACKED_TMP"

# --- Collect diffs per file, respecting line budget ---
DIFF=""
REMAINING="$MAX_LINES"
TRUNCATED=false
SKIPPED_FILES=""
FILE_COUNT=0

while IFS= read -r f; do
  [[ -z "$f" ]] && continue

  if [[ "$REMAINING" -le 0 ]]; then
    SKIPPED_FILES+="  $f"$'\n'
    continue
  fi

  FILE_COUNT=$((FILE_COUNT + 1))
  CHUNK=""

  if echo "$UNTRACKED_FILES" | grep -qx "$f"; then
    # New untracked file — show content
    CONTENT=$(cat "$f" 2>/dev/null | head -n "$REMAINING" || true)
    CHUNK="=== NEW FILE: $f ==="$'\n'"$CONTENT"
  else
    # Tracked file — show diff (staged + unstaged)
    STAGED_DIFF=$(git diff --cached -- "$f" 2>/dev/null || true)
    UNSTAGED_DIFF=$(git diff -- "$f" 2>/dev/null || true)
    CHUNK=$(printf '%s\n%s' "$STAGED_DIFF" "$UNSTAGED_DIFF" | head -n "$REMAINING")
  fi

  CHUNK_LINES=$(echo "$CHUNK" | wc -l)
  DIFF+=$'\n'"$CHUNK"
  REMAINING=$((REMAINING - CHUNK_LINES))
done <<< "$RANKED"

# Append truncation notice if budget was exceeded
if [[ -n "$SKIPPED_FILES" ]]; then
  TRUNCATED=true
  DIFF+=$'\n\n'"[Cold Eyes: diff truncated at ~$MAX_LINES lines. Skipped files:"$'\n'"$SKIPPED_FILES]"
  echo "cold-review: diff truncated at $MAX_LINES lines" >&2
fi

# --- Guard: no changes ---
if [[ -z "${DIFF// /}" ]]; then
  echo "cold-review: skipped (no changes)" >&2
  log_state "skipped" "no changes"
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
  log_state "failed" "claude exit $REVIEW_EXIT"
  exit 0
fi

if [[ -z "$REVIEW_RAW" ]]; then
  echo "cold-review: reviewer returned empty output" >&2
  log_state "failed" "empty output"
  exit 0
fi

# --- Parse review output ---
PARSED=$(echo "$REVIEW_RAW" | python "$HELPER" parse-review)
PASS=$(echo "$PARSED" | python "$HELPER" check-pass)

# --- Compute diff stats for history ---
DIFF_LINE_COUNT=$(echo "$DIFF" | wc -l)

# --- Helper: log review with determined state ---
log_review() {
  local state="$1"
  echo "$PARSED" | python "$HELPER" log-review "$(pwd)" "$MODE" "$MODEL" "$state" "$FILE_COUNT" "$DIFF_LINE_COUNT" "$TRUNCATED" 2>/dev/null || true
}

# --- Determine state and act ---
if [[ "$MODE" == "report" ]]; then
  if [[ "$PASS" == "false" ]]; then
    log_review "reported"
  else
    log_review "passed"
  fi
  echo "cold-review: report logged (pass=$PASS)" >&2
  exit 0
fi

# --- Block mode: check threshold ---
SHOULD_BLOCK=$(echo "$PARSED" | python "$HELPER" should-block "$THRESHOLD")

if [[ "$SHOULD_BLOCK" == "true" ]]; then
  # --- Override: ALLOW_ONCE skips the block but still logs ---
  if [[ "${COLD_REVIEW_ALLOW_ONCE:-}" == "1" ]]; then
    log_review "overridden"
    echo "cold-review: override — block skipped (ALLOW_ONCE)" >&2
    exit 0
  fi

  log_review "blocked"
  REASON=$(echo "$PARSED" | python "$HELPER" format-block)
  REASON_ESCAPED=$(python -c "import json,sys; print(json.dumps(sys.argv[1]))" "$REASON")
  echo "cold-review: blocking (issues at or above $THRESHOLD)" >&2
  echo "{\"decision\":\"block\",\"reason\":$REASON_ESCAPED}"
  exit 0
fi

log_review "passed"
echo "cold-review: pass" >&2
exit 0
