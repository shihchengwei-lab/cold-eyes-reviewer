"""Review depth triage — skip / shallow / deep classification."""

import re

from cold_eyes.constants import RISK_CATEGORIES

# File role patterns — first match wins.
_ROLE_PATTERNS = [
    ("test", re.compile(
        r"(^|[/\\])(tests?[/\\]|test_|spec[/\\])|_test\.py$", re.IGNORECASE)),
    ("docs", re.compile(
        r"\.md$|(^|[/\\])(docs[/\\]|README|CHANGELOG)", re.IGNORECASE)),
    ("config", re.compile(
        r"\.(yml|yaml|toml)$|(^|[/\\])\.env", re.IGNORECASE)),
    ("generated", re.compile(
        r"\.min\.(js|css)$|\.pb\.go$|_generated\.|"
        r"(^|[/\\])dist[/\\]", re.IGNORECASE)),
    ("migration", re.compile(
        r"(^|[/\\])(migrations?[/\\]|alembic[/\\])|[/\\]migrate[/\\]",
        re.IGNORECASE)),
]


def classify_file_role(path):
    """Classify a file path into a role.

    Returns one of: test, docs, config, generated, migration, source.
    """
    normalized = path.replace("\\", "/")

    # Root-level .json → config
    if "/" not in normalized and normalized.endswith(".json"):
        return "config"

    for role, pattern in _ROLE_PATTERNS:
        if pattern.search(normalized):
            return role

    return "source"


def classify_depth(files, diff_meta=None):
    """Classify review depth from file list and optional metadata.

    Args:
        files: ranked file paths.
        diff_meta: optional dict (reserved for future 'total_lines' hint).

    Returns dict with review_depth, why_depth_selected, risk_types.
    """
    if not files:
        return {
            "review_depth": "skip",
            "why_depth_selected": "no files to review",
            "risk_types": [],
        }

    roles = [classify_file_role(f) for f in files]
    role_set = set(roles)

    risk_types = set()
    for f in files:
        n = f.replace("\\", "/")
        for cat, pattern in RISK_CATEGORIES.items():
            if pattern.search(n):
                risk_types.add(cat)
    risk_list = sorted(risk_types)

    # Skip: all files are docs / generated / config (unless secrets keywords)
    skip_roles = {"docs", "generated", "config"}
    if role_set <= skip_roles:
        if "secrets_privacy" in risk_types:
            return {
                "review_depth": "deep",
                "why_depth_selected": "config with secrets-related keywords",
                "risk_types": risk_list,
            }
        return {
            "review_depth": "skip",
            "why_depth_selected": f"all files are {'/'.join(sorted(role_set))}",
            "risk_types": risk_list,
        }

    # Deep: any risk category hit
    if risk_types:
        return {
            "review_depth": "deep",
            "why_depth_selected": (
                f"risk categories: {', '.join(risk_list)}"),
            "risk_types": risk_list,
        }

    # Deep: migration or source files
    if role_set & {"migration", "source"}:
        deep_roles = sorted(role_set & {"migration", "source"})
        return {
            "review_depth": "deep",
            "why_depth_selected": f"contains {'/'.join(deep_roles)} files",
            "risk_types": risk_list,
        }

    # Shallow: test-only or other non-critical
    return {
        "review_depth": "shallow",
        "why_depth_selected": (
            f"non-critical files only ({'/'.join(sorted(role_set))})"),
        "risk_types": risk_list,
    }
