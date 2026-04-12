#!/bin/bash
# Cold Eyes Reviewer — Stop hook shim
#
# All review logic lives in cold_eyes/ Python package.
# This shell script only handles:
#   - Guard checks (off, recursion, engine exists, git repo)
#   - Atomic lock (mkdir-based)
#   - Hook input parsing (stop_hook_active)
#   - Invoking the Python CLI
#   - Translating CLI JSON to hook decision JSON
#
# Environment variables (resolved by Python engine):
#   COLD_REVIEW_MODE            — block (default), report, off
#   COLD_REVIEW_MODEL           — opus (default), sonnet, haiku
#   COLD_REVIEW_MAX_TOKENS      — token budget for diff (default: 12000)
#   COLD_REVIEW_BLOCK_THRESHOLD — critical (default), major
#   COLD_REVIEW_CONFIDENCE      — minimum confidence to keep: high, medium (default), low
#   COLD_REVIEW_LANGUAGE        — output language (default: 繁體中文（台灣）)
#   COLD_REVIEW_SCOPE           — diff scope: working (default), staged, head, pr-diff
#   COLD_REVIEW_BASE            — base branch for pr-diff scope
#   COLD_REVIEW_OVERRIDE_REASON — reason text when overriding (legacy)

set -uo pipefail

export PYTHONIOENCODING=utf-8

SCRIPTS_DIR="$(cd "$(dirname "$0")" && pwd)"
ENGINE="$SCRIPTS_DIR/cold_eyes/cli.py"
LOCKDIR="$HOME/.claude/.cold-review-lock.d"

MODE="${COLD_REVIEW_MODE:-block}"

# --- Guard: off mode ---
[[ "$MODE" == "off" ]] && exit 0

# --- Guard: prevent recursion ---
[[ "${COLD_REVIEW_ACTIVE:-}" == "1" ]] && exit 0

# --- Resolve Python interpreter ---
PYTHON_CMD=""
for _candidate in python3 python; do
  if command -v "$_candidate" > /dev/null 2>&1; then
    PYTHON_CMD="$_candidate"
    break
  fi
done
if [[ -z "$PYTHON_CMD" ]]; then
  echo "cold-review: python interpreter not found" >&2
  if [[ "$MODE" == "block" ]]; then
    echo '{"decision":"block","reason":"Cold Eyes Review — infrastructure failure: python interpreter not found"}'
  fi
  exit 0
fi

# --- Guard: engine must exist ---
if [[ ! -f "$ENGINE" ]]; then
  echo "cold-review: engine not found at $ENGINE" >&2
  if [[ "$MODE" == "block" ]]; then
    echo '{"decision":"block","reason":"Cold Eyes Review — infrastructure failure: engine not found"}'
  fi
  exit 0
fi

# --- Atomic lock (mkdir-based) ---
acquire_lock() {
  if mkdir "$LOCKDIR" 2>/dev/null; then
    echo $$ > "$LOCKDIR/pid" || { rm -rf "$LOCKDIR"; return 1; }
    return 0
  fi
  # Lock exists — check for stale
  local lock_pid
  lock_pid=$(cat "$LOCKDIR/pid" 2>/dev/null || echo "")
  if [[ -n "$lock_pid" ]] && kill -0 "$lock_pid" 2>/dev/null; then
    return 1  # Active process holds lock
  fi
  # Stale lock — remove and retry once
  rm -rf "$LOCKDIR"
  if mkdir "$LOCKDIR" 2>/dev/null; then
    echo $$ > "$LOCKDIR/pid" || { rm -rf "$LOCKDIR"; return 1; }
    return 0
  fi
  return 1
}

release_lock() {
  rm -rf "$LOCKDIR"
}

if ! acquire_lock; then
  echo "cold-review: skipped (another review in progress)" >&2
  exit 0
fi
trap 'release_lock' EXIT

# --- Read hook input, check stop_hook_active ---
INPUT=$(head -c 1048576)  # 1 MB cap to prevent unbounded reads
# If the hook input JSON has stop_hook_active=true, another stop hook is
# already active (e.g. the agent itself).  Skip to avoid recursion.
# Fallback to "false" on any parse error so we proceed with the review.
STOP_ACTIVE=$(echo "$INPUT" | "$PYTHON_CMD" -c "import json,sys; d=json.load(sys.stdin); print('true' if d.get('stop_hook_active') is True else 'false')" 2>/dev/null || echo "false")
[[ "$STOP_ACTIVE" == "true" ]] && exit 0

# --- Guard: must be in a git repo ---
if ! git rev-parse --git-dir > /dev/null 2>&1; then
  echo "cold-review: skipped (not a git repo)" >&2
  exit 0
fi

# --- Build engine args ---
ENGINE_ARGS=(run)
[[ -n "${COLD_REVIEW_MODE:-}" ]]             && ENGINE_ARGS+=(--mode "$MODE")
[[ -n "${COLD_REVIEW_MODEL:-}" ]]            && ENGINE_ARGS+=(--model "${COLD_REVIEW_MODEL}")
[[ -n "${COLD_REVIEW_MAX_TOKENS:-}" ]]       && ENGINE_ARGS+=(--max-tokens "${COLD_REVIEW_MAX_TOKENS}")
[[ -n "${COLD_REVIEW_BLOCK_THRESHOLD:-}" ]]  && ENGINE_ARGS+=(--threshold "${COLD_REVIEW_BLOCK_THRESHOLD}")
[[ -n "${COLD_REVIEW_CONFIDENCE:-}" ]]       && ENGINE_ARGS+=(--confidence "${COLD_REVIEW_CONFIDENCE}")
[[ -n "${COLD_REVIEW_SCOPE:-}" ]]            && ENGINE_ARGS+=(--scope "${COLD_REVIEW_SCOPE}")
[[ -n "${COLD_REVIEW_LANGUAGE:-}" ]]         && ENGINE_ARGS+=(--language "${COLD_REVIEW_LANGUAGE}")
[[ -n "${COLD_REVIEW_BASE:-}" ]]             && ENGINE_ARGS+=(--base "${COLD_REVIEW_BASE}")
[[ -n "${COLD_REVIEW_OVERRIDE_REASON:-}" ]]  && ENGINE_ARGS+=(--override-reason "${COLD_REVIEW_OVERRIDE_REASON}")

# --- Run engine ---
RESULT=$("$PYTHON_CMD" "$ENGINE" "${ENGINE_ARGS[@]}" 2>/dev/null) || true

# --- Release lock early ---
release_lock
trap - EXIT

# --- Parse result and act (fail-closed) ---
# Any failure to get valid engine output is an infrastructure failure.
# Block mode: emit block decision.  Report mode: warn to stderr only.
echo "$RESULT" | COLD_REVIEW_PARSE_MODE="$MODE" "$PYTHON_CMD" -c "
import json, sys, os

mode = os.environ.get('COLD_REVIEW_PARSE_MODE', 'block')
raw = sys.stdin.read().strip()

def infra_fail(detail):
    msg = f'Cold Eyes Review — infrastructure failure: {detail}'
    print(f'cold-review: infrastructure failure — {detail}', file=sys.stderr)
    if mode == 'block':
        print(json.dumps({'decision': 'block', 'reason': msg}))

if not raw:
    infra_fail('engine produced no output')
    sys.exit(0)

try:
    d = json.loads(raw)
except Exception:
    # Engine may print non-JSON to stdout; try to extract JSON object
    start = raw.find('{')
    end = raw.rfind('}')
    if start >= 0 and end > start:
        try:
            d = json.loads(raw[start:end+1])
        except Exception:
            infra_fail('invalid JSON from engine (extraction failed)')
            sys.exit(0)
    else:
        infra_fail('invalid JSON from engine (no JSON object found)')
        sys.exit(0)

if not isinstance(d, dict) or 'action' not in d:
    infra_fail('malformed engine output (missing action)')
    sys.exit(0)

action = d['action']
display = d.get('display', '')
reason = d.get('reason', '')
print(display, file=sys.stderr)
if action == 'block':
    reason_escaped = json.dumps(reason)
    print('{\"decision\":\"block\",\"reason\":' + reason_escaped + '}')
"

exit 0
