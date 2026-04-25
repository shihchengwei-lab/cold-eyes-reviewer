"""Environment health checks."""

import json
import os
import subprocess
import sys

from cold_eyes.constants import DEPLOY_FILES
from cold_eyes.git import git_cmd, GitCommandError
from cold_eyes.config import load_policy, POLICY_FILENAME


DEFAULT_POLICY_TEMPLATE = """# Cold Eyes Reviewer - per-repo configuration
# See README.md for all options.
mode: block
scope: working
model: sonnet
block_threshold: critical
confidence: medium
truncation_policy: warn
minimum_coverage_pct: 80
coverage_policy: warn
fail_on_unreviewed_high_risk: true
checks: auto
check_timeout_sec: 120
"""


GATE_POLICY_TEMPLATE = """# Cold Eyes Reviewer - Claude Code Stop-hook gate profile
# Gate mode is a diff-centered risk gate, not a full-context reviewer.
mode: block
scope: working
model: sonnet
block_threshold: critical
confidence: medium
truncation_policy: warn
minimum_coverage_pct: 80
coverage_policy: warn
fail_on_unreviewed_high_risk: true
checks: auto
check_timeout_sec: 120
"""


IGNORE_TEMPLATE = """# Cold Eyes Reviewer - additional files to skip
# One pattern per line (glob syntax).
# Built-in ignores (*.lock, dist/*, node_modules/*, etc.) are always active.
"""


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
    try:
        git_ver = git_cmd("--version")
        checks.append({"name": "git", "status": "ok", "detail": git_ver})
    except (GitCommandError, FileNotFoundError):
        checks.append({"name": "git", "status": "fail",
                       "detail": "git is not installed. Fix: install Git and ensure it is on PATH"})

    # 3. Claude CLI
    try:
        r = subprocess.run(
            ["claude", "--version"], capture_output=True, text=True, timeout=10,
            encoding="utf-8",
        )
        if r.returncode == 0 and r.stdout.strip():
            checks.append({"name": "claude_cli", "status": "ok",
                           "detail": r.stdout.strip()})
        else:
            checks.append({"name": "claude_cli", "status": "fail",
                           "detail": f"exit {r.returncode}. Fix: run 'claude --version' to diagnose"})
    except FileNotFoundError:
        checks.append({"name": "claude_cli", "status": "fail",
                       "detail": "not found. Fix: install Claude Code CLI (https://docs.anthropic.com/en/docs/claude-code)"})
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
                       "detail": f"missing: {', '.join(missing)}. Fix: re-run 'bash install.sh' from the repo root"})

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
                              entry.get("hooks", [entry]) if isinstance(entry, dict) else [])
            for cmd in ([hook_list] if isinstance(hook_list, str) else
                        [hook_list.get("command", "")] if isinstance(hook_list, dict) else [])
        )
        if found:
            checks.append({"name": "settings_hook", "status": "ok",
                           "detail": "Stop hook configured"})
        else:
            msg = f"cold-review.sh not found in hooks.Stop. Fix: add Stop hook to {settings_path}"
            checks.append({"name": "settings_hook", "status": "fail", "detail": msg})
    except FileNotFoundError:
        msg = f"{settings_path} not found. Fix: create settings.json with Stop hook config"
        checks.append({"name": "settings_hook", "status": "fail", "detail": msg})
    except Exception as e:
        checks.append({"name": "settings_hook", "status": "fail",
                       "detail": str(e)})

    # 6. Git repo
    try:
        git_cmd("rev-parse", "--git-dir")
        checks.append({"name": "git_repo", "status": "ok", "detail": "in git repo"})
    except GitCommandError:
        checks.append({"name": "git_repo", "status": "fail",
                       "detail": "not in a git repo. Fix: run 'git init' or cd to a git repository"})

    # 7. .cold-review-ignore (info level)
    if repo_root is None:
        try:
            repo_root = git_cmd("rev-parse", "--show-toplevel")
        except GitCommandError:
            repo_root = ""
    ignore_path = os.path.join(repo_root, ".cold-review-ignore") if repo_root else ""
    if ignore_path and os.path.isfile(ignore_path):
        checks.append({"name": "ignore_file", "status": "ok",
                       "detail": ".cold-review-ignore found"})
    else:
        checks.append({"name": "ignore_file", "status": "info",
                       "detail": ".cold-review-ignore not found (optional)"})

    # 8. .cold-review-policy.yml (info level)
    policy = load_policy(repo_root) if repo_root else {}
    policy_path = os.path.join(repo_root, POLICY_FILENAME) if repo_root else ""
    if policy:
        keys = ", ".join(sorted(policy.keys()))
        checks.append({"name": "policy_file", "status": "ok",
                       "detail": f"{POLICY_FILENAME} loaded ({keys})"})
    elif policy_path and os.path.isfile(policy_path):
        checks.append({"name": "policy_file", "status": "info",
                       "detail": f"{POLICY_FILENAME} found but empty or unreadable"})
    else:
        checks.append({"name": "policy_file", "status": "info",
                       "detail": f"{POLICY_FILENAME} not found (optional)"})

    # 9. Legacy helper detection (split-brain check)
    helper_path = os.path.join(scripts_dir, "cold-review-helper.py")
    if os.path.isfile(helper_path):
        msg = f"cold-review-helper.py found — split-brain risk. Fix: run 'doctor --fix' or delete {helper_path}"
        checks.append({"name": "legacy_helper", "status": "fail", "detail": msg})
    else:
        checks.append({"name": "legacy_helper", "status": "ok",
                       "detail": "no legacy helper"})

    # 10. Shell version check (no legacy patterns)
    shell_path = os.path.join(scripts_dir, "cold-review.sh")
    if os.path.isfile(shell_path):
        try:
            with open(shell_path, "r", encoding="utf-8") as f:
                shell_content = f.read()
            has_legacy = ("cold-review-helper" in shell_content
                          or "claude -p" in shell_content
                          or "COLD_REVIEW_MAX_LINES" in shell_content)
            if has_legacy:
                checks.append({"name": "shell_version", "status": "fail",
                               "detail": "cold-review.sh contains legacy patterns. Fix: re-run 'bash install.sh' to update"})
            else:
                checks.append({"name": "shell_version", "status": "ok",
                               "detail": "shell is current version"})
        except OSError:
            checks.append({"name": "shell_version", "status": "info",
                           "detail": "could not read cold-review.sh"})

    # 11. Legacy env var
    if os.environ.get("COLD_REVIEW_MAX_LINES"):
        checks.append({"name": "legacy_env", "status": "info",
                       "detail": "COLD_REVIEW_MAX_LINES is set — use COLD_REVIEW_MAX_TOKENS instead"})

    # 12. Agent health notice schedule (best-effort Windows integration)
    try:
        from cold_eyes.health import health_schedule_status
        schedule = health_schedule_status()
        checks.append({
            "name": "health_schedule",
            "status": schedule["status"],
            "detail": schedule["detail"],
        })
    except Exception as e:
        checks.append({"name": "health_schedule", "status": "info",
                       "detail": f"could not inspect health notice schedule: {e}"})

    all_ok = all(c["status"] != "fail" for c in checks)
    return {"action": "doctor", "checks": checks, "all_ok": all_ok}


def verify_install(scripts_dir=None, settings_path=None, repo_root=None):
    """Machine-readable install verification.

    Runs critical install checks (deploy_files, settings_hook) and reports
    git_repo status separately as an environment check.
    """
    report = run_doctor(scripts_dir, settings_path, repo_root)
    critical_checks = {"deploy_files", "settings_hook"}
    failures = [
        {"name": c["name"], "detail": c["detail"]}
        for c in report["checks"]
        if c["name"] in critical_checks and c["status"] == "fail"
    ]
    env_checks = {"git_repo"}
    env_warnings = [
        {"name": c["name"], "detail": c["detail"]}
        for c in report["checks"]
        if c["name"] in env_checks and c["status"] == "fail"
    ]
    return {
        "action": "verify-install",
        "ok": len(failures) == 0,
        "failures": failures,
        "env_warnings": env_warnings,
    }


def run_doctor_fix(scripts_dir=None, repo_root=None):
    """Auto-fix issues that can be safely repaired. Return report dict.

    Fixable:
      - legacy_helper: remove cold-review-helper.py from scripts_dir
      - health_schedule: create/update scheduled Agent health notice
      - stale Agent notice: clear it when health is now clean
    Not auto-fixed (manual decision required):
      - deploy_files: re-run install.sh
      - settings_hook: edit settings.json manually
      - shell_version: re-run install.sh
    """
    if scripts_dir is None:
        scripts_dir = os.path.join(os.path.expanduser("~"), ".claude", "scripts")
    if repo_root is None:
        try:
            repo_root = git_cmd("rev-parse", "--show-toplevel")
        except GitCommandError:
            repo_root = ""

    fixed = []
    skipped = []

    # Fix: remove legacy helper
    helper_path = os.path.join(scripts_dir, "cold-review-helper.py")
    if os.path.isfile(helper_path):
        os.remove(helper_path)
        fixed.append("legacy_helper: removed cold-review-helper.py")

    # Fix: ensure scheduled health notices are installed when supported.
    try:
        from cold_eyes.health import agent_notice, health_schedule_status, install_health_schedule
        schedule = health_schedule_status()
        if schedule.get("status") != "ok":
            scheduled = install_health_schedule(repo_root=repo_root or os.getcwd(), scripts_dir=scripts_dir)
            if scheduled.get("ok"):
                fixed.append("health_schedule: installed Agent health notice schedule")
            elif scheduled.get("supported") is False:
                skipped.append(f"health_schedule: {scheduled.get('reason', 'not supported')}")
            else:
                skipped.append(
                    "health_schedule: could not install schedule "
                    f"({scheduled.get('stderr') or scheduled.get('reason') or 'unknown error'})"
                )
        notice = agent_notice(repo_root=repo_root or os.getcwd(), write=True, only_problem=True)
        if not notice.get("emitted"):
            fixed.append("agent_notice: cleared stale notice")
    except Exception as e:
        skipped.append(f"health_schedule: could not repair ({e})")

    # Report: items that need manual action
    report = run_doctor(scripts_dir=scripts_dir, repo_root=repo_root)
    auto_fixable = {"legacy_helper", "health_schedule"}
    for check in report["checks"]:
        if check["status"] == "fail" and check["name"] not in auto_fixable:
            skipped.append(f"{check['name']}: {check['detail']} (manual fix required)")

    return {"action": "doctor-fix", "fixed": fixed, "skipped": skipped,
            "doctor": report}


def run_init(repo_root=None, profile="gate", force=False):
    """Initialize Cold Eyes Reviewer in a git repository.

    Creates policy and ignore files if they don't exist. Existing policy is
    preserved unless force=True.
    """
    if repo_root is None:
        try:
            repo_root = git_cmd("rev-parse", "--show-toplevel")
        except GitCommandError:
            return {"action": "init", "ok": False,
                    "error": "not in a git repository"}

    if profile not in ("default", "gate"):
        return {"action": "init", "ok": False,
                "error": f"unknown profile: {profile}"}

    created = []
    skipped = []

    # Create default policy file
    policy_path = os.path.join(repo_root, POLICY_FILENAME)
    policy_template = GATE_POLICY_TEMPLATE if profile == "gate" else DEFAULT_POLICY_TEMPLATE
    if force or not os.path.isfile(policy_path):
        with open(policy_path, "w", encoding="utf-8") as f:
            f.write(policy_template)
        created.append(POLICY_FILENAME)
    else:
        skipped.append(POLICY_FILENAME)
    # Create default ignore file
    ignore_path = os.path.join(repo_root, ".cold-review-ignore")
    if not os.path.isfile(ignore_path):
        with open(ignore_path, "w", encoding="utf-8") as f:
            f.write(IGNORE_TEMPLATE)
        created.append(".cold-review-ignore")
    else:
        skipped.append(".cold-review-ignore")
    next_steps = [
        "Run: python cold_eyes/cli.py doctor",
        "Use Claude Code Stop hook with cold-review.sh",
    ]
    if profile == "gate":
        next_steps.append("Use scope: staged manually if you want pre-commit-only review")

    return {"action": "init", "ok": True, "repo_root": repo_root,
            "profile": profile, "created": created, "skipped": skipped,
            "next_steps": next_steps}
