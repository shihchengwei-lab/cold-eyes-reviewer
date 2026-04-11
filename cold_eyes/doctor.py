"""Environment health checks."""

import json
import os
import subprocess
import sys

from cold_eyes.constants import DEPLOY_FILES
from cold_eyes.git import git_cmd


def run_doctor(scripts_dir=None, settings_path=None, repo_root=None):
    """Check environment health. Return structured report dict."""
    if scripts_dir is None:
        scripts_dir = os.path.join(os.path.expanduser("~"), ".claude", "scripts")
    if settings_path is None:
        settings_path = os.path.join(os.path.expanduser("~"), ".claude", "settings.json")

    checks = []

    # 1. Python version
    ver = f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}"
    checks.append({"name": "python", "status": "ok", "detail": ver})

    # 2. Git
    git_ver = git_cmd("--version")
    if git_ver:
        checks.append({"name": "git", "status": "ok", "detail": git_ver})
    else:
        checks.append({"name": "git", "status": "fail", "detail": "not found"})

    # 3. Claude CLI
    try:
        r = subprocess.run(
            ["claude", "--version"], capture_output=True, text=True, timeout=10
        )
        if r.returncode == 0 and r.stdout.strip():
            checks.append({"name": "claude_cli", "status": "ok",
                           "detail": r.stdout.strip()})
        else:
            checks.append({"name": "claude_cli", "status": "fail",
                           "detail": f"exit {r.returncode}"})
    except FileNotFoundError:
        checks.append({"name": "claude_cli", "status": "fail",
                       "detail": "not found"})
    except Exception as e:
        checks.append({"name": "claude_cli", "status": "fail",
                       "detail": str(e)})

    # 4. Deploy files
    missing = [f for f in DEPLOY_FILES if not os.path.isfile(os.path.join(scripts_dir, f))]
    if not missing:
        checks.append({"name": "deploy_files", "status": "ok",
                       "detail": f"{len(DEPLOY_FILES)} files in {scripts_dir}"})
    else:
        checks.append({"name": "deploy_files", "status": "fail",
                       "detail": f"missing: {', '.join(missing)}"})

    # 5. settings.json Stop hook
    try:
        with open(settings_path, "r", encoding="utf-8") as f:
            settings = json.load(f)
        hooks = settings.get("hooks", {})
        stop_hooks = hooks.get("Stop", [])
        found = any(
            "cold-review.sh" in cmd
            for entry in stop_hooks
            for hook_list in ([entry] if isinstance(entry, str) else
                              entry.get("hooks", []) if isinstance(entry, dict) else [])
            for cmd in ([hook_list] if isinstance(hook_list, str) else
                        [hook_list.get("command", "")] if isinstance(hook_list, dict) else [])
        )
        if found:
            checks.append({"name": "settings_hook", "status": "ok",
                           "detail": "Stop hook configured"})
        else:
            checks.append({"name": "settings_hook", "status": "fail",
                           "detail": "cold-review.sh not found in hooks.Stop"})
    except FileNotFoundError:
        checks.append({"name": "settings_hook", "status": "fail",
                       "detail": f"{settings_path} not found"})
    except Exception as e:
        checks.append({"name": "settings_hook", "status": "fail",
                       "detail": str(e)})

    # 6. Git repo
    git_dir = git_cmd("rev-parse", "--git-dir")
    if git_dir:
        checks.append({"name": "git_repo", "status": "ok", "detail": "in git repo"})
    else:
        checks.append({"name": "git_repo", "status": "fail",
                       "detail": "not in a git repo"})

    # 7. .cold-review-ignore (info level)
    if repo_root is None:
        repo_root = git_cmd("rev-parse", "--show-toplevel")
    ignore_path = os.path.join(repo_root, ".cold-review-ignore") if repo_root else ""
    if ignore_path and os.path.isfile(ignore_path):
        checks.append({"name": "ignore_file", "status": "ok",
                       "detail": ".cold-review-ignore found"})
    else:
        checks.append({"name": "ignore_file", "status": "info",
                       "detail": ".cold-review-ignore not found (optional)"})

    all_ok = all(c["status"] != "fail" for c in checks)
    return {"action": "doctor", "checks": checks, "all_ok": all_ok}
