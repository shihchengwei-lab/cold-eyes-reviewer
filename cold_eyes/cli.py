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
from cold_eyes.history import aggregate_overrides


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
