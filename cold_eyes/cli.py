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
from cold_eyes.doctor import run_doctor
from cold_eyes.history import aggregate_overrides, compute_stats
from cold_eyes.override import arm_override


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Cold Eyes Reviewer engine")
    parser.add_argument("command", choices=["run", "doctor", "aggregate-overrides", "stats", "arm-override"])
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
    args = parser.parse_args()

    if args.command == "doctor":
        result = run_doctor()
    elif args.command == "aggregate-overrides":
        result = aggregate_overrides()
    elif args.command == "stats":
        result = compute_stats(last=args.last, by_reason=args.by_reason,
                               by_path=args.by_path)
    elif args.command == "arm-override":
        from cold_eyes.git import git_cmd, GitCommandError
        try:
            repo_root = git_cmd("rev-parse", "--show-toplevel")
        except GitCommandError:
            repo_root = os.getcwd()
        reason = args.reason or args.override_reason or ""
        result = arm_override(repo_root, reason, ttl_minutes=args.ttl)
    else:
        result = run(mode=args.mode, model=args.model,
                     max_tokens=args.max_tokens, threshold=args.threshold,
                     confidence=args.confidence, language=args.language,
                     scope=args.scope, base=args.base,
                     override_reason=args.override_reason)
    print(json.dumps(result, ensure_ascii=False))
