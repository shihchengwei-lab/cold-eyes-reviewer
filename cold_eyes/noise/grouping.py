"""Root-cause grouping — cluster related findings by probable cause."""

from cold_eyes.type_defs import FindingCluster, generate_id


def group_by_root_cause(findings: list[dict]) -> list[dict]:
    """Group findings that likely share a common root cause.

    Heuristics:
    - Same file within 20 lines of each other
    - Same check/code across multiple files (likely one fix)

    Returns list of FindingCluster dicts.
    """
    if not findings:
        return []

    clusters: list[dict] = []
    used: set[int] = set()

    # Pass 1: group by same file + proximity
    by_file: dict[str, list[tuple[int, dict]]] = {}
    for i, f in enumerate(findings):
        file_ = f.get("file", f.get("location", ""))
        if file_:
            by_file.setdefault(file_, []).append((i, f))

    for file_, group in by_file.items():
        if len(group) < 2:
            continue
        # Sort by line number if available
        sorted_group = sorted(group, key=lambda x: _get_line(x[1]))
        cluster_findings: list[tuple[int, dict]] = [sorted_group[0]]
        for j in range(1, len(sorted_group)):
            prev_line = _get_line(cluster_findings[-1][1])
            curr_line = _get_line(sorted_group[j][1])
            if curr_line - prev_line <= 20:
                cluster_findings.append(sorted_group[j])
            else:
                if len(cluster_findings) >= 2:
                    _emit_cluster(clusters, cluster_findings, file_, used)
                cluster_findings = [sorted_group[j]]
        if len(cluster_findings) >= 2:
            _emit_cluster(clusters, cluster_findings, file_, used)

    # Pass 2: group by same check/code across files
    by_check: dict[str, list[tuple[int, dict]]] = {}
    for i, f in enumerate(findings):
        if i in used:
            continue
        check = f.get("check", f.get("code", ""))
        if check:
            by_check.setdefault(check, []).append((i, f))

    for check, group in by_check.items():
        if len(group) >= 2:
            idxs = [i for i, _ in group]
            affected = list({f.get("file", f.get("location", "")) for _, f in group})
            clusters.append(FindingCluster(
                cluster_id=generate_id(),
                probable_root_cause=f"repeated check: {check}",
                supporting_signals=[f.get("message", "") for _, f in group if f.get("message")],
                affected_files=affected,
                recommended_fix_scope=f"fix root cause of {check}",
                confidence="medium",
            ))
            used.update(idxs)

    # Pass 3: remaining unclustered findings become singleton clusters
    for i, f in enumerate(findings):
        if i not in used:
            clusters.append(FindingCluster(
                cluster_id=generate_id(),
                probable_root_cause=f.get("message", f.get("check", "unknown")),
                supporting_signals=[],
                affected_files=[f.get("file", f.get("location", ""))],
                recommended_fix_scope="inspect finding directly",
                confidence="low",
            ))

    return clusters


def _get_line(finding: dict) -> int:
    try:
        return int(finding.get("line", 0))
    except (ValueError, TypeError):
        return 0


def _emit_cluster(clusters, items, file_, used):
    idxs = [i for i, _ in items]
    signals = [f.get("message", "") for _, f in items if f.get("message")]
    clusters.append(FindingCluster(
        cluster_id=generate_id(),
        probable_root_cause=f"multiple issues in {file_} (lines {_get_line(items[0][1])}-{_get_line(items[-1][1])})",
        supporting_signals=signals,
        affected_files=[file_],
        recommended_fix_scope=f"review {file_} around affected lines",
        confidence="medium",
    ))
    used.update(idxs)
