"""Lightweight local check runner for the unified v1 pipeline."""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import time

from cold_eyes.constants import RISK_CATEGORIES
from cold_eyes.gates.result import normalize_result
from cold_eyes.triage import classify_file_role

DEFAULT_CHECK_MODE = "auto"
DEFAULT_TIMEOUT_SEC = 120

_OFF_VALUES = {"0", "false", "no", "off"}
_PY_DEPENDENCY_FILES = {
    "pyproject.toml",
    "setup.py",
    "setup.cfg",
    "requirements.txt",
    "requirements-dev.txt",
    "requirements_test.txt",
    "requirements-test.txt",
    "pipfile",
    "pipfile.lock",
    "poetry.lock",
}


def normalize_check_mode(value: str | None) -> str:
    """Return a supported local-check mode."""
    if value is None or value == "":
        return DEFAULT_CHECK_MODE
    value = str(value).strip().lower()
    if value in _OFF_VALUES:
        return "off"
    if value == "auto":
        return "auto"
    return DEFAULT_CHECK_MODE


def normalize_timeout(value, default: int = DEFAULT_TIMEOUT_SEC) -> int:
    """Return a bounded timeout in seconds."""
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return default
    if parsed <= 0:
        return default
    return min(parsed, 600)


def run_local_checks(
    changed_files: list[str],
    *,
    mode: str = DEFAULT_CHECK_MODE,
    timeout: int = DEFAULT_TIMEOUT_SEC,
    repo_root: str | None = None,
) -> dict:
    """Run selected local checks once and return a compact outcome summary."""
    mode = normalize_check_mode(mode)
    timeout = normalize_timeout(timeout)
    summary = {
        "mode": mode,
        "results": [],
        "hard_failed": False,
        "warnings": [],
    }
    if mode == "off":
        return summary

    repo_root = repo_root or os.getcwd()
    plan = select_checks(changed_files, repo_root=repo_root)
    if not plan:
        return summary

    for entry in plan:
        result = _run_check(entry, timeout=timeout, cwd=repo_root)
        summary["results"].append(result)
        summary["warnings"].extend(result.get("warnings", []))
        if (
            result.get("blocking") == "hard"
            and result.get("status") == "fail"
            and not result.get("infrastructure")
        ):
            summary["hard_failed"] = True

    return summary


def select_checks(changed_files: list[str], *, repo_root: str | None = None) -> list[dict]:
    """Select local checks from the current diff shape."""
    if not changed_files:
        return []

    repo_root = repo_root or os.getcwd()
    roles = {path: classify_file_role(path) for path in changed_files}
    py_files = [path for path in changed_files if path.lower().endswith(".py")]
    source_py = [path for path in py_files if roles.get(path) in {"source", "migration"}]
    test_py = [path for path in py_files if roles.get(path) in {"test", "test_support"}]
    high_risk = _has_high_risk_path(changed_files) or any(
        roles.get(path) == "migration" for path in changed_files
    )
    dependency_change = any(_is_dependency_file(path) for path in changed_files)

    selected: list[dict] = []
    if source_py or (high_risk and py_files):
        selected.extend([
            _entry("lint_checker", "soft", "python source changed"),
            _entry("type_checker", "soft", "python source changed"),
        ])

    if (test_py or (high_risk and source_py)) and _repo_has_pytest(repo_root, changed_files):
        selected.append(_entry("test_runner", "hard", "tests or high-risk python changed"))

    if dependency_change:
        selected.append(_entry("build_checker", "hard", "python dependency/build config changed"))

    return _dedupe(selected)


def format_block_reason(checks: dict) -> str:
    """Build a short block reason for hard local-check failures."""
    failed = _failed_results(checks, hard_only=True)
    if not failed:
        return "local check failed"
    parts = []
    for result in failed[:3]:
        name = result.get("check_id", "check")
        details = _finding_lines(result, limit=1)
        parts.append(f"{name}: {details[0]}" if details else name)
    return "Local check failed: " + "; ".join(parts)


def compact_history(checks: dict | None) -> dict | None:
    """Return a history-safe check summary."""
    if not checks:
        return None
    return {
        "mode": checks.get("mode", ""),
        "hard_failed": bool(checks.get("hard_failed")),
        "results": [
            {
                "check_id": result.get("check_id", ""),
                "status": result.get("status", ""),
                "blocking": result.get("blocking", ""),
                "duration_ms": result.get("duration_ms", 0),
                "finding_count": len(result.get("findings", [])),
                "infrastructure": bool(result.get("infrastructure")),
            }
            for result in checks.get("results", [])[:8]
        ],
        "warnings": list(checks.get("warnings", []))[:5],
    }


def repair_lines(checks: dict | None) -> list[str]:
    """Return agent-facing lines for failed local checks."""
    if not checks:
        return []
    failed = _failed_results(checks, hard_only=False)
    if not failed:
        return []

    lines = ["", "Local checks to fix:"]
    for result in failed[:5]:
        label = result.get("check_id", "check")
        blocking = result.get("blocking", "soft")
        lines.append(f"- [{blocking}] {label}: status={result.get('status', '')}")
        for detail in _finding_lines(result, limit=3):
            lines.append(f"  - {detail}")
    return lines


def _entry(check_id: str, blocking: str, reason: str) -> dict:
    return {"check_id": check_id, "blocking": blocking, "reason": reason}


def _dedupe(entries: list[dict]) -> list[dict]:
    seen: set[str] = set()
    result: list[dict] = []
    for entry in entries:
        check_id = entry["check_id"]
        if check_id in seen:
            continue
        seen.add(check_id)
        result.append(entry)
    return result


def _run_check(entry: dict, *, timeout: int, cwd: str) -> dict:
    check_id = entry["check_id"]
    blocking = entry.get("blocking", "soft")
    command = _command_for(check_id)
    base = {
        "check_id": check_id,
        "blocking": blocking,
        "reason": entry.get("reason", ""),
        "command": _display_command(command),
        "findings": [],
        "warnings": [],
        "raw_output": "",
        "duration_ms": 0,
    }

    if not _is_available(check_id, command):
        base.update({
            "status": "skip",
            "infrastructure": True,
            "warnings": [f"{check_id} skipped: tool not available"],
        })
        return base

    started = time.monotonic()
    try:
        proc = subprocess.run(
            command,
            cwd=cwd,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
        )
    except subprocess.TimeoutExpired:
        base.update({
            "status": "error",
            "infrastructure": True,
            "warnings": [f"{check_id} timed out after {timeout}s"],
            "raw_output": f"{check_id} timed out after {timeout}s",
            "duration_ms": int((time.monotonic() - started) * 1000),
        })
        return base
    except FileNotFoundError:
        base.update({
            "status": "skip",
            "infrastructure": True,
            "warnings": [f"{check_id} skipped: tool not found"],
            "duration_ms": int((time.monotonic() - started) * 1000),
        })
        return base

    raw = "\n".join(part for part in (proc.stdout, proc.stderr) if part)
    normalized = normalize_result(
        check_id,
        raw,
        proc.returncode,
        duration_ms=int((time.monotonic() - started) * 1000),
        blocking_mode=blocking,
    )
    return {
        **base,
        **normalized,
        "check_id": check_id,
        "blocking": blocking,
        "reason": entry.get("reason", ""),
        "command": _display_command(command),
        "infrastructure": False,
    }


def _command_for(check_id: str) -> list[str]:
    commands = {
        "test_runner": ["pytest", "--tb=short", "-q"],
        "lint_checker": ["ruff", "check", "."],
        "type_checker": ["mypy", "."],
        "build_checker": [sys.executable, "-m", "pip", "check", "--quiet"],
    }
    return commands.get(check_id, [check_id])


def _is_available(check_id: str, command: list[str]) -> bool:
    if check_id == "build_checker":
        return bool(sys.executable)
    return bool(command and shutil.which(command[0]))


def _display_command(command: list[str]) -> str:
    return " ".join(command)


def _has_high_risk_path(files: list[str]) -> bool:
    for path in files:
        normalized = path.replace("\\", "/")
        if any(pattern.search(normalized) for pattern in RISK_CATEGORIES.values()):
            return True
    return False


def _is_dependency_file(path: str) -> bool:
    name = path.replace("\\", "/").split("/")[-1].lower()
    if name in _PY_DEPENDENCY_FILES:
        return True
    return name.startswith("requirements") and name.endswith(".txt")


def _repo_has_pytest(repo_root: str, changed_files: list[str]) -> bool:
    if any(classify_file_role(path) in {"test", "test_support"} for path in changed_files):
        return True
    for config_name in ("pytest.ini", "tox.ini", "setup.cfg", "pyproject.toml"):
        path = os.path.join(repo_root, config_name)
        if not os.path.isfile(path):
            continue
        try:
            with open(path, "r", encoding="utf-8") as f:
                text = f.read(4000).lower()
        except (OSError, UnicodeDecodeError):
            continue
        if "pytest" in text or "[tool.pytest" in text:
            return True
    tests_dir = os.path.join(repo_root, "tests")
    return os.path.isdir(tests_dir)


def _failed_results(checks: dict, *, hard_only: bool) -> list[dict]:
    failed = []
    for result in checks.get("results", []):
        if result.get("status") != "fail":
            continue
        if result.get("infrastructure"):
            continue
        if hard_only and result.get("blocking") != "hard":
            continue
        failed.append(result)
    return failed


def _finding_lines(result: dict, *, limit: int) -> list[str]:
    lines = []
    for finding in result.get("findings", [])[:limit]:
        location = finding.get("location") or finding.get("file") or ""
        line = finding.get("line") or ""
        message = finding.get("message") or finding.get("type") or ""
        where = f"{location}:{line}".strip(":")
        lines.append(f"{where} {message}".strip())
    if not lines and result.get("raw_output"):
        lines.append(str(result["raw_output"]).strip().splitlines()[0][:240])
    return lines
