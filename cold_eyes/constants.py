"""Shared constants — single source of truth for all modules."""

import os
import re

_PKG_DIR = os.path.dirname(os.path.abspath(__file__))
SCRIPTS_DIR = os.path.dirname(_PKG_DIR)

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
    "cold-review.sh", "cold-review-prompt.txt",
    "cold_eyes/cli.py", "cold_eyes/engine.py", "cold_eyes/constants.py",
]
