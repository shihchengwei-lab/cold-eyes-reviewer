"""Cold Eyes Reviewer — engine.

Orchestrates the full review pipeline. Called by cold-review.sh after guard
checks pass.  Outputs a single FinalOutcome JSON line to stdout.

Usage:
  python cold_review_engine.py run --mode block --model opus --max-tokens 12000 --threshold critical
"""

import argparse
import fnmatch
import json
import os
import re
import subprocess
import sys
import tempfile
from datetime import datetime, timezone

SCRIPTS_DIR = os.path.dirname(os.path.abspath(__file__))
PROMPT_TEMPLATE = os.path.join(SCRIPTS_DIR, "cold-review-prompt.txt")
HISTORY_FILE = os.path.join(
    os.path.expanduser("~"), ".claude", "cold-review-history.jsonl"
)

SEVERITY_ORDER = {"critical": 3, "major": 2, "minor": 1}
CONFIDENCE_ORDER = {"high": 3, "medium": 2, "low": 1}

BUILTIN_IGNORE = [
    "*.lock", "package-lock.json", "pnpm-lock.yaml", "yarn.lock",
    "dist/*", "build/*", ".next/*", "coverage/*", "vendor/*",
    "node_modules/*", "*.min.js", "*.min.css",
]

RISK_PATTERN = re.compile(
    r"(auth|payment|db|migration|secret|credential|config|api)", re.IGNORECASE
)


# ---------------------------------------------------------------------------
# Git helpers
# ---------------------------------------------------------------------------

def git_cmd(*args):
    """Run a git command, return stdout or empty string on failure."""
    r = subprocess.run(
        ["git"] + list(args), capture_output=True, text=True
    )
    return r.stdout.strip() if r.returncode == 0 else ""


def collect_files():
    """Return (all_files sorted list, untracked set)."""
    staged = set(filter(None, git_cmd("diff", "--cached", "--name-only").split("\n")))
    unstaged = set(filter(None, git_cmd("diff", "--name-only").split("\n")))
    untracked = set(filter(None, git_cmd("ls-files", "--others", "--exclude-standard").split("\n")))
    return sorted(staged | unstaged | untracked), untracked


# ---------------------------------------------------------------------------
# File filtering & ranking
# ---------------------------------------------------------------------------

def filter_file_list(files, ignore_file=""):
    """Apply built-in + custom ignore patterns. Return filtered list."""
    patterns = list(BUILTIN_IGNORE)
    if ignore_file and os.path.isfile(ignore_file):
        with open(ignore_file, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#"):
                    patterns.append(line)
    result = []
    for fp in files:
        if not fp:
            continue
        if not any(
            fnmatch.fnmatch(fp, p) or fnmatch.fnmatch(os.path.basename(fp), p)
            for p in patterns
        ):
            result.append(fp)
    return result


def rank_file_list(files, untracked):
    """Sort files by risk score descending. Return ordered list."""
    scored = []
    for fp in files:
        if not fp:
            continue
        score = 1
        if RISK_PATTERN.search(fp):
            score += 3
        if fp in untracked:
            score += 2
        scored.append((score, fp))
    scored.sort(key=lambda x: (-x[0], x[1]))
    return [fp for _, fp in scored]


# ---------------------------------------------------------------------------
# Binary detection
# ---------------------------------------------------------------------------

def is_binary(filepath):
    """True if file contains null bytes in first 512 bytes."""
    try:
        with open(filepath, "rb") as f:
            return b"\x00" in f.read(512)
    except (OSError, IOError):
        return False


# ---------------------------------------------------------------------------
# Diff building with token budget
# ---------------------------------------------------------------------------

def build_diff(ranked_files, untracked, max_tokens=12000):
    """Build token-budgeted diff.

    Returns (diff_text, file_count, token_count, truncated, skipped_files).
    Token estimate: len(text) // 4.
    """
    remaining = max_tokens
    parts = []
    file_count = 0
    skipped = []

    for f in ranked_files:
        if remaining <= 0:
            skipped.append(f)
            continue

        if f in untracked:
            if is_binary(f):
                skipped.append(f"{f} (binary)")
                continue
            try:
                with open(f, "r", encoding="utf-8", errors="replace") as fh:
                    content = fh.read()
            except (OSError, IOError):
                skipped.append(f"{f} (unreadable)")
                continue
            chunk = f"=== NEW FILE: {f} ===\n{content}"
        else:
            staged = git_cmd("diff", "--cached", "--", f)
            unstaged = git_cmd("diff", "--", f)
            chunk = f"{staged}\n{unstaged}".strip()

        if not chunk:
            continue

        chunk_tokens = len(chunk) // 4
        if chunk_tokens > remaining:
            char_limit = remaining * 4
            chunk = chunk[:char_limit] + f"\n[truncated: {f}]"
            chunk_tokens = remaining

        parts.append(chunk)
        file_count += 1
        remaining -= chunk_tokens

    diff_text = "\n".join(parts)
    total_tokens = max_tokens - remaining
    truncated = len(skipped) > 0

    if truncated:
        notice = f"\n\n[Cold Eyes: diff truncated at ~{max_tokens} tokens. Skipped files:\n"
        for s in skipped:
            notice += f"  {s}\n"
        notice += "]"
        diff_text += notice

    return diff_text, file_count, total_tokens, truncated, skipped


# ---------------------------------------------------------------------------
# Prompt assembly
# ---------------------------------------------------------------------------

def build_prompt_text(language=None):
    """Assemble system prompt from template + language env var. Return string."""
    if language is None:
        language = os.environ.get("COLD_REVIEW_LANGUAGE", "繁體中文（台灣）")

    try:
        with open(PROMPT_TEMPLATE, "r", encoding="utf-8") as f:
            template = f.read()
    except FileNotFoundError:
        return "You are Cold Eyes, a zero-context reviewer. Review the diff. Output JSON: {pass, issues, summary}."

    return template.replace("{language}", language)


# ---------------------------------------------------------------------------
# Claude CLI
# ---------------------------------------------------------------------------

def call_claude(diff_text, model, prompt_file):
    """Call claude CLI. Return (raw_stdout, exit_code)."""
    env = {**os.environ, "COLD_REVIEW_ACTIVE": "1"}
    try:
        r = subprocess.run(
            [
                "claude", "-p", "Review the following changes.",
                "--model", model,
                "--append-system-prompt-file", prompt_file,
                "--output-format", "json",
            ],
            input=diff_text,
            capture_output=True,
            text=True,
            env=env,
            timeout=300,
        )
        return r.stdout.strip(), r.returncode
    except subprocess.TimeoutExpired:
        return "", -1
    except FileNotFoundError:
        return "", -2


# ---------------------------------------------------------------------------
# Review parsing
# ---------------------------------------------------------------------------

def parse_review_output(raw_json_str):
    """Parse claude --output-format json output. Return dict."""
    try:
        raw = json.loads(raw_json_str)
        result_str = raw.get("result", "{}")
        if isinstance(result_str, str):
            cleaned = result_str.strip()
            if cleaned.startswith("```"):
                lines = cleaned.split("\n")
                lines = [l for l in lines if not l.strip().startswith("```")]
                cleaned = "\n".join(lines).strip()
            result = json.loads(cleaned)
        else:
            result = result_str
        result.setdefault("review_status", "completed")
        result.setdefault("pass", True)
        result.setdefault("issues", [])
        result.setdefault("summary", "")
        for issue in result["issues"]:
            issue.setdefault("severity", "major")
            issue.setdefault("confidence", "medium")
            issue.setdefault("category", "correctness")
            issue.setdefault("file", "unknown")
        return result
    except Exception as e:
        return {
            "pass": True,
            "review_status": "failed",
            "issues": [],
            "summary": f"Parse error: {e}",
        }


# ---------------------------------------------------------------------------
# Policy
# ---------------------------------------------------------------------------

def filter_by_confidence(issues, min_confidence="medium"):
    """Remove issues below the confidence threshold. Deterministic hard filter."""
    threshold = CONFIDENCE_ORDER.get(min_confidence, 2)
    return [i for i in issues if CONFIDENCE_ORDER.get(i.get("confidence", "medium"), 2) >= threshold]


def format_block_reason(review):
    """Format review into human-readable block reason."""
    summary = review.get("summary", "")
    issues = review.get("issues", [])
    lines = [f"Cold Eyes Review — {summary}"]
    for issue in issues:
        sev = issue.get("severity", "major").upper()
        check = issue.get("check", "")
        verdict = issue.get("verdict", "")
        fix = issue.get("fix", "")
        lines.append(f"  - [{sev}] \u6aa2\u67e5\uff1a{check}")
        lines.append(f"    \u5224\u6c7a\uff1a{verdict}")
        lines.append(f"    \u6307\u793a\uff1a{fix}")
    return "\n".join(lines)


def apply_policy(review, mode, threshold, allow_once, min_confidence="medium"):
    """Determine final outcome. Return FinalOutcome dict.

    FinalOutcome keys: action, state, reason, display, review
    The review in the outcome has issues filtered by confidence.
    """
    engine_ok = review.get("review_status") != "failed"

    # --- Infrastructure failure ---
    if not engine_ok:
        error_detail = review.get("summary", "unknown error")
        if mode == "block":
            if allow_once:
                return {
                    "action": "pass",
                    "state": "overridden",
                    "reason": "",
                    "display": "cold-review: override \u2014 infra failure bypass (ALLOW_ONCE)",
                }
            return {
                "action": "block",
                "state": "infra_failed",
                "reason": (
                    f"Cold Eyes Review \u2014 infrastructure failure: {error_detail}. "
                    "Use COLD_REVIEW_ALLOW_ONCE=1 to bypass."
                ),
                "display": "cold-review: blocking (infrastructure failure)",
            }
        # report mode — log but pass
        return {
            "action": "pass",
            "state": "failed",
            "reason": error_detail,
            "display": f"cold-review: report logged (infra failure: {error_detail})",
        }

    # --- Confidence filter (hard gate) ---
    filtered_issues = filter_by_confidence(review.get("issues", []), min_confidence)
    review = {**review, "issues": filtered_issues}

    # --- Review completed ---
    threshold_level = SEVERITY_ORDER.get(threshold, 3)
    max_severity = 0
    for issue in filtered_issues:
        level = SEVERITY_ORDER.get(issue.get("severity", "major"), 2)
        max_severity = max(max_severity, level)

    should_block = max_severity >= threshold_level
    review_pass = review.get("pass", True)

    if mode == "report":
        state = "reported" if not review_pass else "passed"
        return {
            "action": "pass",
            "state": state,
            "reason": "",
            "display": f"cold-review: report logged (pass={review_pass})",
        }

    # block mode
    if should_block:
        if allow_once:
            return {
                "action": "pass",
                "state": "overridden",
                "reason": "",
                "display": "cold-review: override \u2014 block skipped (ALLOW_ONCE)",
            }
        return {
            "action": "block",
            "state": "blocked",
            "reason": format_block_reason(review),
            "display": f"cold-review: blocking (issues at or above {threshold})",
        }

    return {
        "action": "pass",
        "state": "passed",
        "reason": "",
        "display": "cold-review: pass",
    }


# ---------------------------------------------------------------------------
# History
# ---------------------------------------------------------------------------

def log_to_history(cwd, mode, model, state, reason="", review=None,
                   file_count=0, line_count=0, truncated=False, token_count=0):
    """Append structured entry to history JSONL file."""
    entry = {
        "version": 2,
        "timestamp": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "cwd": cwd,
        "mode": mode,
        "model": model,
        "state": state,
    }

    if review is not None:
        entry["diff_stats"] = {
            "files": file_count,
            "lines": line_count,
            "tokens": token_count,
            "truncated": truncated,
        }
        entry["review"] = review
    else:
        entry["reason"] = reason
        entry["review"] = None

    os.makedirs(os.path.dirname(HISTORY_FILE), exist_ok=True)
    with open(HISTORY_FILE, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")


# ---------------------------------------------------------------------------
# Main pipeline
# ---------------------------------------------------------------------------

def run(mode, model, max_tokens, threshold):
    """Execute full review pipeline. Return FinalOutcome dict."""
    cwd = os.getcwd()
    allow_once = os.environ.get("COLD_REVIEW_ALLOW_ONCE") == "1"
    min_confidence = os.environ.get("COLD_REVIEW_CONFIDENCE", "medium").lower()
    repo_root = git_cmd("rev-parse", "--show-toplevel")
    ignore_file = os.path.join(repo_root, ".cold-review-ignore") if repo_root else ""

    # 1. Collect files
    all_files, untracked = collect_files()
    if not all_files:
        log_to_history(cwd, mode, model, "skipped", "no changes")
        return _skip("no changes")

    # 2. Filter
    filtered = filter_file_list(all_files, ignore_file)
    if not filtered:
        log_to_history(cwd, mode, model, "skipped", "all files ignored")
        return _skip("all files ignored")

    # 3. Rank
    ranked = rank_file_list(filtered, untracked)

    # 4. Build diff
    diff_text, file_count, token_count, truncated, skipped = build_diff(
        ranked, untracked, max_tokens
    )

    if not diff_text.strip():
        log_to_history(cwd, mode, model, "skipped", "no diff content")
        return _skip("no diff content")

    # 5. Build prompt
    prompt_text = build_prompt_text()
    prompt_fd = tempfile.NamedTemporaryFile(
        mode="w", suffix=".txt", delete=False, encoding="utf-8"
    )
    prompt_fd.write(prompt_text)
    prompt_fd.close()

    try:
        # 6. Call claude
        raw_output, exit_code = call_claude(diff_text, model, prompt_fd.name)

        # 7. Handle CLI errors
        if exit_code != 0:
            review = _infra_review(f"claude exit {exit_code}")
            outcome = apply_policy(review, mode, threshold, allow_once, min_confidence)
            log_to_history(cwd, mode, model, outcome["state"], reason=review["summary"])
            return outcome

        if not raw_output:
            review = _infra_review("empty output")
            outcome = apply_policy(review, mode, threshold, allow_once, min_confidence)
            log_to_history(cwd, mode, model, outcome["state"], reason=review["summary"])
            return outcome

        # 8. Parse review
        review = parse_review_output(raw_output)

        # 9–10. Apply policy
        outcome = apply_policy(review, mode, threshold, allow_once, min_confidence)

        # 11. Log
        diff_line_count = diff_text.count("\n") + 1
        log_to_history(
            cwd, mode, model, outcome["state"],
            review=review, file_count=file_count,
            line_count=diff_line_count, truncated=truncated,
            token_count=token_count,
        )

        return outcome
    finally:
        os.unlink(prompt_fd.name)


def _skip(reason):
    return {
        "action": "pass",
        "state": "skipped",
        "reason": reason,
        "display": f"cold-review: skipped ({reason})",
    }


def _infra_review(summary):
    """Build a synthetic review dict representing an infrastructure failure."""
    return {
        "pass": True,
        "review_status": "failed",
        "issues": [],
        "summary": summary,
    }


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Cold Eyes Reviewer engine")
    parser.add_argument("command", choices=["run"])
    parser.add_argument("--mode", default="block")
    parser.add_argument("--model", default="opus")
    parser.add_argument("--max-tokens", type=int, default=12000)
    parser.add_argument("--threshold", default="critical")
    args = parser.parse_args()

    result = run(args.mode, args.model, args.max_tokens, args.threshold)
    print(json.dumps(result, ensure_ascii=False))
