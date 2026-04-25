"""Policy file loading — flat YAML subset parser (no PyYAML dependency).

Reads .cold-review-policy.yml from the repo root.  Only flat key: value
pairs are supported.  Forward-compatible with full YAML when PyYAML is added.
"""

import os
import sys
import hashlib

POLICY_FILENAME = ".cold-review-policy.yml"
AUTO_POLICY_FILENAME = ".cold-review-policy.auto.yml"
AUTO_POLICY_DIR = os.path.join(
    os.path.expanduser("~"), ".claude", "cold-review-auto-policies"
)

# Keys we recognise and their expected types.
_INT_KEYS = {
    "max_tokens", "context_tokens", "max_input_tokens",
    "minimum_coverage_pct", "check_timeout_sec",
}
_BOOL_KEYS = {"fail_on_unreviewed_high_risk"}
_VALUE_SETS = {
    "coverage_policy": {"warn", "block", "fail-closed"},
    "checks": {"auto", "off"},
    "dirty_worktree_policy": {"ignore", "warn", "block-high-risk", "block"},
    "untracked_policy": {"ignore", "warn", "block-high-risk", "block"},
    "partial_stage_policy": {"ignore", "warn", "block-high-risk", "block"},
}
_VALID_KEYS = {
    "mode", "model", "shallow_model", "max_tokens", "context_tokens",
    "max_input_tokens",
    "block_threshold", "threshold", "confidence", "language", "scope",
    "base", "truncation_policy", "minimum_coverage_pct", "coverage_policy",
    "fail_on_unreviewed_high_risk", "checks", "check_timeout_sec",
    "dirty_worktree_policy", "untracked_policy", "partial_stage_policy",
}


_MAX_POLICY_LINES = 50


def _parse_flat_yaml(text):
    """Parse a flat key: value YAML file. Returns dict of string values."""
    result = {}
    content_lines = 0
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        content_lines += 1
        if content_lines > _MAX_POLICY_LINES:
            print(
                f"cold-review: policy file exceeds {_MAX_POLICY_LINES} "
                "content lines, ignoring remaining entries",
                file=sys.stderr,
            )
            break
        colon = stripped.find(":")
        if colon < 1:
            continue
        key = stripped[:colon].strip()
        val = stripped[colon + 1:].strip()
        # Strip optional surrounding quotes
        if len(val) >= 2 and val[0] == val[-1] and val[0] in ('"', "'"):
            val = val[1:-1]
        result[key] = val
    return result


def load_policy(repo_root):
    """Load policy from repo_root/.cold-review-policy.yml.

    Returns a dict with recognised keys only.  Unknown keys are silently
    ignored.  Returns {} if the file does not exist or is unreadable.

    ``threshold`` is accepted as an alias for ``block_threshold``.
    Integer keys (max_tokens) are converted; invalid values are dropped.
    Auto policy files are loaded first as low-priority tuning layers. Explicit
    values in .cold-review-policy.yml always win.
    """
    if not repo_root:
        return {}
    policy = {}
    paths = [
        user_auto_policy_path(repo_root),
        os.path.join(repo_root, AUTO_POLICY_FILENAME),
        os.path.join(repo_root, POLICY_FILENAME),
    ]
    for path in paths:
        if not os.path.isfile(path):
            continue
        policy.update(_load_policy_file(path))
    return policy


def user_auto_policy_path(repo_root):
    """Return the home-scoped auto policy path for a repo root."""
    key = _repo_key(repo_root)
    return os.path.join(AUTO_POLICY_DIR, f"{key}.yml")


def _repo_key(repo_root):
    root = os.path.abspath(repo_root or "")
    digest = hashlib.sha256(root.lower().encode("utf-8")).hexdigest()
    return digest[:16]


def _load_policy_file(path):
    try:
        with open(path, "r", encoding="utf-8") as f:
            raw = _parse_flat_yaml(f.read())
    except (OSError, UnicodeDecodeError):
        return {}

    policy = {}
    for key, val in raw.items():
        if key not in _VALID_KEYS:
            continue
        # Normalise alias
        canon = "block_threshold" if key == "threshold" else key
        # Type conversion
        if canon in _INT_KEYS:
            try:
                parsed = int(str(val).replace("_", ""))
            except (ValueError, TypeError):
                continue
            if canon == "minimum_coverage_pct" and not (0 <= parsed <= 100):
                continue
            policy[canon] = parsed
        elif canon in _BOOL_KEYS:
            parsed = _parse_bool(val)
            if parsed is None:
                continue
            policy[canon] = parsed
        elif canon in _VALUE_SETS:
            val = str(val).strip().lower()
            if val in _VALUE_SETS[canon]:
                policy[canon] = val
        else:
            if val:  # skip empty values
                policy[canon] = val
    return policy


def _parse_bool(val):
    low = str(val).strip().lower()
    if low in {"1", "true", "yes", "on"}:
        return True
    if low in {"0", "false", "no", "off"}:
        return False
    return None
