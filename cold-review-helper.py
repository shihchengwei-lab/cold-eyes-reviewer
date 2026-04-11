"""Cold Eyes Reviewer — helper script.

Called by cold-review.sh. Handles all JSON parsing and prompt assembly.

Usage:
  python cold-review-helper.py parse-hook          — read hook JSON from stdin, print stop_hook_active
  python cold-review-helper.py build-prompt         — assemble system prompt from profile + template
  python cold-review-helper.py parse-review         — parse claude JSON output from stdin
  python cold-review-helper.py log-review <cwd> <mode> <model>  — read review JSON from stdin, append to history
  python cold-review-helper.py format-block         — read review JSON from stdin, format block reason
  python cold-review-helper.py check-pass           — read review JSON from stdin, print true/false
"""

import json
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
    result = result.replace("{personality}", profile.get("personality", ""))
    result = result.replace("{language}", profile.get("language", "English"))
    result = result.replace("{stats_rigor}", str(stats.get("RIGOR", 50)))
    result = result.replace("{stats_snark}", str(stats.get("SNARK", 50)))
    result = result.replace("{stats_patience}", str(stats.get("PATIENCE", 50)))
    result = result.replace("{stats_paranoia}", str(stats.get("PARANOIA", 50)))

    print(result)


def parse_review():
    """Parse claude --output-format json output. Print parsed JSON to stdout.

    claude -p --output-format json returns:
    {"type":"result","subtype":"success","result":"<the model's text response>", ...}

    The model's response (in "result") should be a JSON string like:
    {"pass": true/false, "issues": [...], "summary": "..."}
    """
    try:
        raw = json.load(sys.stdin)
        result_str = raw.get("result", "{}")
        if isinstance(result_str, str):
            # The model might wrap JSON in markdown code blocks — strip them
            cleaned = result_str.strip()
            if cleaned.startswith("```"):
                lines = cleaned.split("\n")
                # Remove first line (```json) and last line (```)
                lines = [l for l in lines if not l.strip().startswith("```")]
                cleaned = "\n".join(lines).strip()
            result = json.loads(cleaned)
        else:
            result = result_str
        print(json.dumps(result, ensure_ascii=False))
    except Exception as e:
        print(json.dumps({"pass": True, "issues": [], "summary": f"Parse error: {e}"}, ensure_ascii=False))


def log_review():
    """Append review to history file. Reads review JSON from stdin. Args: <cwd> <mode> <model>"""
    cwd = sys.argv[2]
    mode = sys.argv[3]
    model = sys.argv[4]

    try:
        review = json.load(sys.stdin)
    except Exception:
        review = {"pass": True, "issues": [], "summary": "Log parse error"}

    entry = {
        "timestamp": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "cwd": cwd,
        "mode": mode,
        "model": model,
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
        check = issue.get("check", "")
        verdict = issue.get("verdict", "")
        fix = issue.get("fix", "")
        lines.append(f"  - 檢查：{check}")
        lines.append(f"    判決：{verdict}")
        lines.append(f"    指示：{fix}")

    print("\n".join(lines))


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
    else:
        print(f"Unknown command: {cmd}", file=sys.stderr)
        sys.exit(1)
