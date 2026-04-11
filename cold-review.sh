#!/bin/bash
# Cold Eyes Reviewer — Stop hook script (thin orchestrator)
#
# Guards run here (fast, no Python overhead for trivial skips).
# All review logic lives in cold_review_engine.py.
#
# Environment variables:
#   COLD_REVIEW_MODE            — block (default), report, off
#   COLD_REVIEW_MODEL           — opus (default), sonnet, haiku
#   COLD_REVIEW_MAX_TOKENS      — token budget for diff (default: 12000)
#   COLD_REVIEW_MAX_LINES       — backward compat: converted to tokens via ×4
#   COLD_REVIEW_BLOCK_THRESHOLD — critical (default), major
#   COLD_REVIEW_CONFIDENCE      — minimum confidence to keep: high, medium (default), low
#   COLD_REVIEW_LANGUAGE        — output language (default: 繁體中文（台灣）)
#   COLD_REVIEW_SCOPE           — diff scope: working (default), staged, head
#   COLD_REVIEW_ALLOW_ONCE      — set to 1 to bypass block once (logged)
#   COLD_REVIEW_OVERRIDE_REASON — reason text when overriding with ALLOW_ONCE

set -uo pipefail

export PYTHONIOENCODING=utf-8

SCRIPTS_DIR="$(cd "$(dirname "$0")" && pwd)"
HELPER="$SCRIPTS_DIR/cold_eyes/helper.py"
ENGINE="$SCRIPTS_DIR/cold_eyes/cli.py"
LOCKFILE="$HOME/.claude/.cold-review-lock"

MODE="${COLD_REVIEW_MODE:-block}"
MODEL="${COLD_REVIEW_MODEL:-opus}"
OVERRIDE_REASON="${COLD_REVIEW_OVERRIDE_REASON:-}"

# Token budget: prefer MAX_TOKENS, fallback to MAX_LINES×4
# Always computed here for backward compat (MAX_LINES conversion)
if [[ -n "${COLD_REVIEW_MAX_LINES:-}" ]]; then
  MAX_TOKENS=$((COLD_REVIEW_MAX_LINES * 4))
elif [[ -n "${COLD_REVIEW_MAX_TOKENS:-}" ]]; then
  MAX_TOKENS="$COLD_REVIEW_MAX_TOKENS"
else
  MAX_TOKENS=""
fi

# --- Helper: log guard-level skips to history ---
log_state() {
  local state="$1"
  local reason="${2:-}"
  python "$HELPER" log-state "$(pwd)" "$MODE" "$MODEL" "$state" "$reason" 2>/dev/null || true
}

# --- Guard: off mode (no logging — off means off) ---
[[ "$MODE" == "off" ]] && exit 0

# --- Guard: prevent recursion (no logging — internal mechanism) ---
[[ "${COLD_REVIEW_ACTIVE:-}" == "1" ]] && exit 0

# --- Guard: engine must exist ---
if [[ ! -f "$ENGINE" ]]; then
  echo "cold-review: engine not found at $ENGINE" >&2
  log_state "failed" "engine not found"
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
    rm -f "$LOCKFILE"
  fi
fi

# --- Read hook input, check stop_hook_active ---
INPUT=$(cat)
STOP_ACTIVE=$(echo "$INPUT" | python "$HELPER" parse-hook 2>/dev/null)
[[ "$STOP_ACTIVE" == "true" ]] && exit 0

# --- Guard: must be in a git repo ---
if ! git rev-parse --git-dir > /dev/null 2>&1; then
  echo "cold-review: skipped (not a git repo)" >&2
  log_state "skipped" "not a git repo"
  exit 0
fi

# --- Acquire lock ---
echo $$ > "$LOCKFILE"
trap 'rm -f "$LOCKFILE"' EXIT

# --- Run engine ---
# Only pass flags for explicitly-set env vars; engine resolves
# unset values via policy file → hardcoded defaults.
ENGINE_ARGS=(run)
[[ -n "${COLD_REVIEW_MODE+x}" ]]            && ENGINE_ARGS+=(--mode "$MODE")
[[ -n "${COLD_REVIEW_MODEL+x}" ]]           && ENGINE_ARGS+=(--model "${COLD_REVIEW_MODEL}")
[[ -n "$MAX_TOKENS" ]]                      && ENGINE_ARGS+=(--max-tokens "$MAX_TOKENS")
[[ -n "${COLD_REVIEW_BLOCK_THRESHOLD+x}" ]] && ENGINE_ARGS+=(--threshold "${COLD_REVIEW_BLOCK_THRESHOLD}")
[[ -n "${COLD_REVIEW_CONFIDENCE+x}" ]]      && ENGINE_ARGS+=(--confidence "${COLD_REVIEW_CONFIDENCE}")
[[ -n "${COLD_REVIEW_SCOPE+x}" ]]           && ENGINE_ARGS+=(--scope "${COLD_REVIEW_SCOPE}")
[[ -n "${COLD_REVIEW_LANGUAGE:-}" ]]         && ENGINE_ARGS+=(--language "${COLD_REVIEW_LANGUAGE}")
[[ -n "$OVERRIDE_REASON" ]]                  && ENGINE_ARGS+=(--override-reason "$OVERRIDE_REASON")
RESULT=$(python "$ENGINE" "${ENGINE_ARGS[@]}" 2>&2) || true

# --- Release lock early ---
rm -f "$LOCKFILE"
trap - EXIT

# --- Handle engine failure ---
if [[ -z "$RESULT" ]]; then
  echo "cold-review: engine returned no output" >&2
  log_state "failed" "engine no output"
  exit 0
fi

# --- Parse result and act ---
echo "$RESULT" | python -c "
import json, sys
d = json.load(sys.stdin)
action = d.get('action', 'pass')
display = d.get('display', '')
reason = d.get('reason', '')
print(display, file=sys.stderr)
if action == 'block':
    reason_escaped = json.dumps(reason)
    print('{\"decision\":\"block\",\"reason\":' + reason_escaped + '}')
"

exit 0
