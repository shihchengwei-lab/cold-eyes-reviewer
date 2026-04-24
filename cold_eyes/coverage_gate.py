"""Coverage gate decisions for incomplete review visibility."""

from __future__ import annotations

from cold_eyes.constants import RISK_PATTERN

VALID_COVERAGE_POLICIES = {"warn", "block", "fail-closed"}


def normalize_coverage_policy(value: str | None) -> str:
    """Return a supported coverage policy, defaulting to warn."""
    if not value:
        return "warn"
    value = str(value).strip().lower()
    return value if value in VALID_COVERAGE_POLICIES else "warn"


def is_truthy(value) -> bool:
    """Parse common policy/env truthy strings."""
    if isinstance(value, bool):
        return value
    if value is None:
        return False
    return str(value).strip().lower() in {"1", "true", "yes", "on"}


def evaluate_coverage(
    coverage_pct: float,
    unreviewed_files: list[str],
    unreviewed_high_risk_files: list[str],
    minimum_coverage_pct: int | None,
    coverage_policy: str,
    fail_on_unreviewed_high_risk: bool,
) -> dict:
    """Evaluate coverage policy and return a compact decision dict."""
    policy = normalize_coverage_policy(coverage_policy)
    action = "pass"
    reason = ""

    if fail_on_unreviewed_high_risk and unreviewed_high_risk_files:
        action = "block"
        reason = "high_risk_files_unreviewed"
    elif minimum_coverage_pct is not None and coverage_pct < minimum_coverage_pct:
        reason = "coverage_below_minimum"
        action = "block" if policy in {"block", "fail-closed"} else "warn"
    elif unreviewed_files and policy == "fail-closed":
        action = "block"
        reason = "unreviewed_files_present"

    return {
        "policy": policy,
        "action": action,
        "reason": reason,
    }


def build_coverage_report(
    ranked_files: list[str],
    diff_meta: dict,
    minimum_coverage_pct: int | None,
    coverage_policy: str,
    fail_on_unreviewed_high_risk: bool,
) -> dict:
    """Build the normalized coverage report from diff metadata."""
    partial_files = list(diff_meta.get("partial_files", []))
    skipped_budget = list(diff_meta.get("skipped_budget", []))
    skipped_binary = list(diff_meta.get("skipped_binary", []))
    skipped_unreadable = list(diff_meta.get("skipped_unreadable", []))

    unreviewed_files = _dedupe(
        partial_files + skipped_budget + skipped_binary + skipped_unreadable
    )
    total_files = len(ranked_files)
    file_count = int(diff_meta.get("file_count", 0) or 0)
    reviewed_files = max(file_count - len(partial_files), 0)
    coverage_pct = round(reviewed_files / total_files * 100, 1) if total_files else 100.0
    unreviewed_high_risk_files = [
        path for path in unreviewed_files if RISK_PATTERN.search(path or "")
    ]

    decision = evaluate_coverage(
        coverage_pct=coverage_pct,
        unreviewed_files=unreviewed_files,
        unreviewed_high_risk_files=unreviewed_high_risk_files,
        minimum_coverage_pct=minimum_coverage_pct,
        coverage_policy=coverage_policy,
        fail_on_unreviewed_high_risk=fail_on_unreviewed_high_risk,
    )

    status = "complete"
    if unreviewed_files:
        status = "partial"
    if minimum_coverage_pct is not None and coverage_pct < minimum_coverage_pct:
        status = "insufficient"

    return {
        "status": status,
        "coverage_pct": coverage_pct,
        "reviewed_files": reviewed_files,
        "total_files": total_files,
        "unreviewed_files": unreviewed_files,
        "unreviewed_high_risk_files": unreviewed_high_risk_files,
        "partial_files": partial_files,
        "skipped_budget": skipped_budget,
        "skipped_binary": skipped_binary,
        "skipped_unreadable": skipped_unreadable,
        "minimum_coverage_pct": minimum_coverage_pct,
        "fail_on_unreviewed_high_risk": bool(fail_on_unreviewed_high_risk),
        **decision,
    }


def format_coverage_block_reason(coverage: dict) -> str:
    """Format a Claude-actionable coverage block reason."""
    minimum = coverage.get("minimum_coverage_pct")
    lines = [
        "Cold Eyes blocked this change because review coverage was incomplete.",
        "",
        f"Coverage: {coverage.get('coverage_pct', 0.0)}%",
    ]
    if minimum is not None:
        lines.append(f"Minimum required: {minimum}%")

    unreviewed = coverage.get("unreviewed_files", [])
    if unreviewed:
        lines.extend(["", "Unreviewed files:"])
        lines.extend(f"- {path}" for path in unreviewed)

    high_risk = coverage.get("unreviewed_high_risk_files", [])
    if high_risk:
        lines.extend(["", "Unreviewed high-risk files:"])
        lines.extend(f"- {path}" for path in high_risk)

    reason = coverage.get("reason")
    if reason:
        lines.extend(["", f"Reason: {reason}."])

    lines.extend([
        "",
        "Suggested action:",
        "- Split the diff into smaller commits, or",
        "- Increase COLD_REVIEW_MAX_TOKENS, or",
        "- Review the unreviewed files manually and use a one-time override with reason.",
        "",
        "To override: python cli.py arm-override --reason '<reason>'",
    ])
    return "\n".join(lines)


def _dedupe(paths: list[str]) -> list[str]:
    seen = set()
    out = []
    for path in paths:
        if path in seen:
            continue
        seen.add(path)
        out.append(path)
    return out
