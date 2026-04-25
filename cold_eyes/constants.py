"""Shared constants — single source of truth for all modules."""

import os
import re

_PKG_DIR = os.path.dirname(os.path.abspath(__file__))
SCRIPTS_DIR = os.path.dirname(_PKG_DIR)

PROMPT_TEMPLATE = os.path.join(SCRIPTS_DIR, "cold-review-prompt.txt")
PROMPT_TEMPLATE_SHALLOW = os.path.join(SCRIPTS_DIR, "cold-review-prompt-shallow.txt")
HISTORY_FILE = os.path.join(
    os.path.expanduser("~"), ".claude", "cold-review-history.jsonl"
)

SCHEMA_VERSION = 1
SEVERITY_ORDER = {"critical": 3, "major": 2, "minor": 1}
CONFIDENCE_ORDER = {"high": 3, "medium": 2, "low": 1}

# Review outcome states — single source of truth for all modules.
STATE_PASSED = "passed"
STATE_BLOCKED = "blocked"
STATE_OVERRIDDEN = "overridden"
STATE_SKIPPED = "skipped"
STATE_INFRA_FAILED = "infra_failed"
STATE_REPORTED = "reported"

BUILTIN_IGNORE = [
    "*.lock", "package-lock.json", "pnpm-lock.yaml", "yarn.lock",
    "dist/*", "build/*", ".next/*", "coverage/*", "vendor/*",
    "node_modules/*", "*.min.js", "*.min.css", "*.map",
]

RISK_PATTERN = re.compile(
    r"(auth|payment|db|migration|secret|credential|config|api)", re.IGNORECASE
)

# Risk categories — structured classification for triage depth decisions.
RISK_CATEGORIES = {
    "auth_permission": re.compile(
        r"(auth|permission|guard|middleware|policy|ownership)", re.IGNORECASE),
    "state_invariant": re.compile(
        r"(state|status|transition|workflow|fsm)", re.IGNORECASE),
    "migration_schema": re.compile(
        r"(migration|schema|ddl|alter)", re.IGNORECASE),
    "persistence": re.compile(
        r"(db|database|repository|orm|query)", re.IGNORECASE),
    "public_api": re.compile(
        r"(api|endpoint|route|handler|controller)", re.IGNORECASE),
    "async_concurrency": re.compile(
        r"(async|await|thread|lock|mutex|queue|(?<!service[-_])worker)",
        re.IGNORECASE),
    "secrets_privacy": re.compile(
        r"(secret|credential|password|token(?!iz)|key(?!board|frame|stone|press|word|note|map|bind|stroke)|env(?!iron))",
        re.IGNORECASE),
    "cache_retry": re.compile(
        r"(cache|retry|timeout|circuit.?breaker)", re.IGNORECASE),
}

DEPLOY_FILES = [
    "cold-review.sh", "cold-review-prompt.txt",
    "cold_eyes/__init__.py", "cold_eyes/cli.py", "cold_eyes/engine.py",
    "cold_eyes/constants.py", "cold_eyes/git.py", "cold_eyes/filter.py",
    "cold_eyes/prompt.py", "cold_eyes/claude.py", "cold_eyes/review.py",
    "cold_eyes/policy.py", "cold_eyes/history.py", "cold_eyes/config.py",
    "cold_eyes/autotune.py",
    "cold_eyes/override.py", "cold_eyes/doctor.py",
    "cold_eyes/schema.py", "cold_eyes/triage.py",
    "cold_eyes/context.py", "cold_eyes/detector.py",
    "cold_eyes/memory.py",
    "cold_eyes/coverage_gate.py",
    "cold-review-prompt-shallow.txt",
    # v2 sub-packages
    "cold_eyes/type_defs.py",
    "cold_eyes/session/__init__.py", "cold_eyes/session/schema.py",
    "cold_eyes/session/store.py", "cold_eyes/session/state_machine.py",
    "cold_eyes/contract/__init__.py", "cold_eyes/contract/schema.py",
    "cold_eyes/contract/generator.py", "cold_eyes/contract/quality_checker.py",
    "cold_eyes/gates/__init__.py", "cold_eyes/gates/catalog.py",
    "cold_eyes/gates/selection.py", "cold_eyes/gates/orchestrator.py",
    "cold_eyes/gates/result.py", "cold_eyes/gates/risk_classifier.py",
    "cold_eyes/retry/__init__.py", "cold_eyes/retry/taxonomy.py",
    "cold_eyes/retry/brief.py", "cold_eyes/retry/signal_parser.py",
    "cold_eyes/retry/translator.py", "cold_eyes/retry/strategy.py",
    "cold_eyes/retry/stop.py",
    "cold_eyes/noise/__init__.py", "cold_eyes/noise/dedup.py",
    "cold_eyes/noise/grouping.py", "cold_eyes/noise/retry_suppression.py",
    "cold_eyes/noise/fp_memory.py", "cold_eyes/noise/calibration.py",
    "cold_eyes/runner/__init__.py", "cold_eyes/runner/session_runner.py",
    "cold_eyes/runner/metrics.py",
]
