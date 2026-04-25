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
    format_human_status, runtime_status,
)
from cold_eyes.health import (
    agent_notice,
    install_health_schedule,
    remove_health_schedule,
)
from cold_eyes.override import arm_override
from cold_eyes import __version__


def _auto_tune_enabled():
    value = os.environ.get("COLD_REVIEW_AUTO_TUNE", "on").strip().lower()
    return value not in {"0", "false", "no", "off"}


def _env_int(name, default):
    value = os.environ.get(name)
    if value in (None, ""):
        return default
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _attach_auto_tune(result):
    """Run low-frequency auto-tune after reviews without affecting outcome."""
    if not _auto_tune_enabled():
        return result
    from cold_eyes.autotune import maybe_auto_tune
    from cold_eyes.git import git_cmd, GitCommandError

    try:
        repo_root = git_cmd("rev-parse", "--show-toplevel")
    except GitCommandError:
        return result

    try:
        tune = maybe_auto_tune(
            repo_root=repo_root,
            last=os.environ.get("COLD_REVIEW_AUTO_TUNE_LAST", "7d"),
            min_samples=_env_int("COLD_REVIEW_AUTO_TUNE_MIN_SAMPLES", 5),
            interval_hours=_env_int("COLD_REVIEW_AUTO_TUNE_INTERVAL_HOURS", 24),
        )
    except Exception as exc:
        tune = {"action": "auto-tune-skip", "reason": f"error: {exc}"}
    result = dict(result)
    result["auto_tune"] = tune
    return result


def main():
    parser = argparse.ArgumentParser(description="Cold Eyes Reviewer engine")
    parser.add_argument("--version", action="version",
                        version=f"cold-eyes-reviewer {__version__}")
    parser.add_argument("command", choices=[
        "run", "doctor", "init", "aggregate-overrides", "stats", "quality-report",
        "status", "arm-override", "history-prune", "history-archive",
        "agent-notice", "install-health-schedule", "remove-health-schedule",
        "eval", "verify-install", "auto-tune",
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
    parser.add_argument("--min-samples", type=int, default=5,
                        help="Minimum history samples before auto-tune writes policy")
    parser.add_argument("--write-auto-policy", action="store_true",
                        help="Write .cold-review-policy.auto.yml for auto-tune")
    parser.add_argument("--auto-policy-path", default=None,
                        help="Override output path for auto-tune policy")
    parser.add_argument("--by-reason", action="store_true",
                        help="Include override reason breakdown in stats")
    parser.add_argument("--by-path", action="store_true",
                        help="Include per-path breakdown in stats")
    parser.add_argument("--reason", default=None,
                        help="Override reason for arm-override")
    parser.add_argument("--note", default=None,
                        help="Optional human note for arm-override")
    parser.add_argument("--ttl", type=int, default=10,
                        help="Token TTL in minutes for arm-override (default: 10)")
    parser.add_argument("--fix", action="store_true",
                        help="Auto-fix safe issues (for doctor command)")
    parser.add_argument("--profile", default="gate",
                        choices=["default", "gate"],
                        help="Init profile (gate by default; default keeps a minimal policy)")
    parser.add_argument("--force", action="store_true",
                        help="Overwrite existing policy when used with init")
    parser.add_argument("--keep-days", type=int, default=None,
                        help="Keep entries from last N days (for history-prune)")
    parser.add_argument("--keep-entries", type=int, default=None,
                        help="Keep most recent N entries (for history-prune)")
    parser.add_argument("--before", default=None,
                        help="Archive entries before date YYYY-MM-DD (for history-archive)")
    parser.add_argument("--stale-after-hours", type=float, default=0,
                        help="Optional age threshold for status health checks")
    parser.add_argument("--human", action="store_true",
                        help="Print a short human-readable status")
    parser.add_argument("--repo-root", default=None,
                        help="Repository root for health notice commands")
    parser.add_argument("--scripts-dir", default=None,
                        help="Installed scripts directory for schedule commands")
    parser.add_argument("--notice-dir", default=None,
                        help="Directory for agent notice files")
    parser.add_argument("--write", action="store_true",
                        help="Write agent notice file when used with agent-notice")
    parser.add_argument("--only-problem", action="store_true",
                        help="Emit agent notice only when attention is needed")
    parser.add_argument("--every-days", type=int, default=7,
                        help="Health schedule interval in days (default: 7)")
    parser.add_argument("--time", default="09:00",
                        help="Health schedule local time HH:MM (default: 09:00)")
    parser.add_argument("--task-name", default=None,
                        help="Windows scheduled task name for health notices")
    parser.add_argument("--shallow-model", default=None,
                        help="Model for shallow reviews (default: sonnet)")
    parser.add_argument("--context-tokens", type=int, default=None,
                        help="Token budget for context retrieval in deep reviews (default: 2000)")
    parser.add_argument("--max-input-tokens", type=int, default=None,
                        help="Total token cap for model input: diff + context + hints")
    parser.add_argument("--truncation-policy", default=None,
                        choices=["warn", "soft-pass", "fail-closed"],
                        help="How to handle truncated diffs (default: warn)")
    parser.add_argument("--minimum-coverage-pct", type=int, default=None,
                        help="Minimum reviewed file coverage percentage")
    parser.add_argument("--coverage-policy", default=None,
                        choices=["warn", "block", "fail-closed"],
                        help="How incomplete coverage is handled")
    parser.add_argument("--dirty-worktree-policy", default=None,
                        choices=["ignore", "warn", "block-high-risk", "block"],
                        help="How unstaged files outside the review target are handled")
    parser.add_argument("--untracked-policy", default=None,
                        choices=["ignore", "warn", "block-high-risk", "block"],
                        help="How untracked files outside the review target are handled")
    parser.add_argument("--partial-stage-policy", default=None,
                        choices=["ignore", "warn", "block-high-risk", "block"],
                        help="How partially staged files are handled")
    parser.add_argument("--fail-on-unreviewed-high-risk",
                        action="store_true", default=None,
                        help="Block if a high-risk file was not fully reviewed")
    parser.add_argument("--checks", default=None, choices=["auto", "off"],
                        help="Run automatic local checks when useful (default: auto)")
    parser.add_argument("--check-timeout-sec", type=int, default=None,
                        help="Timeout per local check in seconds (default: 120)")
    parser.add_argument("--hook-input-path", default=None,
                        help=argparse.SUPPRESS)
    parser.add_argument("--v2", action="store_true",
                        help=argparse.SUPPRESS)
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

    if getattr(args, "v2", False):
        print("warning: --v2 is retired; using unified v1", file=sys.stderr)

    if args.command == "init":
        result = run_init(profile=args.profile, force=args.force)
    elif args.command == "doctor":
        result = run_doctor_fix() if args.fix else run_doctor()
    elif args.command == "aggregate-overrides":
        result = aggregate_overrides()
    elif args.command == "stats":
        result = compute_stats(last=args.last, by_reason=args.by_reason,
                               by_path=args.by_path)
    elif args.command == "quality-report":
        result = quality_report(last=args.last)
    elif args.command == "status":
        result = runtime_status(stale_after_hours=args.stale_after_hours)
        if args.human:
            print(format_human_status(result, run_doctor()))
            return
    elif args.command == "agent-notice":
        result = agent_notice(
            repo_root=args.repo_root,
            notice_dir=args.notice_dir,
            write=args.write,
            only_problem=args.only_problem,
        )
    elif args.command == "install-health-schedule":
        schedule_kwargs = {
            "repo_root": args.repo_root,
            "scripts_dir": args.scripts_dir,
            "every_days": args.every_days,
            "time_of_day": args.time,
        }
        if args.task_name:
            schedule_kwargs["task_name"] = args.task_name
        result = install_health_schedule(**schedule_kwargs)
    elif args.command == "remove-health-schedule":
        schedule_kwargs = {"scripts_dir": args.scripts_dir}
        if args.task_name:
            schedule_kwargs["task_name"] = args.task_name
        result = remove_health_schedule(**schedule_kwargs)
    elif args.command == "auto-tune":
        from cold_eyes.autotune import auto_tune
        from cold_eyes.git import git_cmd, GitCommandError
        try:
            repo_root = git_cmd("rev-parse", "--show-toplevel")
        except GitCommandError:
            repo_root = os.getcwd()
        result = auto_tune(
            last=args.last,
            min_samples=args.min_samples,
            repo_root=repo_root,
            write=args.write_auto_policy,
            output_path=args.auto_policy_path,
        )
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
        result = arm_override(repo_root, reason, ttl_minutes=args.ttl,
                              note=args.note or "")
    elif args.command == "eval":
        from evals.eval_runner import (
            run_deterministic, run_benchmark, threshold_sweep,
            save_report, compare_reports, regression_check,
        )
        cases_dir = args.cases_dir or os.path.join(_root, "evals", "cases")
        regression_path = getattr(args, "regression_check", None)
        if regression_path:
            if args.save or args.compare:
                print("warning: --save and --compare are ignored when --regression-check is used "
                      "(regression-check exits early)", file=sys.stderr)
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
        result = run(mode=args.mode, model=args.model,
                     max_tokens=args.max_tokens, threshold=args.threshold,
                     confidence=args.confidence, language=args.language,
                     scope=args.scope, base=args.base,
                     override_reason=args.override_reason,
                     truncation_policy=args.truncation_policy,
                     shallow_model=args.shallow_model,
                     context_tokens=args.context_tokens,
                     max_input_tokens=args.max_input_tokens,
                     minimum_coverage_pct=args.minimum_coverage_pct,
                     coverage_policy=args.coverage_policy,
                     fail_on_unreviewed_high_risk=args.fail_on_unreviewed_high_risk,
                     hook_input_path=args.hook_input_path,
                     checks=args.checks,
                     check_timeout_sec=args.check_timeout_sec,
                     dirty_worktree_policy=args.dirty_worktree_policy,
                     untracked_policy=args.untracked_policy,
                     partial_stage_policy=args.partial_stage_policy)
        result = _attach_auto_tune(result)
    print(json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    main()
