"""Policy file loading — flat YAML subset parser (no PyYAML dependency).

Reads .cold-review-policy.yml from the repo root.  Only flat key: value
pairs are supported.  Forward-compatible with full YAML when PyYAML is added.
"""

import os
import sys

POLICY_FILENAME = ".cold-review-policy.yml"

# Keys we recognise and their expected types.
_INT_KEYS = {"max_tokens", "context_tokens", "max_input_tokens"}
_VALID_KEYS = {
    "mode", "model", "shallow_model", "max_tokens", "context_tokens",
    "max_input_tokens",
    "block_threshold", "threshold", "confidence", "language", "scope",
    "base", "truncation_policy",
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
    """
    if not repo_root:
        return {}
    path = os.path.join(repo_root, POLICY_FILENAME)
    if not os.path.isfile(path):
        return {}
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
                policy[canon] = int(val)
            except ValueError:
                continue
        else:
            if val:  # skip empty values
                policy[canon] = val
    return policy
