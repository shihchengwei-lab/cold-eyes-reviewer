"""False-positive memory — extract override patterns from history."""

import json
import os
from collections import Counter
from datetime import datetime, timezone, timedelta

from cold_eyes import constants


def _read_overrides(history_path=None, last_days=None):
    """Read overridden entries from history JSONL.

    Returns list of history entries where state == overridden.
    """
    path = history_path or constants.HISTORY_FILE
    if not os.path.isfile(path):
        return []

    entries = []
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                entry = json.loads(line)
            except json.JSONDecodeError:
                continue
            if entry.get("state") != constants.STATE_OVERRIDDEN:
                continue
            entries.append(entry)

    if last_days is not None and last_days > 0:
        cutoff = datetime.now(timezone.utc) - timedelta(days=last_days)
        filtered = []
        for e in entries:
            ts = e.get("timestamp", "")
            try:
                t = datetime.fromisoformat(ts.replace("Z", "+00:00"))
                if t >= cutoff:
                    filtered.append(e)
            except (ValueError, TypeError):
                filtered.append(e)
        entries = filtered

    return entries


def _extract_issues_from_overrides(overrides):
    """Collect all issues from overridden review entries."""
    issues = []
    for entry in overrides:
        review = entry.get("review")
        if not review or not isinstance(review, dict):
            continue
        for issue in review.get("issues", []):
            if isinstance(issue, dict):
                issues.append(issue)
    return issues


def extract_fp_patterns(history_path=None, min_count=2, last_days=90):
    """Extract false-positive patterns from override history.

    Scans overridden entries for recurring category, path, and check patterns.

    Args:
        history_path: Path to history JSONL file.
        min_count: Minimum occurrences to qualify as a pattern.
        last_days: Only look at entries from the last N days (None = all).

    Returns dict:
        category_patterns: {category: count} for categories above min_count
        path_patterns:     {dir_prefix: count} for file dirs above min_count
        check_patterns:    {normalised_prefix: count} for claim prefixes above min_count
        total_overrides:   total override entries scanned
        total_issues:      total issues extracted
    """
    overrides = _read_overrides(history_path, last_days)
    issues = _extract_issues_from_overrides(overrides)

    # Category patterns
    cat_counter = Counter()
    for issue in issues:
        cat = issue.get("category")
        if cat:
            cat_counter[cat] += 1

    # Path patterns — group by directory prefix
    path_counter = Counter()
    for issue in issues:
        file_path = issue.get("file", "")
        if file_path and file_path != "unknown":
            dir_part = file_path.rsplit("/", 1)[0] if "/" in file_path else ""
            # Also try backslash for Windows paths
            if not dir_part and "\\" in file_path:
                dir_part = file_path.rsplit("\\", 1)[0]
            if dir_part:
                path_counter[dir_part] += 1

    # Check patterns — normalise to first 8 words (lowercase)
    check_counter = Counter()
    for issue in issues:
        check = issue.get("check", "")
        if check:
            words = check.lower().split()[:8]
            prefix = " ".join(words)
            if prefix:
                check_counter[prefix] += 1

    def _above_threshold(counter):
        return {k: v for k, v in counter.most_common() if v >= min_count}

    return {
        "category_patterns": _above_threshold(cat_counter),
        "path_patterns": _above_threshold(path_counter),
        "check_patterns": _above_threshold(check_counter),
        "total_overrides": len(overrides),
        "total_issues": len(issues),
    }


def match_fp_pattern(issue, fp_patterns):
    """Check if an issue matches known false-positive patterns.

    Returns (match_count, matched_types) where:
        match_count: number of pattern types matched (0-3)
        matched_types: list of matched type names
    """
    if not fp_patterns or not issue:
        return 0, []

    matched = []

    # Category match
    cat = issue.get("category", "")
    if cat and cat in fp_patterns.get("category_patterns", {}):
        matched.append("category")

    # Path match — issue file starts with a known FP directory
    file_path = issue.get("file", "")
    if file_path and file_path != "unknown":
        for dir_prefix in fp_patterns.get("path_patterns", {}):
            normalised = file_path.replace("\\", "/")
            if normalised.startswith(dir_prefix.replace("\\", "/") + "/") or normalised == dir_prefix:
                matched.append("path")
                break

    # Check prefix match
    check = issue.get("check", "")
    if check:
        words = check.lower().split()[:8]
        prefix = " ".join(words)
        for known_prefix in fp_patterns.get("check_patterns", {}):
            if prefix == known_prefix or prefix.startswith(known_prefix):
                matched.append("check")
                break

    return len(matched), matched


def compute_category_baselines(fp_patterns, total_reviews=None):
    """Compute per-category confidence caps from FP patterns.

    Categories that appear frequently in overrides relative to total reviews
    get a confidence cap:
      - override ratio >= 0.5 → cap at "low"
      - override ratio >= 0.3 → cap at "medium"
      - otherwise → no cap (None)

    If total_reviews is not provided, uses total_overrides * 3 as estimate
    (assuming roughly 1/3 of reviews are overridden at most).

    Args:
        fp_patterns: output of extract_fp_patterns()
        total_reviews: total review count for ratio calculation

    Returns dict: {category: confidence_cap} (only categories with caps)
    """
    if not fp_patterns:
        return {}

    cat_patterns = fp_patterns.get("category_patterns", {})
    if not cat_patterns:
        return {}

    total = total_reviews or max(fp_patterns.get("total_overrides", 0) * 3, 1)

    caps = {}
    for cat, count in cat_patterns.items():
        ratio = count / total
        if ratio >= 0.5:
            caps[cat] = "low"
        elif ratio >= 0.3:
            caps[cat] = "medium"

    return caps
