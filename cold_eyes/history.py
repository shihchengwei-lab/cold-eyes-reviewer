"""History logging and override aggregation."""

import json
import os
from datetime import datetime, timezone

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
