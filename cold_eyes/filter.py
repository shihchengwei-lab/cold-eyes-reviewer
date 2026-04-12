"""File filtering and risk ranking."""

import fnmatch
import os

from cold_eyes.constants import BUILTIN_IGNORE, RISK_PATTERN


def filter_file_list(files, ignore_file=""):
    """Apply built-in + custom ignore patterns. Return filtered list."""
    patterns = list(BUILTIN_IGNORE)
    if ignore_file and os.path.isfile(ignore_file):
        with open(ignore_file, "r", encoding="utf-8", errors="replace") as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#"):
                    patterns.append(line)
    result = []
    for fp in files:
        if not fp:
            continue
        if not any(
            fnmatch.fnmatch(fp, p) or fnmatch.fnmatch(os.path.basename(fp), p)
            for p in patterns
        ):
            result.append(fp)
    return result


def rank_file_list(files, untracked):
    """Sort files by risk score descending. Return ordered list."""
    scored = []
    for fp in files:
        if not fp:
            continue
        score = 1
        if RISK_PATTERN.search(fp):
            score += 3
        if fp in untracked:
            score += 2
        scored.append((score, fp))
    scored.sort(key=lambda x: (-x[0], x[1]))
    return [fp for _, fp in scored]
