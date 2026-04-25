"""Conservative auto-tuning from local review history.

The tuner is intentionally quality-first:
- it never raises the block threshold or confidence filter to reduce noise;
- it never disables high-risk coverage protection;
- it only reduces supporting context, not the primary diff budget.
"""

from __future__ import annotations

import json
import os
import tempfile
from datetime import datetime, timezone, timedelta

from cold_eyes.config import AUTO_POLICY_FILENAME, user_auto_policy_path
from cold_eyes.constants import (
    STATE_BLOCKED,
    STATE_INFRA_FAILED,
    STATE_OVERRIDDEN,
)
from cold_eyes.history import _parse_duration, _read_history


QUALITY_FLOOR = {
    "block_threshold": "critical",
    "confidence": "medium",
    "minimum_coverage_pct": 80,
    "coverage_policy": "warn",
    "fail_on_unreviewed_high_risk": True,
}

_WRITABLE_KEYS = set(QUALITY_FLOOR) | {"context_tokens"}
AUTOTUNE_STATE_FILE = os.path.join(
    os.path.expanduser("~"), ".claude", "cold-review-autotune-state.json"
)
DEFAULT_AUTO_INTERVAL_HOURS = 24


def auto_tune(
    history_path: str | None = None,
    last: str | None = None,
    min_samples: int = 5,
    repo_root: str | None = None,
    write: bool = False,
    output_path: str | None = None,
) -> dict:
    """Return conservative tuning recommendations from recent history."""
    entries = _filter_entries(_read_history(history_path), last)
    diagnostics = _diagnostics(entries)
    reasons: list[str] = []
    safeguards = [
        "block_threshold is never relaxed above critical",
        "confidence is never raised above medium by auto-tune",
        "fail_on_unreviewed_high_risk stays enabled",
        "speed tuning only reduces supporting context_tokens",
        "manual .cold-review-policy.yml overrides auto policy values",
    ]

    total = diagnostics["total"]
    changes: dict = {}
    recommended_profile = "observe"
    write_eligible = False

    if total < min_samples:
        reasons.append(
            f"only {total} sample(s); need at least {min_samples} before auto tuning"
        )
    else:
        write_eligible = True
        changes.update(QUALITY_FLOOR)
        quality_blocker = _quality_blocker(diagnostics)
        if quality_blocker:
            recommended_profile = "hold-quality"
            changes.update(_strictness_changes(diagnostics))
            reasons.extend(quality_blocker)
            reasons.append("quality signals present; keep full context and stronger coverage posture")
        else:
            speed_change = _speed_change(diagnostics)
            if speed_change:
                recommended_profile = "fast-safe"
                changes.update(speed_change)
                reasons.append(
                    "recent reviews look clean but expensive; reduce bounded context first"
                )
            else:
                recommended_profile = "balanced"
                reasons.append("recent history does not justify a speed reduction yet")

        if diagnostics["avg_files"] >= 8:
            reasons.append(
                "large working-tree reviews are common; consider staged scope manually"
            )
        if diagnostics["duration_samples"] == 0:
            reasons.append(
                "duration_ms is missing in older history; future runs will record it"
            )

    result = {
        "action": "auto-tune",
        "period": f"last {last}" if last else "all",
        "total": total,
        "min_samples": min_samples,
        "recommended_profile": recommended_profile,
        "changes": _safe_changes(changes),
        "safety_floor": dict(QUALITY_FLOOR),
        "diagnostics": diagnostics,
        "reasons": reasons,
        "safeguards": safeguards,
        "write_eligible": write_eligible,
        "written": False,
    }

    if write:
        if not write_eligible:
            result["write_error"] = "not enough samples"
        else:
            path = write_auto_policy(
                repo_root=repo_root or os.getcwd(),
                changes=result["changes"],
                output_path=output_path,
            )
            result["written"] = True
            result["path"] = path

    return result


def maybe_auto_tune(
    repo_root: str,
    history_path: str | None = None,
    last: str = "7d",
    min_samples: int = 5,
    interval_hours: int = DEFAULT_AUTO_INTERVAL_HOURS,
    state_path: str | None = None,
    output_path: str | None = None,
    now: datetime | None = None,
) -> dict:
    """Low-frequency automatic tuning for hook-driven runs.

    This writes a home-scoped auto policy, so normal hook usage does not dirty
    the repository working tree.
    """
    if not repo_root:
        return {"action": "auto-tune-skip", "reason": "no repo root"}
    now = now or datetime.now(timezone.utc)
    state_path = state_path or AUTOTUNE_STATE_FILE
    repo_key = _repo_state_key(repo_root)
    state = _read_state(state_path)
    repo_state = state.get("repos", {}).get(repo_key, {})
    last_checked = _parse_iso(repo_state.get("last_checked", ""))
    if last_checked and interval_hours > 0:
        elapsed = now - last_checked
        if elapsed < timedelta(hours=interval_hours):
            return {
                "action": "auto-tune-skip",
                "reason": "interval",
                "last_checked": repo_state.get("last_checked", ""),
                "interval_hours": interval_hours,
            }

    result = auto_tune(
        history_path=history_path,
        last=last,
        min_samples=min_samples,
        repo_root=repo_root,
        write=False,
    )
    written = False
    path = ""
    if result.get("write_eligible") and result.get("changes"):
        path = write_auto_policy(
            repo_root=repo_root,
            changes=result["changes"],
            output_path=output_path or user_auto_policy_path(repo_root),
        )
        written = True

    _write_state(
        state_path,
        state,
        repo_key,
        {
            "repo_root": os.path.abspath(repo_root),
            "last_checked": _format_iso(now),
            "last_recommended_profile": result.get("recommended_profile", ""),
            "last_written": written,
            "policy_path": path,
        },
    )
    return {
        "action": "auto-tune-auto",
        "recommended_profile": result.get("recommended_profile", ""),
        "written": written,
        "path": path,
        "reasons": result.get("reasons", []),
    }


def write_auto_policy(
    repo_root: str,
    changes: dict,
    output_path: str | None = None,
) -> str:
    """Write a low-priority auto policy file and return its path."""
    if not repo_root and not output_path:
        raise ValueError("repo_root or output_path is required")
    safe = _safe_changes(changes)
    path = output_path or os.path.join(repo_root, AUTO_POLICY_FILENAME)
    directory = os.path.dirname(path) or "."
    os.makedirs(directory, exist_ok=True)

    lines = [
        "# Cold Eyes auto tuning",
        "# Generated from local history. Manual .cold-review-policy.yml overrides this file.",
        "# Safe to delete; it will be recreated by auto-tune --write-auto-policy.",
    ]
    for key in sorted(safe):
        lines.append(f"{key}: {_format_policy_value(safe[key])}")
    text = "\n".join(lines) + "\n"

    fd, tmp_path = tempfile.mkstemp(dir=directory, suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(text)
        os.replace(tmp_path, path)
    except BaseException:
        os.unlink(tmp_path)
        raise
    return path


def _repo_state_key(repo_root: str) -> str:
    return os.path.abspath(repo_root).lower()


def _read_state(path: str) -> dict:
    if not os.path.isfile(path):
        return {"repos": {}}
    try:
        with open(path, "r", encoding="utf-8") as f:
            state = json.load(f)
    except (OSError, json.JSONDecodeError):
        return {"repos": {}}
    if not isinstance(state, dict):
        return {"repos": {}}
    repos = state.get("repos")
    if not isinstance(repos, dict):
        state["repos"] = {}
    return state


def _write_state(path: str, state: dict, repo_key: str, repo_state: dict) -> None:
    state = dict(state)
    repos = dict(state.get("repos", {}))
    repos[repo_key] = repo_state
    state["repos"] = repos
    directory = os.path.dirname(path) or "."
    os.makedirs(directory, exist_ok=True)
    fd, tmp_path = tempfile.mkstemp(dir=directory, suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(state, f, ensure_ascii=False, indent=2)
            f.write("\n")
        os.replace(tmp_path, path)
    except BaseException:
        os.unlink(tmp_path)
        raise


def _parse_iso(value: str) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def _format_iso(value: datetime) -> str:
    return value.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _filter_entries(entries: list[dict], last: str | None) -> list[dict]:
    if not last:
        return entries
    delta = _parse_duration(last)
    if not delta:
        return entries
    cutoff = datetime.now(timezone.utc) - delta
    filtered = []
    for entry in entries:
        ts = entry.get("timestamp", "")
        try:
            when = datetime.fromisoformat(ts.replace("Z", "+00:00"))
        except (ValueError, TypeError):
            continue
        if when >= cutoff:
            filtered.append(entry)
    return filtered


def _diagnostics(entries: list[dict]) -> dict:
    total = len(entries)
    durations = [
        int(e["duration_ms"]) for e in entries
        if isinstance(e.get("duration_ms"), int) and e.get("duration_ms", 0) >= 0
    ]
    tokens = []
    files = []
    depth_counts: dict[str, int] = {}
    issue_count = 0
    blocked = 0
    overridden = 0
    infra = 0
    coverage_blocks = 0
    high_risk_unreviewed = 0

    for entry in entries:
        depth = entry.get("review_depth", "unknown")
        depth_counts[depth] = depth_counts.get(depth, 0) + 1

        state = entry.get("state")
        if state == STATE_BLOCKED:
            blocked += 1
        elif state == STATE_OVERRIDDEN:
            overridden += 1
        elif state == STATE_INFRA_FAILED:
            infra += 1

        if entry.get("final_action") == "coverage_block":
            coverage_blocks += 1

        coverage = entry.get("coverage")
        if isinstance(coverage, dict):
            high_risk_unreviewed += len(coverage.get("unreviewed_high_risk_files", []))

        stats = entry.get("diff_stats")
        if isinstance(stats, dict):
            if isinstance(stats.get("tokens"), int):
                tokens.append(stats["tokens"])
            if isinstance(stats.get("files"), int):
                files.append(stats["files"])

        review = entry.get("review")
        if isinstance(review, dict):
            issue_count += len(review.get("issues", []))

    return {
        "total": total,
        "duration_samples": len(durations),
        "avg_duration_ms": _avg(durations),
        "p95_duration_ms": _percentile(durations, 95),
        "avg_tokens": _avg(tokens),
        "avg_files": _avg(files),
        "issue_count": issue_count,
        "by_review_depth": depth_counts,
        "deep_rate": _rate(depth_counts.get("deep", 0), total),
        "skip_rate": _rate(depth_counts.get("skip", 0), total),
        "shallow_rate": _rate(depth_counts.get("shallow", 0), total),
        "block_rate": _rate(blocked, total),
        "override_rate": _rate(overridden, total),
        "infra_failure_rate": _rate(infra, total),
        "coverage_block_rate": _rate(coverage_blocks, total),
        "high_risk_unreviewed_count": high_risk_unreviewed,
    }


def _quality_blocker(diagnostics: dict) -> list[str]:
    reasons = []
    if diagnostics["infra_failure_rate"] > 0.05:
        reasons.append("infra failures are above 5%; fix reliability before reducing time")
    if diagnostics["coverage_block_rate"] > 0:
        reasons.append("coverage blocks occurred; do not reduce review input yet")
    if diagnostics["high_risk_unreviewed_count"] > 0:
        reasons.append("high-risk files were unreviewed; keep coverage protection strict")
    if diagnostics["override_rate"] > 0.10:
        reasons.append("override rate is above 10%; tune noise before reducing context")
    if diagnostics["block_rate"] > 0:
        reasons.append("recent blocks exist; keep context until the pattern is understood")
    return reasons


def _strictness_changes(diagnostics: dict) -> dict:
    changes = {"context_tokens": 2000}
    if (
        diagnostics["coverage_block_rate"] > 0
        or diagnostics["high_risk_unreviewed_count"] > 0
    ):
        changes["coverage_policy"] = "block"
    return changes


def _speed_change(diagnostics: dict) -> dict:
    slow_by_time = (
        diagnostics["duration_samples"] > 0
        and (
            diagnostics["avg_duration_ms"] >= 20_000
            or diagnostics["p95_duration_ms"] >= 45_000
        )
    )
    slow_by_tokens = diagnostics["avg_tokens"] >= 10_000
    deep_heavy = diagnostics["deep_rate"] >= 0.5
    if not deep_heavy or not (slow_by_time or slow_by_tokens):
        return {}
    if diagnostics["avg_tokens"] >= 16_000 or diagnostics["p95_duration_ms"] >= 60_000:
        return {"context_tokens": 800}
    return {"context_tokens": 1200}


def _safe_changes(changes: dict) -> dict:
    return {k: v for k, v in changes.items() if k in _WRITABLE_KEYS}


def _avg(values: list[int]) -> float:
    return round(sum(values) / len(values), 1) if values else 0.0


def _percentile(values: list[int], pct: int) -> int:
    if not values:
        return 0
    ordered = sorted(values)
    idx = round((len(ordered) - 1) * pct / 100)
    return ordered[idx]


def _rate(count: int, total: int) -> float:
    return round(count / total, 3) if total else 0.0


def _format_policy_value(value) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)):
        return str(value)
    return json.dumps(str(value), ensure_ascii=False)
