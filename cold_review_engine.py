"""Cold Eyes Reviewer — engine.

Orchestrates the full review pipeline. Called by cold-review.sh after guard
checks pass.  Outputs a single FinalOutcome JSON line to stdout.

Usage:
  python cold_review_engine.py run --mode block --model opus --max-tokens 12000 --threshold critical
  python cold_review_engine.py doctor
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

SCHEMA_VERSION = 1
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

DEPLOY_FILES = [
    "cold-review.sh", "cold-review-helper.py",
    "cold_review_engine.py", "cold-review-prompt.txt",
]


# ---------------------------------------------------------------------------
# Git helpers
# ---------------------------------------------------------------------------

def git_cmd(*args):
    """Run a git command, return stdout or empty string on failure."""
    r = subprocess.run(
        ["git"] + list(args), capture_output=True, text=True
    )
    return r.stdout.strip() if r.returncode == 0 else ""


def collect_files(scope="working"):
    """Return (all_files sorted list, untracked set).

    Scopes:
      working — staged + unstaged + untracked (default)
      staged  — only staged changes
      head    — diff against HEAD (staged + unstaged, no untracked)
    """
    if scope == "staged":
        staged = set(filter(None, git_cmd("diff", "--cached", "--name-only").split("\n")))
        return sorted(staged), set()
    elif scope == "head":
        head = set(filter(None, git_cmd("diff", "HEAD", "--name-only").split("\n")))
        return sorted(head), set()
    else:  # working
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

def build_diff(ranked_files, untracked, max_tokens=12000, scope="working"):
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
            if scope == "staged":
                chunk = git_cmd("diff", "--cached", "--", f)
            elif scope == "head":
                chunk = git_cmd("diff", "HEAD", "--", f)
            else:  # working
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
        result.setdefault("schema_version", SCHEMA_VERSION)
        result.setdefault("review_status", "completed")
        result.setdefault("pass", True)
        result.setdefault("issues", [])
        result.setdefault("summary", "")
        for issue in result["issues"]:
            issue.setdefault("severity", "major")
            issue.setdefault("confidence", "medium")
            issue.setdefault("category", "correctness")
            issue.setdefault("file", "unknown")
            issue.setdefault("line_hint", "")
        return result
    except Exception as e:
        return {
            "schema_version": SCHEMA_VERSION,
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


def format_block_reason(review, truncated=False, skipped_count=0):
    """Format review into human-readable block reason."""
    summary = review.get("summary", "")
    issues = review.get("issues", [])
    lines = [f"Cold Eyes Review — {summary}"]
    for issue in issues:
        sev = issue.get("severity", "major").upper()
        line_hint = issue.get("line_hint", "")
        check = issue.get("check", "")
        verdict = issue.get("verdict", "")
        fix = issue.get("fix", "")
        hint_part = f" (~{line_hint})" if line_hint else ""
        lines.append(f"  - [{sev}]{hint_part} \u6aa2\u67e5\uff1a{check}")
        lines.append(f"    \u5224\u6c7a\uff1a{verdict}")
        lines.append(f"    \u6307\u793a\uff1a{fix}")
    if truncated:
        lines.append(f"  \u26a0 \u5be9\u67e5\u4e0d\u5b8c\u6574\uff1adiff \u8d85\u904e token \u9810\u7b97\uff0c{skipped_count} \u500b\u6a94\u6848\u672a\u5be9\u67e5\u3002")
    return "\n".join(lines)


def apply_policy(review, mode, threshold, allow_once, min_confidence="medium",
                 truncated=False, skipped_files=None, override_reason=""):
    """Determine final outcome. Return FinalOutcome dict.

    FinalOutcome keys: action, state, reason, display, truncated, skipped_count
    The review in the outcome has issues filtered by confidence.
    """
    if skipped_files is None:
        skipped_files = []
    skipped_count = len(skipped_files)
    engine_ok = review.get("review_status") != "failed"

    # --- Infrastructure failure ---
    if not engine_ok:
        error_detail = review.get("summary", "unknown error")
        if mode == "block":
            if allow_once:
                reason_suffix = f" [{override_reason}]" if override_reason else ""
                return {
                    "action": "pass",
                    "state": "overridden",
                    "reason": override_reason,
                    "display": f"cold-review: override \u2014 infra failure bypass (ALLOW_ONCE){reason_suffix}",
                }
            return {
                "action": "block",
                "state": "infra_failed",
                "reason": (
                    f"Cold Eyes Review \u2014 infrastructure failure: {error_detail}.\n"
                    "To override: COLD_REVIEW_ALLOW_ONCE=1 COLD_REVIEW_OVERRIDE_REASON='<reason>'"
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
            reason_suffix = f" [{override_reason}]" if override_reason else ""
            return {
                "action": "pass",
                "state": "overridden",
                "reason": override_reason,
                "display": f"cold-review: override \u2014 block skipped (ALLOW_ONCE){reason_suffix}",
            }
        block_reason = format_block_reason(review, truncated, skipped_count)
        block_reason += (
            "\n\nTo override: COLD_REVIEW_ALLOW_ONCE=1 "
            "COLD_REVIEW_OVERRIDE_REASON='<reason>'"
        )
        return {
            "action": "block",
            "state": "blocked",
            "reason": block_reason,
            "display": f"cold-review: blocking (issues at or above {threshold})",
            "truncated": truncated,
            "skipped_count": skipped_count,
        }

    return {
        "action": "pass",
        "state": "passed",
        "reason": "",
        "display": "cold-review: pass",
        "truncated": truncated,
        "skipped_count": skipped_count,
    }


# ---------------------------------------------------------------------------
# History
# ---------------------------------------------------------------------------

def log_to_history(cwd, mode, model, state, reason="", review=None,
                   file_count=0, line_count=0, truncated=False, token_count=0,
                   min_confidence="medium", scope="working", override_reason=""):
    """Append structured entry to history JSONL file."""
    entry = {
        "version": 2,
        "timestamp": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "cwd": cwd,
        "mode": mode,
        "model": model,
        "state": state,
        "min_confidence": min_confidence,
        "scope": scope,
        "schema_version": review.get("schema_version", SCHEMA_VERSION) if review else SCHEMA_VERSION,
    }
    if override_reason:
        entry["override_reason"] = override_reason

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

def run(mode, model, max_tokens, threshold, confidence=None, language=None,
        scope="working", override_reason=None):
    """Execute full review pipeline. Return FinalOutcome dict."""
    cwd = os.getcwd()
    allow_once = os.environ.get("COLD_REVIEW_ALLOW_ONCE") == "1"
    override_reason = override_reason or os.environ.get("COLD_REVIEW_OVERRIDE_REASON", "")
    min_confidence = confidence or os.environ.get("COLD_REVIEW_CONFIDENCE", "medium").lower()
    repo_root = git_cmd("rev-parse", "--show-toplevel")
    ignore_file = os.path.join(repo_root, ".cold-review-ignore") if repo_root else ""

    # 1. Collect files
    all_files, untracked = collect_files(scope)
    if not all_files:
        log_to_history(cwd, mode, model, "skipped", "no changes",
                       min_confidence=min_confidence, scope=scope)
        return _skip("no changes")

    # 2. Filter
    filtered = filter_file_list(all_files, ignore_file)
    if not filtered:
        log_to_history(cwd, mode, model, "skipped", "all files ignored",
                       min_confidence=min_confidence, scope=scope)
        return _skip("all files ignored")

    # 3. Rank
    ranked = rank_file_list(filtered, untracked)

    # 4. Build diff
    diff_text, file_count, token_count, truncated, skipped = build_diff(
        ranked, untracked, max_tokens, scope
    )

    if not diff_text.strip():
        log_to_history(cwd, mode, model, "skipped", "no diff content",
                       min_confidence=min_confidence, scope=scope)
        return _skip("no diff content")

    # 5. Build prompt
    prompt_text = build_prompt_text(language)
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
            outcome = apply_policy(review, mode, threshold, allow_once, min_confidence,
                                   override_reason=override_reason)
            log_to_history(cwd, mode, model, outcome["state"],
                           reason=review["summary"], min_confidence=min_confidence,
                           scope=scope, override_reason=override_reason)
            return outcome

        if not raw_output:
            review = _infra_review("empty output")
            outcome = apply_policy(review, mode, threshold, allow_once, min_confidence,
                                   override_reason=override_reason)
            log_to_history(cwd, mode, model, outcome["state"],
                           reason=review["summary"], min_confidence=min_confidence,
                           scope=scope, override_reason=override_reason)
            return outcome

        # 8. Parse review
        review = parse_review_output(raw_output)

        # 9–10. Apply policy (with truncation context)
        outcome = apply_policy(review, mode, threshold, allow_once, min_confidence,
                               truncated=truncated, skipped_files=skipped,
                               override_reason=override_reason)

        # 11. Log
        diff_line_count = diff_text.count("\n") + 1
        log_to_history(
            cwd, mode, model, outcome["state"],
            review=review, file_count=file_count,
            line_count=diff_line_count, truncated=truncated,
            token_count=token_count, min_confidence=min_confidence,
            scope=scope, override_reason=override_reason,
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
        "schema_version": SCHEMA_VERSION,
        "pass": True,
        "review_status": "failed",
        "issues": [],
        "summary": summary,
    }


# ---------------------------------------------------------------------------
# Aggregate overrides
# ---------------------------------------------------------------------------

def aggregate_overrides(history_path=None, limit=50):
    """Summarise override patterns from history.

    Returns dict with total_overrides, reasons (grouped by count desc), recent.
    """
    path = history_path or HISTORY_FILE
    overrides = []
    if os.path.isfile(path):
        with open(path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    entry = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if entry.get("state") == "overridden":
                    overrides.append(entry)

    counts = {}
    for entry in overrides:
        reason = entry.get("override_reason", "")
        counts[reason] = counts.get(reason, 0) + 1
    reasons = sorted(
        [{"reason": r, "count": c} for r, c in counts.items()],
        key=lambda x: x["count"], reverse=True,
    )
    recent = overrides[-limit:] if overrides else []
    return {
        "action": "aggregate-overrides",
        "total_overrides": len(overrides),
        "reasons": reasons,
        "recent": recent,
    }


# ---------------------------------------------------------------------------
# Doctor
# ---------------------------------------------------------------------------

def run_doctor(scripts_dir=None, settings_path=None, repo_root=None):
    """Check environment health. Return structured report dict."""
    if scripts_dir is None:
        scripts_dir = os.path.join(os.path.expanduser("~"), ".claude", "scripts")
    if settings_path is None:
        settings_path = os.path.join(os.path.expanduser("~"), ".claude", "settings.json")

    checks = []

    # 1. Python version
    ver = f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}"
    checks.append({"name": "python", "status": "ok", "detail": ver})

    # 2. Git
    git_ver = git_cmd("--version")
    if git_ver:
        checks.append({"name": "git", "status": "ok", "detail": git_ver})
    else:
        checks.append({"name": "git", "status": "fail", "detail": "not found"})

    # 3. Claude CLI
    try:
        r = subprocess.run(
            ["claude", "--version"], capture_output=True, text=True, timeout=10
        )
        if r.returncode == 0 and r.stdout.strip():
            checks.append({"name": "claude_cli", "status": "ok",
                           "detail": r.stdout.strip()})
        else:
            checks.append({"name": "claude_cli", "status": "fail",
                           "detail": f"exit {r.returncode}"})
    except FileNotFoundError:
        checks.append({"name": "claude_cli", "status": "fail",
                       "detail": "not found"})
    except Exception as e:
        checks.append({"name": "claude_cli", "status": "fail",
                       "detail": str(e)})

    # 4. Deploy files
    missing = [f for f in DEPLOY_FILES if not os.path.isfile(os.path.join(scripts_dir, f))]
    if not missing:
        checks.append({"name": "deploy_files", "status": "ok",
                       "detail": f"{len(DEPLOY_FILES)} files in {scripts_dir}"})
    else:
        checks.append({"name": "deploy_files", "status": "fail",
                       "detail": f"missing: {', '.join(missing)}"})

    # 5. settings.json Stop hook
    try:
        with open(settings_path, "r", encoding="utf-8") as f:
            settings = json.load(f)
        hooks = settings.get("hooks", {})
        stop_hooks = hooks.get("Stop", [])
        found = any(
            "cold-review.sh" in cmd
            for entry in stop_hooks
            for hook_list in ([entry] if isinstance(entry, str) else
                              entry.get("hooks", []) if isinstance(entry, dict) else [])
            for cmd in ([hook_list] if isinstance(hook_list, str) else
                        [hook_list.get("command", "")] if isinstance(hook_list, dict) else [])
        )
        if found:
            checks.append({"name": "settings_hook", "status": "ok",
                           "detail": "Stop hook configured"})
        else:
            checks.append({"name": "settings_hook", "status": "fail",
                           "detail": "cold-review.sh not found in hooks.Stop"})
    except FileNotFoundError:
        checks.append({"name": "settings_hook", "status": "fail",
                       "detail": f"{settings_path} not found"})
    except Exception as e:
        checks.append({"name": "settings_hook", "status": "fail",
                       "detail": str(e)})

    # 6. Git repo
    git_dir = git_cmd("rev-parse", "--git-dir")
    if git_dir:
        checks.append({"name": "git_repo", "status": "ok", "detail": "in git repo"})
    else:
        checks.append({"name": "git_repo", "status": "fail",
                       "detail": "not in a git repo"})

    # 7. .cold-review-ignore (info level)
    if repo_root is None:
        repo_root = git_cmd("rev-parse", "--show-toplevel")
    ignore_path = os.path.join(repo_root, ".cold-review-ignore") if repo_root else ""
    if ignore_path and os.path.isfile(ignore_path):
        checks.append({"name": "ignore_file", "status": "ok",
                       "detail": ".cold-review-ignore found"})
    else:
        checks.append({"name": "ignore_file", "status": "info",
                       "detail": ".cold-review-ignore not found (optional)"})

    all_ok = all(c["status"] != "fail" for c in checks)
    return {"action": "doctor", "checks": checks, "all_ok": all_ok}


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Cold Eyes Reviewer engine")
    parser.add_argument("command", choices=["run", "doctor", "aggregate-overrides"])
    parser.add_argument("--mode", default="block")
    parser.add_argument("--model", default="opus")
    parser.add_argument("--max-tokens", type=int, default=12000)
    parser.add_argument("--threshold", default="critical")
    parser.add_argument("--confidence", default=None)
    parser.add_argument("--language", default=None)
    parser.add_argument("--scope", default="working",
                        choices=["working", "staged", "head"])
    parser.add_argument("--override-reason", default=None)
    args = parser.parse_args()

    if args.command == "doctor":
        result = run_doctor()
    elif args.command == "aggregate-overrides":
        result = aggregate_overrides()
    else:
        result = run(args.mode, args.model, args.max_tokens, args.threshold,
                     confidence=args.confidence, language=args.language,
                     scope=args.scope,
                     override_reason=args.override_reason)
    print(json.dumps(result, ensure_ascii=False))
