"""Shell-facing utilities — only commands actually called by cold-review.sh."""

import os
import sys

# Allow direct invocation: python cold_eyes/helper.py
_pkg = os.path.dirname(os.path.abspath(__file__))
_root = os.path.dirname(_pkg)
if _root not in sys.path:
    sys.path.insert(0, _root)

import json

from cold_eyes.history import log_to_history


def parse_hook():
    """Read hook JSON from stdin, print 'true' if stop_hook_active."""
    try:
        data = json.load(sys.stdin)
        if data.get("stop_hook_active"):
            print("true")
        else:
            print("false")
    except Exception:
        print("false")


def log_state_from_shell():
    """Log a non-review state to history. Args: <cwd> <mode> <model> <state> [reason] [override_reason]"""
    cwd = sys.argv[2]
    mode = sys.argv[3]
    model = sys.argv[4]
    state = sys.argv[5]
    reason = sys.argv[6] if len(sys.argv) > 6 else ""
    override_reason = sys.argv[7] if len(sys.argv) > 7 else ""

    log_to_history(cwd, mode, model, state, reason=reason,
                   override_reason=override_reason)


COMMANDS = {
    "parse-hook": parse_hook,
    "log-state": log_state_from_shell,
}


if __name__ == "__main__":
    if len(sys.argv) < 2 or sys.argv[1] not in COMMANDS:
        print(f"Usage: {sys.argv[0]} <{'|'.join(COMMANDS)}>", file=sys.stderr)
        sys.exit(1)
    COMMANDS[sys.argv[1]]()
