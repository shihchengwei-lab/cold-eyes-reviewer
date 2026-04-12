"""Duplicate failure merger — combine obviously identical findings."""


def merge_duplicates(findings: list[dict]) -> list[dict]:
    """Merge findings that share the same (gate, file, check/code) key.

    Returns a de-duplicated list.  Each merged finding gets a ``count``
    field and ``supporting`` list of original messages.
    """
    buckets: dict[tuple, dict] = {}

    for f in findings:
        key = _dedup_key(f)
        if key in buckets:
            buckets[key]["count"] += 1
            msg = f.get("message", "")
            if msg and msg not in buckets[key]["supporting"]:
                buckets[key]["supporting"].append(msg)
        else:
            merged = dict(f)
            merged["count"] = 1
            merged["supporting"] = []
            buckets[key] = merged

    return list(buckets.values())


def _dedup_key(finding: dict) -> tuple:
    """Build a hashable key for deduplication."""
    return (
        finding.get("type", ""),
        finding.get("file", finding.get("location", "")),
        finding.get("check", finding.get("code", "")),
    )
