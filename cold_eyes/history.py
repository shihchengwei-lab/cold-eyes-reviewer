"""History logging, override aggregation, and statistics."""

import json
import os
import re
import tempfile
from datetime import datetime, timezone, timedelta

from cold_eyes import constants
from cold_eyes.constants import (
    STATE_OVERRIDDEN,
    STATE_BLOCKED,
    STATE_INFRA_FAILED,
    STATE_PASSED,
    STATE_REPORTED,
)


def log_to_history(cwd, mode, model, state, reason="", review=None,
                   file_count=0, line_count=0, truncated=False, token_count=0,
                   min_confidence="medium", scope="working", override_reason="",
                   failure_kind=None, stderr_excerpt="", review_depth=None,
                   coverage=None, cold_eyes_verdict=None, final_action=None,
                   authority=None, override_note="", duration_ms=None,
                   protection=None):
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
    if coverage is not None:
        entry["coverage"] = coverage
    if cold_eyes_verdict:
        entry["cold_eyes_verdict"] = cold_eyes_verdict
    if final_action:
        entry["final_action"] = final_action
    if authority:
        entry["authority"] = authority
    if override_note:
        entry["override_note"] = override_note
    if duration_ms is not None:
        entry["duration_ms"] = int(duration_ms)
    if protection is not None:
        entry["protection"] = protection

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
    gate_quality = _compute_gate_quality(entries)

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

    # Triage depth distribution
    depth_counts = {}
    for e in entries:
        d = e.get("review_depth", "unknown")
        depth_counts[d] = depth_counts.get(d, 0) + 1

    return {
        "action": "quality-report",
        "period": period,
        "total": total,
        "by_state": state_counts,
        "rates": rates,
        "gate_quality": gate_quality,
        "by_review_depth": depth_counts,
        "top_noisy_paths": noisy_paths[:10],
        "top_issue_categories": top_categories[:10],
    }


def _entry_final_action(entry):
    """Best-effort final action for old and new history entries."""
    final_action = entry.get("final_action")
    if final_action:
        return final_action
    state = entry.get("state")
    if state == STATE_OVERRIDDEN:
        return "override_pass"
    if state == STATE_BLOCKED:
        return "block"
    if state == STATE_REPORTED:
        return "report"
    if state == STATE_PASSED:
        return "pass"
    return ""


def _compute_gate_quality(entries):
    total = len(entries)
    final_actions = [_entry_final_action(e) for e in entries]
    pass_count = sum(1 for a in final_actions if a == "pass")
    block_count = sum(1 for a in final_actions if a == "block")
    override_count = sum(
        1 for e, a in zip(entries, final_actions)
        if a == "override_pass" or e.get("state") == STATE_OVERRIDDEN
    )
    false_positive_override_count = sum(
        1 for e, a in zip(entries, final_actions)
        if (a == "override_pass" or e.get("state") == STATE_OVERRIDDEN)
        and e.get("override_reason") == "false_positive"
    )
    accepted_risk_count = sum(
        1 for e, a in zip(entries, final_actions)
        if (a == "override_pass" or e.get("state") == STATE_OVERRIDDEN)
        and e.get("override_reason") == "acceptable_risk"
    )
    coverage_block_count = sum(1 for a in final_actions if a == "coverage_block")
    infra_failure_count = sum(
        1 for e in entries
        if e.get("state") == STATE_INFRA_FAILED
        or e.get("cold_eyes_verdict") == "infra_failed"
    )

    def rate(count):
        return round(count / total, 3) if total else 0.0

    return {
        "pass_count": pass_count,
        "block_count": block_count,
        "override_count": override_count,
        "override_rate": rate(override_count),
        "false_positive_override_count": false_positive_override_count,
        "accepted_risk_count": accepted_risk_count,
        "coverage_block_count": coverage_block_count,
        "coverage_block_rate": rate(coverage_block_count),
        "infra_failure_count": infra_failure_count,
        "infra_failure_rate": rate(infra_failure_count),
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

    if keep_entries is not None and keep_entries < 1:
        raise ValueError("--keep-entries must be >= 1")

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

    # Rewrite file atomically
    dir_name = os.path.dirname(path)
    if dir_name:
        os.makedirs(dir_name, exist_ok=True)
    fd, tmp_path = tempfile.mkstemp(dir=dir_name or ".", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            for e in kept:
                f.write(json.dumps(e, ensure_ascii=False) + "\n")
        os.replace(tmp_path, path)
    except BaseException:
        os.unlink(tmp_path)
        raise

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

    # Ensure archive directory exists (#72: always, not just when archive non-empty)
    dest_dir = os.path.dirname(dest)
    if dest_dir:  # #13: guard against bare filename where dirname is ""
        os.makedirs(dest_dir, exist_ok=True)

    # Atomic archive write: read existing, append new, write to temp, rename
    existing_archive = _read_history(dest)
    all_archive = existing_archive + archive
    fd_arc, tmp_arc = tempfile.mkstemp(dir=dest_dir or ".", suffix=".tmp")
    try:
        with os.fdopen(fd_arc, "w", encoding="utf-8") as f:
            for e in all_archive:
                f.write(json.dumps(e, ensure_ascii=False) + "\n")
        os.replace(tmp_arc, dest)
    except BaseException:
        os.unlink(tmp_arc)
        raise

    # Atomic main history rewrite
    path_dir = os.path.dirname(path)
    if path_dir:
        os.makedirs(path_dir, exist_ok=True)
    fd_main, tmp_main = tempfile.mkstemp(dir=path_dir or ".", suffix=".tmp")
    try:
        with os.fdopen(fd_main, "w", encoding="utf-8") as f:
            for e in keep:
                f.write(json.dumps(e, ensure_ascii=False) + "\n")
        os.replace(tmp_main, path)
    except BaseException:
        os.unlink(tmp_main)
        raise

    return {
        "action": "archive",
        "archived": len(archive),
        "kept": len(keep),
        "dest": dest,
    }
