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
    parser.add_argument("--truncation-policy", default=None,
                        choices=["warn", "soft-pass", "fail-closed"],
                        help="How to handle truncated diffs (default: warn)")
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
            save_report, compare_reports,
        )
        cases_dir = args.cases_dir or os.path.join(_root, "evals", "cases")
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
        result = run(mode=args.mode, model=args.model,
                     max_tokens=args.max_tokens, threshold=args.threshold,
                     confidence=args.confidence, language=args.language,
                     scope=args.scope, base=args.base,
                     override_reason=args.override_reason,
                     truncation_policy=args.truncation_policy)
    print(json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    main()
