"""Review-target inspection and policy decisions."""

from __future__ import annotations

from cold_eyes.constants import RISK_PATTERN
from cold_eyes.filter import filter_file_list
from cold_eyes.git import git_cmd


VALID_TARGET_POLICIES = {"ignore", "warn", "block-high-risk", "block"}


def normalize_target_policy(value: str | None, default: str = "warn") -> str:
    """Return a supported target policy."""
    if not value:
        return default
    value = str(value).strip().lower()
    return value if value in VALID_TARGET_POLICIES else default


def inspect_review_target(
    scope: str = "staged",
    ignore_file: str = "",
    review_files: list[str] | None = None,
) -> dict:
    """Inspect what the configured review scope sees and misses."""
    scope = (scope or "staged").strip().lower()
    staged = _filtered_paths(_git_lines("diff", "--cached", "--name-only"), ignore_file)
    unstaged = _filtered_paths(_git_lines("diff", "--name-only"), ignore_file)
    untracked = _filtered_paths(
        _git_lines("ls-files", "--others", "--exclude-standard", "--full-name"),
        ignore_file,
    )

    if review_files is None:
        review_files = _review_files_for_scope(scope, staged, unstaged, untracked)
    review_files = sorted(dict.fromkeys(review_files))

    partial_stage = sorted(set(staged) & set(unstaged))
    if scope == "working":
        unreviewed_unstaged: list[str] = []
        unreviewed_untracked: list[str] = []
        unreviewed_partial: list[str] = []
    elif scope == "head":
        unreviewed_unstaged = []
        unreviewed_untracked = list(untracked)
        unreviewed_partial = []
    elif scope == "staged":
        unreviewed_unstaged = list(unstaged)
        unreviewed_untracked = list(untracked)
        unreviewed_partial = list(partial_stage)
    else:
        # pr-diff and future non-working scopes review a configured branch target;
        # local uncommitted files are visible as "not reviewed" context.
        unreviewed_unstaged = list(unstaged)
        unreviewed_untracked = list(untracked)
        unreviewed_partial = list(partial_stage)

    unreviewed = _dedupe(unreviewed_unstaged + unreviewed_untracked)
    high_risk_unreviewed = [path for path in unreviewed if _high_risk(path)]
    high_risk_partial = [path for path in unreviewed_partial if _high_risk(path)]
    target_integrity = _target_integrity(
        review_files=review_files,
        unreviewed=unreviewed,
        partial_stage=unreviewed_partial,
    )

    return {
        "scope": scope,
        "review_files": review_files,
        "review_file_count": len(review_files),
        "staged_files": staged,
        "staged_count": len(staged),
        "unstaged_files": unstaged,
        "unstaged_count": len(unstaged),
        "untracked_files": untracked,
        "untracked_count": len(untracked),
        "partial_stage_files": partial_stage,
        "partial_stage_count": len(partial_stage),
        "unreviewed_unstaged_files": unreviewed_unstaged,
        "unreviewed_untracked_files": unreviewed_untracked,
        "unreviewed_partial_stage_files": unreviewed_partial,
        "unreviewed_files": unreviewed,
        "unreviewed_count": len(unreviewed),
        "high_risk_unreviewed_files": high_risk_unreviewed,
        "high_risk_unreviewed_count": len(high_risk_unreviewed),
        "high_risk_partial_stage_files": high_risk_partial,
        "high_risk_partial_stage_count": len(high_risk_partial),
        "target_integrity": target_integrity,
    }


def evaluate_target_policy(
    target: dict,
    *,
    dirty_worktree_policy: str = "warn",
    untracked_policy: str = "warn",
    partial_stage_policy: str = "block-high-risk",
) -> dict:
    """Evaluate target-integrity policy and return pass/warn/block."""
    dirty_policy = normalize_target_policy(dirty_worktree_policy, "warn")
    untracked_policy = normalize_target_policy(untracked_policy, "warn")
    partial_policy = normalize_target_policy(partial_stage_policy, "block-high-risk")

    decisions = [
        _evaluate_bucket(
            "dirty_worktree",
            target.get("unreviewed_unstaged_files", []),
            [p for p in target.get("unreviewed_unstaged_files", []) if _high_risk(p)],
            dirty_policy,
            "unstaged changes are outside the review target",
        ),
        _evaluate_bucket(
            "untracked",
            target.get("unreviewed_untracked_files", []),
            [p for p in target.get("unreviewed_untracked_files", []) if _high_risk(p)],
            untracked_policy,
            "untracked files are outside the review target",
        ),
        _evaluate_bucket(
            "partial_stage",
            target.get("unreviewed_partial_stage_files", []),
            target.get("high_risk_partial_stage_files", []),
            partial_policy,
            "files are partially staged",
        ),
    ]
    active = [decision for decision in decisions if decision["action"] != "pass"]
    block = [decision for decision in active if decision["action"] == "block"]
    action = "block" if block else "warn" if active else "pass"

    return {
        "action": action,
        "reason": _primary_reason(block or active),
        "policies": {
            "dirty_worktree_policy": dirty_policy,
            "untracked_policy": untracked_policy,
            "partial_stage_policy": partial_policy,
        },
        "warnings": [decision for decision in active if decision["action"] == "warn"],
        "blocks": block,
    }


def attach_target_decision(target: dict, decision: dict) -> dict:
    """Return target metadata with policy decision embedded."""
    target = dict(target or {})
    target["policy_action"] = decision.get("action", "pass")
    target["policy_reason"] = decision.get("reason", "")
    target["policies"] = dict(decision.get("policies") or {})
    return target


def format_target_block_reason(target: dict, decision: dict) -> str:
    """Format an agent-actionable target-integrity block reason."""
    lines = [
        "Cold Eyes blocked this change because the configured review target is incomplete.",
        "",
        f"Review target: {target.get('review_file_count', 0)} {target.get('scope', 'staged')} files",
        (
            "Not reviewed: "
            f"{len(target.get('unreviewed_unstaged_files', []))} unstaged, "
            f"{len(target.get('unreviewed_untracked_files', []))} untracked"
        ),
    ]

    partial = target.get("unreviewed_partial_stage_files", [])
    if partial:
        lines.extend(["", "Partially staged files:"])
        lines.extend(f"- {path}" for path in partial[:20])

    high_risk = target.get("high_risk_unreviewed_files", [])
    if high_risk:
        lines.extend(["", "High-risk files not reviewed:"])
        lines.extend(f"- {path}" for path in high_risk[:20])

    blocks = decision.get("blocks") or []
    if blocks:
        lines.extend(["", "Target policy:"])
        lines.extend(f"- {block['kind']}: {block['reason']}" for block in blocks)

    lines.extend([
        "",
        "Suggested action:",
        "- Stage the complete intended change, or",
        "- Ignore the file intentionally when it should not be reviewed, or",
        "- Switch scope when this turn should review a broader target.",
        "",
        "To override: python cli.py arm-override --reason '<reason>'",
    ])
    return "\n".join(lines)


def target_status_message(target: dict) -> str:
    """Return a short status message for human-readable status."""
    if not target:
        return "Review target is unknown."
    scope = target.get("scope", "staged")
    reviewed = target.get("review_file_count", 0)
    unstaged = len(target.get("unreviewed_unstaged_files", []))
    untracked = len(target.get("unreviewed_untracked_files", []))
    partial = len(target.get("unreviewed_partial_stage_files", []))
    parts = [f"Review target: {reviewed} {scope} files"]
    parts.append(f"Not reviewed: {unstaged} unstaged files, {untracked} untracked files")
    if partial:
        parts.append(f"Partial stage: {partial} files")
    return "\n".join(parts)


def _git_lines(*args: str) -> list[str]:
    return [line for line in git_cmd(*args).splitlines() if line]


def _filtered_paths(paths: list[str], ignore_file: str = "") -> list[str]:
    return sorted(dict.fromkeys(filter_file_list(paths, ignore_file)))


def _review_files_for_scope(
    scope: str,
    staged: list[str],
    unstaged: list[str],
    untracked: list[str],
) -> list[str]:
    if scope == "working":
        return sorted(set(staged) | set(unstaged) | set(untracked))
    if scope == "head":
        return sorted(set(staged) | set(unstaged))
    if scope == "staged":
        return staged
    return []


def _evaluate_bucket(
    kind: str,
    files: list[str],
    high_risk_files: list[str],
    policy: str,
    reason: str,
) -> dict:
    files = list(files or [])
    high_risk_files = list(high_risk_files or [])
    if not files or policy == "ignore":
        action = "pass"
    elif policy == "block":
        action = "block"
    elif policy == "block-high-risk":
        action = "block" if high_risk_files else "warn"
    else:
        action = "warn"

    return {
        "kind": kind,
        "action": action,
        "policy": policy,
        "reason": reason,
        "files": files,
        "file_count": len(files),
        "high_risk_files": high_risk_files,
        "high_risk_count": len(high_risk_files),
    }


def _primary_reason(decisions: list[dict]) -> str:
    if not decisions:
        return ""
    first = decisions[0]
    if first.get("kind") == "partial_stage":
        return "partial_stage"
    if first.get("kind") == "untracked":
        return "untracked_unreviewed"
    return "dirty_worktree_unreviewed"


def _target_integrity(
    *,
    review_files: list[str],
    unreviewed: list[str],
    partial_stage: list[str],
) -> str:
    if partial_stage:
        return "partial"
    if unreviewed:
        return "dirty"
    if not review_files:
        return "empty"
    return "clean"


def _high_risk(path: str) -> bool:
    return bool(RISK_PATTERN.search(path or ""))


def _dedupe(paths: list[str]) -> list[str]:
    return list(dict.fromkeys(path for path in paths if path))
