"""CLI entry point for Cold Eyes Reviewer."""

import os
import sys

# Allow direct invocation: python cold_eyes/cli.py
_pkg = os.path.dirname(os.path.abspath(__file__))
_root = os.path.dirname(_pkg)
if _root not in sys.path:
    sys.path.insert(0, _root)

import argparse
import json

from cold_eyes.engine import run
from cold_eyes.doctor import run_doctor, run_doctor_fix, run_init
from cold_eyes.history import (
    aggregate_overrides, compute_stats, prune_history, archive_history, quality_report,
)
from cold_eyes.override import arm_override
from cold_eyes import __version__


def _run_v2(args):
    """Run the v2 session pipeline and return a shell-compatible result dict."""
    from cold_eyes.git import collect_files, git_cmd, GitCommandError, ConfigError
    from cold_eyes.config import load_policy
    from cold_eyes.engine import _resolve
    from cold_eyes.runner.session_runner import run_session
    from cold_eyes.session.store import SessionStore

    # Resolve scope/base the same way engine.run() does (CLI > env > policy > default)
    try:
        repo_root = git_cmd("rev-parse", "--show-toplevel")
    except GitCommandError:
        repo_root = ""
    policy = load_policy(repo_root)
    scope = _resolve(args.scope, "COLD_REVIEW_SCOPE", policy, "scope", "working")
    base = _resolve(args.base, "COLD_REVIEW_BASE", policy, "base", None)

    try:
        all_files, _untracked = collect_files(scope, base=base)
    except (GitCommandError, ConfigError) as exc:
        return {"action": "pass", "state": "infra_failed",
                "reason": str(exc),
                "display": f"cold-review: infrastructure failure — {exc}"}

    if not all_files:
        return {"action": "pass", "state": "skipped", "reason": "no changes",
                "display": "cold-review: skipped (no changes)"}

    # Build engine_kwargs so the internal engine.run() call picks up CLI settings
    engine_kwargs = {}
    for attr, key in [
        ("mode", "mode"), ("model", "model"), ("max_tokens", "max_tokens"),
        ("threshold", "threshold"), ("confidence", "confidence"),
        ("language", "language"), ("scope", "scope"), ("base", "base"),
        ("override_reason", "override_reason"),
        ("truncation_policy", "truncation_policy"),
        ("shallow_model", "shallow_model"),
        ("context_tokens", "context_tokens"),
        ("max_input_tokens", "max_input_tokens"),
    ]:
        val = getattr(args, attr, None)
        if val is not None:
            engine_kwargs[key] = val

    task_desc = f"review {scope} changes ({len(all_files)} files)"

    session = run_session(
        task_description=task_desc,
        changed_files=all_files,
        engine_kwargs=engine_kwargs,
    )

    # Persist session record
    try:
        store = SessionStore()
        store.save(session)
    except Exception:
        pass  # persistence failure must not block the review outcome

    # Extract final_outcome and add shell-compatible fields
    outcome = session.get("final_outcome", {"action": "pass", "state": "unknown"})
    state = outcome.get("state", "unknown")
    action = outcome.get("action", "pass")

    if action == "block":
        reason = outcome.get("stop_reason", "review failed")
        display = f"cold-review: BLOCKED — {reason}"
    else:
        display = f"cold-review: {state}"
        reason = ""

    outcome.setdefault("display", display)
    outcome.setdefault("reason", reason)
    return outcome


def main():
    parser = argparse.ArgumentParser(description="Cold Eyes Reviewer engine")
    parser.add_argument("--version", action="version",
                        version=f"cold-eyes-reviewer {__version__}")
    parser.add_argument("command", choices=[
        "run", "doctor", "init", "aggregate-overrides", "stats", "quality-report",
        "arm-override", "history-prune", "history-archive",
        "eval", "verify-install",
    ])
    parser.add_argument("--mode", default=None)
    parser.add_argument("--model", default=None)
    parser.add_argument("--max-tokens", type=int, default=None)
    parser.add_argument("--threshold", default=None)
    parser.add_argument("--confidence", default=None)
    parser.add_argument("--language", default=None)
    parser.add_argument("--scope", default=None,
                        choices=["working", "staged", "head", "pr-diff"])
    parser.add_argument("--base", default=None,
                        help="Base branch for pr-diff scope (e.g. main)")
    parser.add_argument("--override-reason", default=None)
    parser.add_argument("--last", default=None,
                        help="Time filter for stats (e.g. 7d, 24h, 2w)")
    parser.add_argument("--by-reason", action="store_true",
                        help="Include override reason breakdown in stats")
    parser.add_argument("--by-path", action="store_true",
                        help="Include per-path breakdown in stats")
    parser.add_argument("--reason", default=None,
                        help="Override reason for arm-override")
    parser.add_argument("--ttl", type=int, default=10,
                        help="Token TTL in minutes for arm-override (default: 10)")
    parser.add_argument("--fix", action="store_true",
                        help="Auto-fix safe issues (for doctor command)")
    parser.add_argument("--keep-days", type=int, default=None,
                        help="Keep entries from last N days (for history-prune)")
    parser.add_argument("--keep-entries", type=int, default=None,
                        help="Keep most recent N entries (for history-prune)")
    parser.add_argument("--before", default=None,
                        help="Archive entries before date YYYY-MM-DD (for history-archive)")
    parser.add_argument("--shallow-model", default=None,
                        help="Model for shallow reviews (default: sonnet)")
    parser.add_argument("--context-tokens", type=int, default=None,
                        help="Token budget for context retrieval in deep reviews (default: 2000)")
    parser.add_argument("--max-input-tokens", type=int, default=None,
                        help="Total token cap for model input: diff + context + hints")
    parser.add_argument("--truncation-policy", default=None,
                        choices=["warn", "soft-pass", "fail-closed"],
                        help="How to handle truncated diffs (default: warn)")
    parser.add_argument("--v2", action="store_true",
                        help="Use v2 session pipeline (opt-in)")
    parser.add_argument("--eval-mode", default="deterministic",
                        choices=["deterministic", "benchmark", "sweep"],
                        help="Eval mode: deterministic (mock), benchmark (real model), sweep")
    parser.add_argument("--cases-dir", default=None,
                        help="Path to eval cases directory (default: evals/cases/)")
    parser.add_argument("--save", action="store_true",
                        help="Save eval report to evals/results/")
    parser.add_argument("--format", default="json",
                        choices=["json", "markdown", "both"],
                        help="Report save format (default: json)")
    parser.add_argument("--compare", default=None,
                        help="Path to a previous report JSON for comparison")
    parser.add_argument("--regression-check", default=None,
                        help="Path to baseline JSON for regression check (exit 1 on regression)")
    args = parser.parse_args()

    if args.command == "init":
        result = run_init()
    elif args.command == "doctor":
        result = run_doctor_fix() if args.fix else run_doctor()
    elif args.command == "aggregate-overrides":
        result = aggregate_overrides()
    elif args.command == "stats":
        result = compute_stats(last=args.last, by_reason=args.by_reason,
                               by_path=args.by_path)
    elif args.command == "quality-report":
        result = quality_report(last=args.last)
    elif args.command == "history-prune":
        result = prune_history(keep_days=args.keep_days,
                               keep_entries=args.keep_entries)
    elif args.command == "history-archive":
        result = archive_history(before=args.before)
    elif args.command == "arm-override":
        from cold_eyes.git import git_cmd, GitCommandError
        try:
            repo_root = git_cmd("rev-parse", "--show-toplevel")
        except GitCommandError:
            repo_root = os.getcwd()
        reason = args.reason or args.override_reason or ""
        result = arm_override(repo_root, reason, ttl_minutes=args.ttl)
    elif args.command == "eval":
        from evals.eval_runner import (
            run_deterministic, run_benchmark, threshold_sweep,
            save_report, compare_reports, regression_check,
        )
        cases_dir = args.cases_dir or os.path.join(_root, "evals", "cases")
        regression_path = getattr(args, "regression_check", None)
        if regression_path:
            result = regression_check(
                regression_path, cases_dir,
                threshold=args.threshold or "critical",
                confidence=args.confidence or "medium",
            )
            print(json.dumps(result, ensure_ascii=False))
            sys.exit(1 if result["regressed"] else 0)
        if args.eval_mode == "deterministic":
            result = run_deterministic(cases_dir, threshold=args.threshold or "critical",
                                       confidence=args.confidence or "medium")
        elif args.eval_mode == "benchmark":
            result = run_benchmark(cases_dir, model=args.model or "opus")
        elif args.eval_mode == "sweep":
            result = threshold_sweep(cases_dir)
        if args.save:
            saved = save_report(result, fmt=getattr(args, "format", "json"))
            result["saved"] = saved
        if args.compare:
            with open(args.compare, "r", encoding="utf-8") as f:
                other = json.load(f)
            result["comparison"] = compare_reports(other, result)
    elif args.command == "verify-install":
        from cold_eyes.doctor import verify_install
        result = verify_install()
    else:
        if getattr(args, "v2", False):
            result = _run_v2(args)
        else:
            result = run(mode=args.mode, model=args.model,
                         max_tokens=args.max_tokens, threshold=args.threshold,
                         confidence=args.confidence, language=args.language,
                         scope=args.scope, base=args.base,
                         override_reason=args.override_reason,
                         truncation_policy=args.truncation_policy,
                         shallow_model=args.shallow_model,
                         context_tokens=args.context_tokens,
                         max_input_tokens=args.max_input_tokens)
    print(json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    main()
