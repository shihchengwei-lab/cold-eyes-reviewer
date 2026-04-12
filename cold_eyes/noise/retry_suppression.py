"""Retry suppression — suppress findings already seen in previous iterations."""


def suppress_seen(
    findings: list[dict],
    previous_findings: list[dict],
) -> list[dict]:
    """Remove findings that were already reported in a previous iteration.

    Match by (type, file, check/code) tuple.
    Returns the filtered list plus a suppression summary.
    """
    prev_keys = {_suppress_key(f) for f in previous_findings}

    kept: list[dict] = []
    suppressed_count = 0

    for f in findings:
        if _suppress_key(f) in prev_keys:
            suppressed_count += 1
        else:
            kept.append(f)

    return kept


def suppress_seen_with_report(
    findings: list[dict],
    previous_findings: list[dict],
) -> tuple[list[dict], dict]:
    """Like suppress_seen but also returns a report dict."""
    prev_keys = {_suppress_key(f) for f in previous_findings}

    kept: list[dict] = []
    suppressed: list[dict] = []

    for f in findings:
        if _suppress_key(f) in prev_keys:
            suppressed.append(f)
        else:
            kept.append(f)

    report = {
        "total_input": len(findings),
        "kept": len(kept),
        "suppressed": len(suppressed),
        "suppressed_keys": [_suppress_key(f) for f in suppressed],
    }
    return kept, report


def _suppress_key(finding: dict) -> tuple:
    return (
        finding.get("type", ""),
        finding.get("file", finding.get("location", "")),
        finding.get("check", finding.get("code", "")),
    )
