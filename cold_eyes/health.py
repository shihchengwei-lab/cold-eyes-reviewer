"""Agent-facing health notice and scheduler support."""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess

from cold_eyes.doctor import run_doctor
from cold_eyes.history import runtime_status


DEFAULT_TASK_NAME = "Cold Eyes Reviewer Health Notice"
DEFAULT_EVERY_DAYS = 7
DEFAULT_TIME = "09:00"
NOTICE_BASENAME = "cold-review-agent-notice"
RUNNER_BASENAME = "cold-review-health-notice.cmd"
LEVEL_OK = "ok"
LEVEL_ATTENTION = "attention"
LEVEL_GATE_UNRELIABLE = "gate_unreliable"
LEVEL_SCHEDULE_MISSING = "schedule_missing"
_GATE_UNRELIABLE_CHECKS = {
    "python",
    "git",
    "claude_cli",
    "deploy_files",
    "settings_hook",
    "shell_version",
}


def agent_notice(
    *,
    repo_root: str | None = None,
    notice_dir: str | None = None,
    write: bool = False,
    only_problem: bool = False,
) -> dict:
    """Build a low-detail notice intended for the main Agent."""
    repo_root = repo_root or os.getcwd()
    status = runtime_status(cwd=repo_root)
    doctor = run_doctor(repo_root=repo_root)
    failures = [
        {"name": check.get("name", ""), "detail": check.get("detail", "")}
        for check in doctor.get("checks", [])
        if check.get("status") == "fail"
    ]
    schedule_missing = _schedule_missing(doctor.get("checks", []))
    level = _notice_level(failures, schedule_missing, status)
    needs_attention = level != LEVEL_OK

    if needs_attention:
        message = _problem_message(level, failures, status)
    else:
        message = "Cold Eyes health check passed."

    result = {
        "action": "agent-notice",
        "ok": not needs_attention,
        "emitted": needs_attention or not only_problem,
        "level": level,
        "message": message,
        "repo_root": repo_root,
        "status_health": status.get("health"),
        "doctor_ok": bool(doctor.get("all_ok")),
        "failure_count": len(failures),
    }

    if write:
        paths = _notice_paths(notice_dir)
        if result["emitted"]:
            _write_notice(paths, result)
        else:
            _clear_notice(paths)
        result["notice_path"] = paths["text"]

    return result


def install_health_schedule(
    *,
    repo_root: str | None = None,
    scripts_dir: str | None = None,
    every_days: int = DEFAULT_EVERY_DAYS,
    time_of_day: str = DEFAULT_TIME,
    task_name: str = DEFAULT_TASK_NAME,
) -> dict:
    """Install or update a Windows scheduled task for health notices."""
    repo_root = repo_root or os.getcwd()
    scripts_dir = scripts_dir or os.path.join(os.path.expanduser("~"), ".claude", "scripts")
    every_days = _normalize_every_days(every_days)
    time_of_day = _normalize_time(time_of_day)
    scheduler = _scheduler_command()
    if not scheduler:
        return {
            "action": "install-health-schedule",
            "ok": False,
            "supported": False,
            "reason": "Windows Task Scheduler command not found",
        }

    scripts_dir_win = _to_windows_path(scripts_dir)
    repo_root_win = _to_windows_path(repo_root)
    runner_path = os.path.join(scripts_dir, RUNNER_BASENAME)
    runner_win = _to_windows_path(runner_path)
    cli_win = _win_join(scripts_dir_win, "cold_eyes", "cli.py")
    _write_runner(runner_path, repo_root_win, cli_win)

    proc = _run_scheduler([
        *scheduler,
        "/Create",
        "/F",
        "/SC",
        "DAILY",
        "/MO",
        str(every_days),
        "/ST",
        time_of_day,
        "/TN",
        task_name,
        "/TR",
        f'"{runner_win}"',
    ])
    return {
        "action": "install-health-schedule",
        "ok": proc.returncode == 0,
        "supported": True,
        "task_name": task_name,
        "every_days": every_days,
        "time": time_of_day,
        "runner": runner_win,
        "stdout": proc.stdout.strip(),
        "stderr": proc.stderr.strip(),
    }


def remove_health_schedule(
    *,
    scripts_dir: str | None = None,
    task_name: str = DEFAULT_TASK_NAME,
) -> dict:
    """Remove the scheduled health notice task and generated runner."""
    scripts_dir = scripts_dir or os.path.join(os.path.expanduser("~"), ".claude", "scripts")
    scheduler = _scheduler_command()
    if not scheduler:
        return {
            "action": "remove-health-schedule",
            "ok": False,
            "supported": False,
            "reason": "Windows Task Scheduler command not found",
        }
    proc = _run_scheduler([*scheduler, "/Delete", "/F", "/TN", task_name])
    runner_path = os.path.join(scripts_dir, RUNNER_BASENAME)
    try:
        os.remove(runner_path)
    except FileNotFoundError:
        pass
    return {
        "action": "remove-health-schedule",
        "ok": proc.returncode == 0,
        "supported": True,
        "task_name": task_name,
        "stdout": proc.stdout.strip(),
        "stderr": proc.stderr.strip(),
    }


def health_schedule_status(task_name: str = DEFAULT_TASK_NAME) -> dict:
    scheduler = _scheduler_command()
    if not scheduler:
        return {"status": "info", "detail": "Windows Task Scheduler command not found"}
    proc = _run_scheduler([*scheduler, "/Query", "/TN", task_name])
    if proc.returncode == 0:
        return {"status": "ok", "detail": f"scheduled task configured: {task_name}"}
    return {"status": "info", "detail": f"health notice schedule not found: {task_name}"}


def _notice_level(failures: list[dict], schedule_missing: bool, status: dict) -> str:
    names = {failure.get("name", "") for failure in failures}
    if names & _GATE_UNRELIABLE_CHECKS or status.get("health") == "problem":
        return LEVEL_GATE_UNRELIABLE
    if schedule_missing:
        return LEVEL_SCHEDULE_MISSING
    if failures:
        return LEVEL_ATTENTION
    return LEVEL_OK


def _schedule_missing(checks: list[dict]) -> bool:
    for check in checks:
        if check.get("name") != "health_schedule":
            continue
        return check.get("status") != "ok" and "schedule not found" in check.get("detail", "")
    return False


def _problem_message(level: str, failures: list[dict], status: dict) -> str:
    if level == LEVEL_GATE_UNRELIABLE:
        parts = ["Cold Eyes gate is not reliable yet."]
    elif level == LEVEL_SCHEDULE_MISSING:
        parts = ["Cold Eyes background health schedule is missing."]
    else:
        parts = ["Cold Eyes needs Agent attention."]

    if failures:
        names = ", ".join(failure["name"] for failure in failures if failure.get("name"))
        parts.append(f"Setup check needs attention: {names}.")
    elif status.get("health") == "problem":
        parts.append("The last health record shows the reviewer tool had an infrastructure problem.")
    if level == LEVEL_SCHEDULE_MISSING:
        parts.append("Run install-health-schedule or re-run install.sh to restore background checks.")
    else:
        parts.append("Run doctor --fix first, then doctor if attention remains.")
    return " ".join(parts)


def _notice_paths(notice_dir: str | None = None) -> dict:
    notice_dir = notice_dir or os.path.join(os.path.expanduser("~"), ".claude")
    return {
        "text": os.path.join(notice_dir, f"{NOTICE_BASENAME}.txt"),
        "json": os.path.join(notice_dir, f"{NOTICE_BASENAME}.json"),
    }


def _write_notice(paths: dict, result: dict) -> None:
    os.makedirs(os.path.dirname(paths["text"]), exist_ok=True)
    with open(paths["text"], "w", encoding="utf-8") as f:
        f.write(result["message"].strip() + "\n")
    with open(paths["json"], "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False)
        f.write("\n")


def _clear_notice(paths: dict) -> None:
    for path in paths.values():
        try:
            os.remove(path)
        except FileNotFoundError:
            pass


def _normalize_every_days(value) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return DEFAULT_EVERY_DAYS
    return min(max(parsed, 1), 365)


def _normalize_time(value) -> str:
    text = str(value or "").strip()
    if re.fullmatch(r"\d{1,2}:\d{2}", text):
        hour, minute = text.split(":", 1)
        hour_i = int(hour)
        minute_i = int(minute)
        if 0 <= hour_i <= 23 and 0 <= minute_i <= 59:
            return f"{hour_i:02d}:{minute_i:02d}"
    return DEFAULT_TIME


def _write_runner(path: str, repo_root_win: str, cli_win: str) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    content = (
        "@echo off\r\n"
        f'cd /d "{repo_root_win}"\r\n'
        f'python "{cli_win}" agent-notice --write --only-problem --repo-root "{repo_root_win}"\r\n'
    )
    with open(path, "w", encoding="utf-8", newline="") as f:
        f.write(content)


def _win_join(*parts: str) -> str:
    cleaned = [str(part).strip("\\/") for part in parts if str(part)]
    if not cleaned:
        return ""
    first, rest = cleaned[0], cleaned[1:]
    if re.fullmatch(r"[A-Za-z]:", first):
        first += "\\"
    return first + ("\\" + "\\".join(rest) if rest else "")


def _scheduler_command() -> list[str] | None:
    direct = shutil.which("schtasks") or shutil.which("schtasks.exe")
    if direct:
        return [direct]
    cmd = shutil.which("cmd.exe")
    if cmd:
        return [cmd, "/c", "schtasks"]
    return None


def _run_scheduler(args: list[str]) -> subprocess.CompletedProcess:
    return subprocess.run(
        args,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=30,
    )


def _to_windows_path(path: str) -> str:
    normalized = os.path.abspath(os.path.normpath(path))
    if os.name == "nt":
        return normalized

    match = re.match(r"^/mnt/([a-zA-Z])/(.*)$", normalized)
    if match:
        drive, rest = match.groups()
        return f"{drive.upper()}:\\" + rest.replace("/", "\\")

    match = re.match(r"^/([a-zA-Z])/(.*)$", normalized)
    if match:
        drive, rest = match.groups()
        return f"{drive.upper()}:\\" + rest.replace("/", "\\")

    wslpath = shutil.which("wslpath")
    if wslpath:
        try:
            proc = subprocess.run(
                [wslpath, "-w", normalized],
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=5,
            )
            if proc.returncode == 0 and proc.stdout.strip():
                return proc.stdout.strip()
        except Exception:
            pass
    return normalized
