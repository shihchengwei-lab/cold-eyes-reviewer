"""One-time override token — arm, consume, expire."""

import hashlib
import json
import os
import uuid
from datetime import datetime, timezone, timedelta

TOKEN_DIR = os.path.expanduser("~/.claude/cold-review-overrides")


def _repo_hash(repo_root):
    """SHA-256 hex of normalized repo root path."""
    normalized = os.path.normcase(os.path.normpath(repo_root))
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()[:16]


def arm_override(repo_root, reason, ttl_minutes=10):
    """Create a one-time override token for the given repo.

    Returns dict with token metadata.
    """
    if ttl_minutes <= 0:
        raise ValueError(f"ttl_minutes must be positive, got {ttl_minutes}")
    os.makedirs(TOKEN_DIR, exist_ok=True)
    now = datetime.now(timezone.utc)
    token = {
        "repo_root": os.path.normpath(repo_root),
        "reason": reason or "",
        "created_at": now.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "expires_at": (now + timedelta(minutes=ttl_minutes)).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "nonce": uuid.uuid4().hex,
    }
    path = os.path.join(TOKEN_DIR, f"{_repo_hash(repo_root)}.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(token, f, ensure_ascii=False)
    return {"action": "arm-override", "token_path": path, **token}


def consume_override(repo_root):
    """Try to consume an override token for the given repo.

    Returns (True, reason) if a valid token was consumed.
    Returns (False, "") otherwise (missing, expired, wrong repo).
    """
    if not repo_root:
        return False, ""
    path = os.path.join(TOKEN_DIR, f"{_repo_hash(repo_root)}.json")
    if not os.path.isfile(path):
        return False, ""

    try:
        with open(path, "r", encoding="utf-8") as f:
            token = json.load(f)
    except (json.JSONDecodeError, OSError):
        _safe_remove(path)
        return False, ""

    # Validate repo_root match
    stored = os.path.normpath(token.get("repo_root", ""))
    expected = os.path.normpath(repo_root)
    if os.path.normcase(stored) != os.path.normcase(expected):
        return False, ""

    # Check expiry
    expires_str = token.get("expires_at", "")
    try:
        expires = datetime.fromisoformat(expires_str.replace("Z", "+00:00"))
        if datetime.now(timezone.utc) > expires:
            _safe_remove(path)
            return False, ""
    except (ValueError, TypeError):
        _safe_remove(path)
        return False, ""

    # Consume: delete first, then return
    reason = token.get("reason", "")
    _safe_remove(path)
    return True, reason


def _safe_remove(path):
    try:
        os.remove(path)
    except OSError:
        pass
