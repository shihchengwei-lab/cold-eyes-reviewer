"""History logging, override aggregation, and statistics."""

import json
import os
import re
from datetime import datetime, timezone, timedelta

from cold_eyes import constants
from cold_eyes.constants import STATE_OVERRIDDEN, STATE_BLOCKED, STATE_INFRA_FAILED


def log_to_history(cwd, mode, model, state, reason="", review=None,
                   file_count=0, line_count=0, truncated=False, token_count=0,
                   min_confidence="medium", scope="working", override_reason="",
                   failure_kind=None, stderr_excerpt="", review_depth=None):
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
    if failure_kind:
        entry["failure_kind"] = failure_kind
    if stderr_excerpt:
        entry["stderr_excerpt"] = stderr_excerpt[:500]
    if review_depth:
        entry["review_depth"] = review_depth

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
                if entry.get("state") == STATE_OVERRIDDEN:
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
            if e.get("state") == STATE_OVERRIDDEN:
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
            if st == STATE_BLOCKED:
                path_data[p]["blocked"] += 1
            elif st == STATE_OVERRIDDEN:
                path_data[p]["overridden"] += 1
        result["by_path"] = sorted(
            [{"path": p, **d} for p, d in path_data.items()],
            key=lambda x: x["blocked"], reverse=True,
        )

    return result


def quality_report(history_path=None, last=None):
    """Generate a quality report with rates and noise analysis.

    Returns dict with rates, top noisy paths, and top issue categories.
    """
    entries = _read_history(history_path)

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

    total = len(entries)
    if total == 0:
        return {"action": "quality-report", "period": period, "total": 0}

    # State counts
    state_counts = {}
    for e in entries:
        st = e.get("state", "unknown")
        state_counts[st] = state_counts.get(st, 0) + 1

    blocked = state_counts.get(STATE_BLOCKED, 0)
    overridden = state_counts.get(STATE_OVERRIDDEN, 0)
    infra = state_counts.get(STATE_INFRA_FAILED, 0)

    # Rates
    rates = {
        "block_rate": round(blocked / total, 3),
        "override_rate": round(overridden / total, 3),
        "infra_failure_rate": round(infra / total, 3),
    }

    # Top noisy paths (highest block+override rate)
    path_data = {}
    for e in entries:
        p = e.get("cwd", "unknown")
        if p not in path_data:
            path_data[p] = {"total": 0, "blocked": 0, "overridden": 0}
        path_data[p]["total"] += 1
        st = e.get("state", "")
        if st == STATE_BLOCKED:
            path_data[p]["blocked"] += 1
        elif st == STATE_OVERRIDDEN:
            path_data[p]["overridden"] += 1

    noisy_paths = []
    for p, d in path_data.items():
        noise = d["blocked"] + d["overridden"]
        if noise > 0:
            noisy_paths.append({
                "path": p,
                "noise_count": noise,
                "noise_rate": round(noise / d["total"], 3),
                **d,
            })
    noisy_paths.sort(key=lambda x: x["noise_count"], reverse=True)

    # Top issue categories
    category_counts = {}
    for e in entries:
        review = e.get("review")
        if not review or not isinstance(review, dict):
            continue
        for issue in review.get("issues", []):
            cat = issue.get("category", "unknown")
            category_counts[cat] = category_counts.get(cat, 0) + 1
    top_categories = sorted(
        [{"category": c, "count": n} for c, n in category_counts.items()],
        key=lambda x: x["count"], reverse=True,
    )

    return {
        "action": "quality-report",
        "period": period,
        "total": total,
        "by_state": state_counts,
        "rates": rates,
        "top_noisy_paths": noisy_paths[:10],
        "top_issue_categories": top_categories[:10],
    }


def prune_history(history_path=None, keep_days=None, keep_entries=None):
    """Remove old history entries. Returns report dict.

    Args:
        keep_days: Keep entries from the last N days.
        keep_entries: Keep the most recent N entries.
    At least one of keep_days or keep_entries must be specified.
    If both are given, entries matching either criterion are kept.
    """
    path = history_path or constants.HISTORY_FILE
    if keep_days is None and keep_entries is None:
        return {"action": "prune", "error": "specify --keep-days or --keep-entries"}

    entries = _read_history(path)
    original_count = len(entries)

    kept = []
    if keep_days is not None:
        cutoff = datetime.now(timezone.utc) - timedelta(days=keep_days)
        for e in entries:
            ts = e.get("timestamp", "")
            try:
                t = datetime.fromisoformat(ts.replace("Z", "+00:00"))
                if t >= cutoff:
                    kept.append(e)
            except (ValueError, TypeError):
                kept.append(e)  # keep unparseable entries
    if keep_entries is not None:
        tail = entries[-keep_entries:] if keep_entries > 0 else []
        if kept:
            kept_set = {
                json.dumps(e, sort_keys=True, ensure_ascii=False)
                for e in kept
            }
            for e in tail:
                key = json.dumps(e, sort_keys=True, ensure_ascii=False)
                if key not in kept_set:
                    kept.append(e)
                    kept_set.add(key)
            kept.sort(key=lambda e: e.get("timestamp", ""))
        else:
            kept = tail

    # Rewrite file
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        for e in kept:
            f.write(json.dumps(e, ensure_ascii=False) + "\n")

    return {
        "action": "prune",
        "original": original_count,
        "kept": len(kept),
        "removed": original_count - len(kept),
    }


def archive_history(history_path=None, before=None, dest=None):
    """Move entries older than a date to an archive file.

    Args:
        before: ISO date string (YYYY-MM-DD). Entries before this date are archived.
        dest: Destination archive file path. Defaults to history file + '.archive'.
    """
    path = history_path or constants.HISTORY_FILE
    if not before:
        return {"action": "archive", "error": "specify --before YYYY-MM-DD"}

    try:
        cutoff = datetime.fromisoformat(before).replace(tzinfo=timezone.utc)
    except ValueError:
        return {"action": "archive", "error": f"invalid date: {before}"}

    if dest is None:
        dest = path + ".archive"

    entries = _read_history(path)
    keep = []
    archive = []
    for e in entries:
        ts = e.get("timestamp", "")
        try:
            t = datetime.fromisoformat(ts.replace("Z", "+00:00"))
            if t < cutoff:
                archive.append(e)
            else:
                keep.append(e)
        except (ValueError, TypeError):
            keep.append(e)

    # Append to archive
    if archive:
        os.makedirs(os.path.dirname(dest), exist_ok=True)
        with open(dest, "a", encoding="utf-8") as f:
            for e in archive:
                f.write(json.dumps(e, ensure_ascii=False) + "\n")

    # Rewrite main history
    with open(path, "w", encoding="utf-8") as f:
        for e in keep:
            f.write(json.dumps(e, ensure_ascii=False) + "\n")

    return {
        "action": "archive",
        "archived": len(archive),
        "kept": len(keep),
        "dest": dest,
    }
