"""Fast review-envelope scan and cache decisions for the v2 gate."""

from __future__ import annotations

import fnmatch
import hashlib
import json
import os
import re
from pathlib import Path

from cold_eyes import __version__
from cold_eyes.constants import (
    GATE_BLOCKED_ISSUE,
    GATE_BLOCKED_UNREVIEWED_DELTA,
    GATE_PROTECTED,
    GATE_SCHEMA_VERSION,
    RISK_PATTERN,
)
from cold_eyes.git import GitCommandError, git_cmd, is_binary
from cold_eyes.triage import classify_file_role


SOURCE_EXTENSIONS = {
    ".py", ".ts", ".tsx", ".js", ".jsx", ".go", ".rs", ".java", ".kt",
    ".swift", ".c", ".cc", ".cpp", ".cxx", ".h", ".hpp", ".cs", ".rb",
    ".php",
}
CONFIG_EXTENSIONS = {
    ".yml", ".yaml", ".json", ".toml", ".ini", ".cfg", ".conf",
}
CONFIG_BASENAMES = {
    "dockerfile", "docker-compose.yml", "docker-compose.yaml",
    "requirements.txt", "pyproject.toml", "package.json",
    "package-lock.json", "pnpm-lock.yaml", "yarn.lock", "bun.lockb",
    ".cold-review-policy.yml", ".cold-review-ignore", "cold-review.sh",
}
INTERNAL_ARTIFACT_BASENAMES = {
    "history.jsonl",
    "cold-review-history.jsonl",
}
SAFE_BINARY_EXTENSIONS = {
    ".png", ".jpg", ".jpeg", ".gif", ".webp", ".ico", ".pdf", ".zip",
    ".gz", ".mp4", ".mov", ".woff", ".woff2", ".ttf", ".otf",
}
HIGH_RISK_PATH_RE = re.compile(
    r"(^|[/\\])(\.github[/\\]workflows|scripts|cold_eyes)([/\\]|$)|"
    r"(^|[/\\])cold-review(\.sh|-prompt.*\.txt)$|"
    r"(auth|permission|secret|credential|token|webhook|api|subprocess|shell|"
    r"delete|path|traversal|parser|policy|hook|review|gate)",
    re.IGNORECASE,
)
HIGH_RISK_DIFF_RE = re.compile(
    r"(subprocess|shell=True|rm\s+-rf|unlink|rmtree|requests\.|fetch\(|"
    r"api[_-]?key|secret|token|password|authorization|webhook)",
    re.IGNORECASE,
)


def build_review_envelope(
    *,
    repo_root: str,
    policy: dict | None = None,
    scope: str = "staged",
    shadow_scope: str = "working_delta",
    include_untracked: bool = True,
    ignore_file: str = "",
    model_profile: str = "deep",
    max_shadow_delta_files: int = 8,
    max_shadow_delta_bytes: int = 60000,
    tool_version: str = __version__,
) -> dict:
    """Build a deterministic envelope for the current effective changeset."""
    policy = policy or {}
    scope = (scope or "staged").lower()
    shadow_scope = (shadow_scope or "working_delta").lower()
    include_untracked = bool(include_untracked)
    max_shadow_delta_files = max(int(max_shadow_delta_files or 0), 0)
    max_shadow_delta_bytes = max(int(max_shadow_delta_bytes or 0), 0)

    staged = _custom_filter(_git_lines("diff", "--cached", "--name-only"), ignore_file)
    unstaged = _custom_filter(_git_lines("diff", "--name-only"), ignore_file)
    untracked = (
        _custom_filter(
            _git_lines("ls-files", "--others", "--exclude-standard", "--full-name"),
            ignore_file,
        )
        if include_untracked
        else []
    )

    all_changed = _dedupe(staged + unstaged + untracked)
    file_meta = {
        path: classify_envelope_file(path, repo_root=repo_root)
        for path in all_changed
    }
    diff_risk = _diff_high_risk_paths(staged, unstaged)
    for path in diff_risk:
        if path in file_meta:
            file_meta[path]["high_risk"] = True

    primary = _primary_files(scope, staged, unstaged, untracked)
    shadow_candidates = _shadow_candidates(
        scope=scope,
        shadow_scope=shadow_scope,
        primary=primary,
        staged=staged,
        unstaged=unstaged,
        untracked=untracked,
        file_meta=file_meta,
    )
    shadow = _select_shadow_delta(
        shadow_candidates,
        untracked=set(untracked),
        repo_root=repo_root,
        file_meta=file_meta,
        max_files=max_shadow_delta_files,
        max_bytes=max_shadow_delta_bytes,
    )

    review_files = _dedupe(primary + shadow["review_files"])
    unreviewed = shadow["unreviewed"]
    reviewable = [p for p in review_files if _requires_review(file_meta.get(p, {}))]
    safe_files = [
        p for p in all_changed
        if p not in reviewable and not _requires_review(file_meta.get(p, {}))
    ]
    high_risk_files = [
        p for p in all_changed if file_meta.get(p, {}).get("high_risk")
    ]
    high_risk_review_files = [
        p for p in review_files if file_meta.get(p, {}).get("high_risk")
    ]
    unreviewed_blocking = [
        item for item in unreviewed
        if item.get("high_risk") or item.get("role") in {"source", "config", "test", "migration"}
    ]

    policy_hash = _sha_json(_policy_projection(policy))
    ignore_hash = _file_hash(ignore_file)
    prompt_hash = _prompt_hash(repo_root)
    head_sha = _git_value("rev-parse", "HEAD")
    raw_parts = {
        "head_sha": head_sha,
        "cached_diff": _git_value("diff", "--cached"),
        "working_diff": _git_value("diff"),
        "untracked_hashes": _untracked_hashes(untracked, repo_root),
        "policy_hash": policy_hash,
        "ignore_hash": ignore_hash,
        "prompt_hash": prompt_hash,
        "model_profile": model_profile,
        "scope": scope,
        "shadow_scope": shadow_scope,
        "include_untracked": include_untracked,
        "tool_version": tool_version,
    }
    envelope_hash = "sha256:" + _sha_json(raw_parts)

    return {
        "schema_version": GATE_SCHEMA_VERSION,
        "tool_version": tool_version,
        "head_sha": head_sha,
        "policy_hash": "sha256:" + policy_hash,
        "ignore_hash": "sha256:" + ignore_hash,
        "prompt_hash": "sha256:" + prompt_hash,
        "model_profile": model_profile,
        "primary_scope": scope,
        "shadow_scope": shadow_scope,
        "changed_files": {
            "staged": staged,
            "unstaged": unstaged,
            "untracked": untracked,
            "ignored": [],
            "generated": [p for p, meta in file_meta.items() if meta.get("role") == "generated"],
            "binary": [p for p, meta in file_meta.items() if meta.get("role") == "binary"],
            "safe": safe_files,
        },
        "file_meta": file_meta,
        "review_target": {
            "files": review_files,
            "untracked_files": [p for p in review_files if p in set(untracked)],
            "delta_kind": "staged_plus_shadow_delta",
            "high_risk_files": high_risk_review_files,
            "source_config_files": reviewable,
        },
        "unreviewed": {
            "files": [item["path"] for item in unreviewed],
            "items": unreviewed,
            "high_risk_files": [
                item["path"] for item in unreviewed if item.get("high_risk")
            ],
            "reason": _primary_unreviewed_reason(unreviewed),
        },
        "high_risk_files": high_risk_files,
        "review_required": bool(reviewable),
        "blocking_unreviewed": unreviewed_blocking,
        "safe_only": bool(all_changed) and not reviewable and not unreviewed_blocking,
        "no_relevant_changes": not bool(all_changed),
        "envelope_hash": envelope_hash,
    }


def classify_envelope_file(path: str, *, repo_root: str = "") -> dict:
    """Classify a path for fast envelope decisions."""
    normalized = path.replace("\\", "/")
    base = os.path.basename(normalized)
    base_low = base.lower()
    suffix = Path(base_low).suffix
    role = classify_file_role(normalized)

    if _looks_binary_path(normalized) or _path_is_binary(path, repo_root):
        role = "binary"
    elif _is_config_path(normalized):
        role = "config"
    elif role == "test":
        role = "test"
    elif role == "migration":
        role = "migration"
    elif suffix in SOURCE_EXTENSIONS:
        role = "source"
    elif role not in {"docs", "generated", "config"}:
        role = "source"

    high_risk = bool(
        HIGH_RISK_PATH_RE.search(normalized)
        or RISK_PATTERN.search(normalized)
        or base_low in CONFIG_BASENAMES
    )
    return {
        "role": role,
        "high_risk": high_risk,
        "source_config": role in {"source", "config", "test", "migration"},
    }


def fast_path_decision(envelope: dict, cache: dict | None = None) -> dict:
    """Return the v2 fast-path decision before any model call."""
    cache = cache or {"hit": False}
    if envelope.get("no_relevant_changes"):
        return {"action": "pass", "gate_state": "skipped_no_change", "reason": "no relevant changes"}
    if envelope.get("blocking_unreviewed"):
        return {
            "action": "block",
            "gate_state": GATE_BLOCKED_UNREVIEWED_DELTA,
            "reason": "unreviewed_delta",
        }
    if envelope.get("safe_only"):
        return {"action": "pass", "gate_state": "skipped_safe", "reason": "safe-only changes"}
    if cache.get("hit") and cache.get("gate_state") == GATE_PROTECTED:
        return {"action": "pass", "gate_state": "protected_cached", "reason": "cache hit"}
    if cache.get("hit") and str(cache.get("gate_state", "")).startswith("blocked_"):
        return {
            "action": "block",
            "gate_state": cache.get("gate_state"),
            "reason": "cached block",
            "cached_entry": cache.get("entry"),
        }
    return {"action": "review", "gate_state": "review_needed", "reason": "review required"}


def find_matching_cache(envelope: dict, history_path: str) -> dict:
    """Find the newest trustworthy matching envelope in history."""
    if not history_path or not os.path.isfile(history_path):
        return {"hit": False, "reason": "history_missing"}
    target_hash = envelope.get("envelope_hash")
    target_policy = envelope.get("policy_hash")
    target_prompt = envelope.get("prompt_hash")
    with open(history_path, "r", encoding="utf-8") as f:
        lines = f.readlines()
    for line in reversed(lines):
        try:
            entry = json.loads(line)
        except json.JSONDecodeError:
            continue
        entry_env = entry.get("envelope")
        if not isinstance(entry_env, dict):
            continue
        if entry_env.get("envelope_hash") != target_hash:
            continue
        if entry_env.get("policy_hash") != target_policy:
            continue
        if entry_env.get("prompt_hash") != target_prompt:
            continue
        gate_state = entry.get("gate_state", "")
        if gate_state == GATE_PROTECTED and _entry_is_cacheable(entry):
            return {"hit": True, "gate_state": gate_state, "entry": entry}
        if str(gate_state).startswith("blocked_"):
            return {"hit": True, "gate_state": gate_state, "entry": entry}
        return {"hit": False, "reason": "matching_entry_not_cacheable", "entry": entry}
    return {"hit": False, "reason": "miss"}


def format_unreviewed_delta_reason(envelope: dict) -> str:
    """Format an agent-facing unreviewed delta block reason."""
    items = envelope.get("blocking_unreviewed") or envelope.get("unreviewed", {}).get("items") or []
    lines = [
        "Cold Eyes could not verify this turn.",
        "",
        f"Gate state: {GATE_BLOCKED_UNREVIEWED_DELTA}",
        "",
        "Reason:",
    ]
    if not items:
        lines.append("- Source/config changes were outside the review target.")
    for item in items[:20]:
        path = item.get("path", "")
        reason = item.get("reason", "unreviewed")
        role = item.get("role", "source")
        lines.append(f"- {path} ({role}, {reason}) was not reviewed.")
    lines.extend([
        "",
        "Required agent action:",
        "1. Do not summarize this task as completed.",
        "2. Inspect the listed files and keep the changes in the working tree.",
        "3. Stage the intended changes, ignore files intentionally, or reduce the delta.",
        "4. End the turn again so Cold Eyes can run a fresh review.",
    ])
    return "\n".join(lines)


def format_cached_block_reason(cache: dict, envelope: dict) -> str:
    """Return a short block reason for a repeated blocked envelope."""
    entry = cache.get("entry") or {}
    gate_state = cache.get("gate_state") or entry.get("gate_state") or GATE_BLOCKED_ISSUE
    files = envelope.get("review_target", {}).get("files") or []
    lines = [
        "Cold Eyes could not verify this turn.",
        "",
        f"Gate state: {gate_state}",
        "",
        "Reason:",
        "- This effective changeset already has a blocking Cold Eyes result.",
        "",
        "Required agent action:",
        "1. Do not summarize this task as completed.",
        "2. Fix or reduce the current diff.",
        "3. End the turn again so Cold Eyes can run a fresh review.",
    ]
    if files:
        lines.extend(["", "Files:"])
        lines.extend(f"- {path}" for path in files[:20])
    return "\n".join(lines)


def envelope_summary(envelope: dict | None) -> dict | None:
    """Compact history-safe envelope summary."""
    if not isinstance(envelope, dict):
        return None
    return {
        "schema_version": envelope.get("schema_version"),
        "tool_version": envelope.get("tool_version"),
        "head_sha": envelope.get("head_sha"),
        "policy_hash": envelope.get("policy_hash"),
        "ignore_hash": envelope.get("ignore_hash"),
        "prompt_hash": envelope.get("prompt_hash"),
        "primary_scope": envelope.get("primary_scope"),
        "shadow_scope": envelope.get("shadow_scope"),
        "changed_files": envelope.get("changed_files"),
        "review_target": envelope.get("review_target"),
        "unreviewed": envelope.get("unreviewed"),
        "review_required": bool(envelope.get("review_required")),
        "safe_only": bool(envelope.get("safe_only")),
        "envelope_hash": envelope.get("envelope_hash"),
    }


def _entry_is_cacheable(entry: dict) -> bool:
    if entry.get("state") == "overridden" or entry.get("final_action") == "override_pass":
        return False
    if entry.get("coverage_warning") or entry.get("target_warning") or entry.get("check_warning"):
        return False
    coverage = entry.get("coverage") or {}
    if coverage.get("action") in {"warn", "block"}:
        return False
    return entry.get("final_action") in {None, "", "pass"} or entry.get("gate_state") == GATE_PROTECTED


def _primary_files(scope: str, staged: list[str], unstaged: list[str], untracked: list[str]) -> list[str]:
    if scope == "working":
        return _dedupe(staged + unstaged + untracked)
    if scope == "head":
        return _dedupe(staged + unstaged)
    return list(staged)


def _shadow_candidates(
    *,
    scope: str,
    shadow_scope: str,
    primary: list[str],
    staged: list[str],
    unstaged: list[str],
    untracked: list[str],
    file_meta: dict,
) -> list[str]:
    if shadow_scope in {"off", "none"} or scope == "working":
        return []
    primary_set = set(primary)
    candidates = [p for p in _dedupe(unstaged + untracked) if p not in primary_set]
    return [p for p in candidates if _requires_review(file_meta.get(p, {}))]


def _select_shadow_delta(
    candidates: list[str],
    *,
    untracked: set[str],
    repo_root: str,
    file_meta: dict,
    max_files: int,
    max_bytes: int,
) -> dict:
    review_files = []
    unreviewed = []
    for path in candidates:
        meta = file_meta.get(path, {})
        if len(review_files) >= max_files:
            unreviewed.append(_unreviewed(path, meta, "budget"))
            continue
        if meta.get("role") == "binary":
            unreviewed.append(_unreviewed(path, meta, "binary"))
            continue
        byte_count = _delta_byte_count(path, untracked=untracked, repo_root=repo_root)
        if byte_count < 0:
            unreviewed.append(_unreviewed(path, meta, "unsupported"))
            continue
        if byte_count > max_bytes:
            unreviewed.append(_unreviewed(path, meta, "too_large"))
            continue
        review_files.append(path)
    return {"review_files": review_files, "unreviewed": unreviewed}


def _unreviewed(path: str, meta: dict, reason: str) -> dict:
    return {
        "path": path,
        "role": meta.get("role", "source"),
        "reason": reason,
        "high_risk": bool(meta.get("high_risk")),
    }


def _delta_byte_count(path: str, *, untracked: set[str], repo_root: str) -> int:
    if path in untracked:
        abs_path = os.path.join(repo_root, path) if repo_root else path
        try:
            return os.path.getsize(abs_path)
        except OSError:
            return -1
    try:
        return len(git_cmd("diff", "--", path).encode("utf-8"))
    except GitCommandError:
        return -1


def _requires_review(meta: dict) -> bool:
    return bool(
        meta.get("high_risk")
        or meta.get("role") in {"source", "config", "test", "migration"}
    )


def _is_config_path(path: str) -> bool:
    base = os.path.basename(path).lower()
    suffix = Path(base).suffix
    return (
        base in CONFIG_BASENAMES
        or suffix in CONFIG_EXTENSIONS
        or base.endswith(".env.example")
        or path.startswith(".github/workflows/")
        or path.startswith("scripts/")
    )


def _looks_binary_path(path: str) -> bool:
    suffix = Path(path.lower()).suffix
    return suffix in SAFE_BINARY_EXTENSIONS


def _path_is_binary(path: str, repo_root: str) -> bool:
    abs_path = os.path.join(repo_root, path) if repo_root else path
    return os.path.exists(abs_path) and is_binary(abs_path)


def _diff_high_risk_paths(staged: list[str], unstaged: list[str]) -> set[str]:
    paths = set()
    for path in _dedupe(staged + unstaged):
        try:
            diff = "\n".join([
                git_cmd("diff", "--cached", "--", path),
                git_cmd("diff", "--", path),
            ])
        except GitCommandError:
            continue
        if HIGH_RISK_DIFF_RE.search(diff):
            paths.add(path)
    return paths


def _untracked_hashes(untracked: list[str], repo_root: str) -> dict:
    result = {}
    for path in untracked:
        abs_path = os.path.join(repo_root, path) if repo_root else path
        try:
            with open(abs_path, "rb") as f:
                data = f.read()
        except OSError:
            result[path] = "unreadable"
            continue
        result[path] = "sha256:" + hashlib.sha256(data).hexdigest()
    return result


def _policy_projection(policy: dict) -> dict:
    return {str(k): policy[k] for k in sorted(policy)}


def _prompt_hash(repo_root: str) -> str:
    root = Path(repo_root or ".")
    paths = [
        root / "cold-review-prompt.txt",
        root / "cold-review-prompt-shallow.txt",
    ]
    h = hashlib.sha256()
    for path in paths:
        h.update(str(path.name).encode("utf-8"))
        h.update(_file_bytes(str(path)))
    return h.hexdigest()


def _file_hash(path: str) -> str:
    return hashlib.sha256(_file_bytes(path)).hexdigest()


def _file_bytes(path: str) -> bytes:
    if not path or not os.path.isfile(path):
        return b""
    try:
        with open(path, "rb") as f:
            return f.read()
    except OSError:
        return b""


def _custom_filter(paths: list[str], ignore_file: str = "") -> list[str]:
    patterns = _custom_ignore_patterns(ignore_file)
    result = []
    for path in paths:
        if not path:
            continue
        if os.path.basename(path) in INTERNAL_ARTIFACT_BASENAMES:
            continue
        if any(
            fnmatch.fnmatch(path, pattern)
            or fnmatch.fnmatch(os.path.basename(path), pattern)
            for pattern in patterns
        ):
            continue
        result.append(path)
    return _dedupe(result)


def _custom_ignore_patterns(ignore_file: str) -> list[str]:
    if not ignore_file or not os.path.isfile(ignore_file):
        return []
    patterns = []
    with open(ignore_file, "r", encoding="utf-8", errors="replace") as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#"):
                patterns.append(line)
    return patterns


def _primary_unreviewed_reason(items: list[dict]) -> str:
    if not items:
        return ""
    return str(items[0].get("reason") or "unreviewed")


def _git_lines(*args: str) -> list[str]:
    return [line for line in git_cmd(*args).splitlines() if line]


def _git_value(*args: str) -> str:
    try:
        return git_cmd(*args)
    except GitCommandError:
        return ""


def _sha_json(value: object) -> str:
    data = json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(data.encode("utf-8")).hexdigest()


def _dedupe(paths: list[str]) -> list[str]:
    return sorted(dict.fromkeys(path for path in paths if path))
