"""History logging, override aggregation, and statistics."""

import json
import os
import re
from datetime import datetime, timezone, timedelta

from cold_eyes import constants


def log_to_history(cwd, mode, model, state, reason="", review=None,
                   file_count=0, line_count=0, truncated=False, token_count=0,
                   min_confidence="medium", scope="working", override_reason=""):
    """Append structured entry to history JSONL file."""
    entry = {
        "version": 2,
        "timestamp": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "cwd": cwd,
        "mode": mode,
        "model": model,
        "state": state,
        "min_confidence": min_confidence,
        "scope": scope,
        "schema_version": review.get("schema_version", constants.SCHEMA_VERSION) if review else constants.SCHEMA_VERSION,
    }
    if override_reason:
        entry["override_reason"] = override_reason

    if review is not None:
        entry["diff_stats"] = {
            "files": file_count,
            "lines": line_count,
            "tokens": token_count,
            "truncated": truncated,
        }
        entry["review"] = review
    else:
        entry["reason"] = reason
        entry["review"] = None

    path = constants.HISTORY_FILE
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")


def aggregate_overrides(history_path=None, limit=50):
    """Summarise override patterns from history.

    Returns dict with total_overrides, reasons (grouped by count desc), recent.
    """
    path = history_path or constants.HISTORY_FILE
    overrides = []
    if os.path.isfile(path):
        with open(path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    entry = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if entry.get("state") == "overridden":
                    overrides.append(entry)

    counts = {}
    for entry in overrides:
        reason = entry.get("override_reason", "")
        counts[reason] = counts.get(reason, 0) + 1
    reasons = sorted(
        [{"reason": r, "count": c} for r, c in counts.items()],
        key=lambda x: x["count"], reverse=True,
    )
    recent = overrides[-limit:] if overrides else []
    return {
        "action": "aggregate-overrides",
        "total_overrides": len(overrides),
        "reasons": reasons,
        "recent": recent,
    }


def _parse_duration(s):
    """Parse a duration string like '7d', '24h', '2w' into a timedelta."""
    m = re.fullmatch(r"(\d+)([dhw])", s.strip().lower())
    if not m:
        return None
    n, unit = int(m.group(1)), m.group(2)
    if unit == "h":
        return timedelta(hours=n)
    if unit == "d":
        return timedelta(days=n)
    if unit == "w":
        return timedelta(weeks=n)
    return None


def _read_history(history_path=None):
    """Read and parse all history entries from JSONL file."""
    path = history_path or constants.HISTORY_FILE
    entries = []
    if not os.path.isfile(path):
        return entries
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                entries.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return entries


def compute_stats(history_path=None, last=None, by_reason=False, by_path=False):
    """Compute review statistics from history.

    Args:
        history_path: Path to history JSONL file.
        last: Duration filter string ('7d', '24h', '2w').
        by_reason: Include override reason breakdown.
        by_path: Include per-cwd breakdown.

    Returns dict with totals, state counts, and optional breakdowns.
    """
    entries = _read_history(history_path)

    # --- Time filter ---
    period = "all"
    if last:
        delta = _parse_duration(last)
        if delta:
            cutoff = datetime.now(timezone.utc) - delta
            filtered = []
            for e in entries:
                ts = e.get("timestamp", "")
                try:
                    t = datetime.fromisoformat(ts.replace("Z", "+00:00"))
                    if t >= cutoff:
                        filtered.append(e)
                except (ValueError, TypeError):
                    continue
            entries = filtered
            period = f"last {last}"

    # --- State counts ---
    state_counts = {}
    for e in entries:
        st = e.get("state", "unknown")
        state_counts[st] = state_counts.get(st, 0) + 1

    result = {
        "action": "stats",
        "period": period,
        "total": len(entries),
        "by_state": state_counts,
    }

    # --- Override reason breakdown ---
    if by_reason:
        reason_counts = {}
        for e in entries:
            if e.get("state") == "overridden":
                r = e.get("override_reason", "")
                reason_counts[r] = reason_counts.get(r, 0) + 1
        result["by_reason"] = sorted(
            [{"reason": r, "count": c} for r, c in reason_counts.items()],
            key=lambda x: x["count"], reverse=True,
        )

    # --- Per-path breakdown ---
    if by_path:
        path_data = {}
        for e in entries:
            p = e.get("cwd", "unknown")
            if p not in path_data:
                path_data[p] = {"total": 0, "blocked": 0, "overridden": 0}
            path_data[p]["total"] += 1
            st = e.get("state", "")
            if st == "blocked":
                path_data[p]["blocked"] += 1
            elif st == "overridden":
                path_data[p]["overridden"] += 1
        result["by_path"] = sorted(
            [{"path": p, **d} for p, d in path_data.items()],
            key=lambda x: x["blocked"], reverse=True,
        )

    return result
