"""Cold Eyes Reviewer — helper script.

Called by cold-review.sh. Handles all JSON parsing and prompt assembly.

Usage:
  python cold-review-helper.py parse-hook             — read hook JSON from stdin, print stop_hook_active
  python cold-review-helper.py build-prompt            — assemble system prompt from profile + template
  python cold-review-helper.py parse-review            — parse claude JSON output from stdin
  python cold-review-helper.py log-review <cwd> <mode> <model>  — read review JSON from stdin, append to history
  python cold-review-helper.py log-state <cwd> <mode> <model> <state> [reason]  — log non-review state to history
  python cold-review-helper.py format-block            — read review JSON from stdin, format block reason
  python cold-review-helper.py check-pass              — read review JSON from stdin, print true/false
  python cold-review-helper.py should-block [threshold] — read review JSON from stdin, print true/false
  python cold-review-helper.py filter-files [ignore_file] — read file list from stdin, print filtered list
  python cold-review-helper.py rank-files [untracked_file] — read file list from stdin, print risk-sorted list
"""

import fnmatch
import json
import re
import sys
import os
from datetime import datetime, timezone


SCRIPTS_DIR = os.path.dirname(os.path.abspath(__file__))
PROFILE_PATH = os.path.join(SCRIPTS_DIR, "cold-review-profile.json")
PROMPT_TEMPLATE = os.path.join(SCRIPTS_DIR, "cold-review-prompt.txt")
HISTORY_FILE = os.path.join(os.path.expanduser("~"), ".claude", "cold-review-history.jsonl")


def parse_hook():
    """Read hook JSON from stdin, print stop_hook_active."""
    try:
        data = json.load(sys.stdin)
        active = data.get("stop_hook_active", False)
        print(str(active).lower())
    except Exception:
        print("false")


def build_prompt():
    """Assemble system prompt from profile + template. Print to stdout."""
    try:
        with open(PROFILE_PATH, "r", encoding="utf-8") as f:
            profile = json.load(f)
    except FileNotFoundError:
        profile = {
            "name": "Cold Eyes",
            "personality": "A methodical reviewer.",
            "language": "English",
            "stats": {}
        }

    try:
        with open(PROMPT_TEMPLATE, "r", encoding="utf-8") as f:
            template = f.read()
    except FileNotFoundError:
        print("You are a cold-eyes reviewer. Review the diff. Output JSON: {pass, issues, summary}.")
        return

    stats = profile.get("stats", {})
    result = template
    result = result.replace("{name}", profile.get("name", "Cold Eyes"))
    result = result.replace("{language}", profile.get("language", "English"))
    result = result.replace("{stats_rigor}", str(stats.get("RIGOR", 50)))
    result = result.replace("{stats_paranoia}", str(stats.get("PARANOIA", 50)))

    print(result)


def parse_review():
    """Parse claude --output-format json output. Print parsed JSON to stdout.

    claude -p --output-format json returns:
    {"type":"result","subtype":"success","result":"<the model's text response>", ...}

    The model's response (in "result") should be a JSON string like:
    {"pass": true/false, "review_status": "completed", "issues": [...], "summary": "..."}
    """
    try:
        raw = json.load(sys.stdin)
        result_str = raw.get("result", "{}")
        if isinstance(result_str, str):
            # The model might wrap JSON in markdown code blocks — strip them
            cleaned = result_str.strip()
            if cleaned.startswith("```"):
                lines = cleaned.split("\n")
                lines = [l for l in lines if not l.strip().startswith("```")]
                cleaned = "\n".join(lines).strip()
            result = json.loads(cleaned)
        else:
            result = result_str
        # Apply defaults for missing fields
        result.setdefault("review_status", "completed")
        result.setdefault("pass", True)
        result.setdefault("issues", [])
        result.setdefault("summary", "")
        for issue in result["issues"]:
            issue.setdefault("severity", "major")
            issue.setdefault("confidence", "medium")
            issue.setdefault("category", "correctness")
            issue.setdefault("file", "unknown")
        print(json.dumps(result, ensure_ascii=False))
    except Exception as e:
        # Explicit failure state — do not block on parse failure
        print(json.dumps({
            "pass": True,
            "review_status": "failed",
            "issues": [],
            "summary": f"Parse error: {e}"
        }, ensure_ascii=False))


def log_review():
    """Append review to history file. Reads review JSON from stdin.

    Args: <cwd> <mode> <model> <state> [file_count] [line_count] [truncated]

    State is determined by the shell script after the should-block decision,
    not inferred from the review's pass field.
    """
    cwd = sys.argv[2]
    mode = sys.argv[3]
    model = sys.argv[4]
    state = sys.argv[5]
    file_count = int(sys.argv[6]) if len(sys.argv) > 6 else 0
    line_count = int(sys.argv[7]) if len(sys.argv) > 7 else 0
    truncated = sys.argv[8].lower() == "true" if len(sys.argv) > 8 else False

    try:
        review = json.load(sys.stdin)
    except Exception:
        review = {"pass": True, "issues": [], "summary": "Log parse error"}

    entry = {
        "version": 2,
        "timestamp": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "cwd": cwd,
        "mode": mode,
        "model": model,
        "state": state,
        "diff_stats": {
            "files": file_count,
            "lines": line_count,
            "truncated": truncated
        },
        "review": review
    }

    os.makedirs(os.path.dirname(HISTORY_FILE), exist_ok=True)
    with open(HISTORY_FILE, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")


def format_block():
    """Format review JSON into a block reason string. Reads review JSON from stdin."""
    try:
        data = json.load(sys.stdin)
    except Exception:
        print("Cold Eyes Review found issues but failed to parse details.")
        return

    issues = data.get("issues", [])
    summary = data.get("summary", "")

    lines = [f"Cold Eyes Review — {summary}"]
    for issue in issues:
        severity = issue.get("severity", "major").upper()
        check = issue.get("check", "")
        verdict = issue.get("verdict", "")
        fix = issue.get("fix", "")
        lines.append(f"  - [{severity}] 檢查：{check}")
        lines.append(f"    判決：{verdict}")
        lines.append(f"    指示：{fix}")

    print("\n".join(lines))


def log_state():
    """Log a non-review state to history. Args: <cwd> <mode> <model> <state> [reason]"""
    cwd = sys.argv[2]
    mode = sys.argv[3]
    model = sys.argv[4]
    state = sys.argv[5]
    reason = sys.argv[6] if len(sys.argv) > 6 else ""

    entry = {
        "version": 2,
        "timestamp": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "cwd": cwd,
        "mode": mode,
        "model": model,
        "state": state,
        "reason": reason,
        "review": None
    }

    os.makedirs(os.path.dirname(HISTORY_FILE), exist_ok=True)
    with open(HISTORY_FILE, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")


SEVERITY_ORDER = {"critical": 3, "major": 2, "minor": 1}


def should_block():
    """Read review JSON from stdin, compare max severity against threshold. Print true/false.

    Args: [threshold] — 'critical' (default) or 'major'.
    """
    threshold = sys.argv[2] if len(sys.argv) > 2 else "critical"
    threshold_level = SEVERITY_ORDER.get(threshold, 3)

    try:
        data = json.load(sys.stdin)
    except Exception:
        print("false")
        return

    if data.get("review_status") == "failed":
        print("false")
        return

    max_severity = 0
    for issue in data.get("issues", []):
        level = SEVERITY_ORDER.get(issue.get("severity", "major"), 2)
        max_severity = max(max_severity, level)

    print("true" if max_severity >= threshold_level else "false")


BUILTIN_IGNORE = [
    "*.lock", "package-lock.json", "pnpm-lock.yaml", "yarn.lock",
    "dist/*", "build/*", ".next/*", "coverage/*", "vendor/*",
    "node_modules/*", "*.min.js", "*.min.css",
]

RISK_PATTERN = re.compile(r"(auth|payment|db|migration|secret|credential|config|api)", re.IGNORECASE)


def filter_files():
    """Read file list from stdin, print filtered list. Args: [ignore_file_path]"""
    ignore_file = sys.argv[2] if len(sys.argv) > 2 else ""
    patterns = list(BUILTIN_IGNORE)
    if ignore_file and os.path.isfile(ignore_file):
        with open(ignore_file, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#"):
                    patterns.append(line)
    for line in sys.stdin:
        filepath = line.strip()
        if not filepath:
            continue
        if not any(
            fnmatch.fnmatch(filepath, p) or fnmatch.fnmatch(os.path.basename(filepath), p)
            for p in patterns
        ):
            print(filepath)


def rank_files():
    """Read file list from stdin, print risk-sorted list. Args: [untracked_list_file]

    Risk scoring:
      +3 path matches auth|payment|db|migration|secret|credential|config|api
      +2 file is untracked (new)
      +1 default (every file gets at least 1)
    """
    untracked_file = sys.argv[2] if len(sys.argv) > 2 else ""
    untracked = set()
    if untracked_file and os.path.isfile(untracked_file):
        with open(untracked_file, "r", encoding="utf-8") as f:
            for line in f:
                untracked.add(line.strip())

    files = []
    for line in sys.stdin:
        filepath = line.strip()
        if not filepath:
            continue
        score = 1  # base score
        if RISK_PATTERN.search(filepath):
            score += 3
        if filepath in untracked:
            score += 2
        files.append((score, filepath))

    files.sort(key=lambda x: (-x[0], x[1]))
    for _, filepath in files:
        print(filepath)


def check_pass():
    """Read review JSON from stdin, print true/false."""
    try:
        data = json.load(sys.stdin)
        print(str(data.get("pass", True)).lower())
    except Exception:
        print("true")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: cold-review-helper.py <command>", file=sys.stderr)
        sys.exit(1)

    cmd = sys.argv[1]
    if cmd == "parse-hook":
        parse_hook()
    elif cmd == "build-prompt":
        build_prompt()
    elif cmd == "parse-review":
        parse_review()
    elif cmd == "log-review":
        log_review()
    elif cmd == "format-block":
        format_block()
    elif cmd == "check-pass":
        check_pass()
    elif cmd == "log-state":
        log_state()
    elif cmd == "should-block":
        should_block()
    elif cmd == "filter-files":
        filter_files()
    elif cmd == "rank-files":
        rank_files()
    else:
        print(f"Unknown command: {cmd}", file=sys.stderr)
        sys.exit(1)
