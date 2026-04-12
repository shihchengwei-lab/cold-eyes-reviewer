"""FP memory integration — thin wrapper around v1 memory.py for v2 findings."""

try:
    from cold_eyes.memory import extract_fp_patterns, match_fp_pattern
    _HAS_MEMORY = True
except ImportError:
    _HAS_MEMORY = False


def apply_fp_memory(
    findings: list[dict],
    history_path: str | None = None,
) -> list[dict]:
    """Annotate or remove findings that match known FP patterns.

    Each finding gets ``fp_match_count`` and ``fp_matched_types`` fields.
    Findings with 2+ FP matches are removed.

    If memory module is unavailable, returns findings unchanged.
    """
    if not _HAS_MEMORY:
        return findings

    fp_patterns = extract_fp_patterns(history_path=history_path)
    if not fp_patterns or fp_patterns.get("total_overrides", 0) == 0:
        return findings

    result: list[dict] = []
    for f in findings:
        # Convert v2 finding to v1 issue format for matching
        issue = _to_v1_issue(f)
        match_count, matched_types = match_fp_pattern(issue, fp_patterns)
        f = dict(f)  # copy to avoid mutating original
        f["fp_match_count"] = match_count
        f["fp_matched_types"] = matched_types
        if match_count < 2:
            result.append(f)

    return result


def _to_v1_issue(finding: dict) -> dict:
    """Convert a v2 finding dict to v1 issue format for FP matching."""
    return {
        "check": finding.get("check", finding.get("code", "")),
        "file": finding.get("file", finding.get("location", "")),
        "category": finding.get("category", "correctness"),
        "severity": finding.get("severity", "major"),
        "confidence": finding.get("confidence", "medium"),
    }
