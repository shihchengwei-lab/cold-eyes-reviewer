"""Smoke tests for cold-review.sh and profile sanity checks."""

import json
import os
import subprocess
import tempfile

SCRIPTS_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SHELL_SCRIPT = os.path.join(SCRIPTS_DIR, "cold-review.sh")
PROFILE_PATH = os.path.join(SCRIPTS_DIR, "cold-review-profile.json")


def run_shell(env_override=None, stdin_data="", cwd=None):
    """Run cold-review.sh with given environment and return result."""
    env = {**os.environ}
    env["PYTHONIOENCODING"] = "utf-8"
    if env_override:
        env.update(env_override)
    result = subprocess.run(
        ["bash", SHELL_SCRIPT],
        input=stdin_data,
        capture_output=True,
        text=True,
        env=env,
        cwd=cwd,
        timeout=30,
    )
    return result


class TestOffMode:
    def test_exits_zero(self):
        result = run_shell(env_override={"COLD_REVIEW_MODE": "off"})
        assert result.returncode == 0
        assert result.stdout == ""


class TestRecursionGuard:
    def test_exits_zero_when_active(self):
        result = run_shell(env_override={"COLD_REVIEW_ACTIVE": "1"})
        assert result.returncode == 0


class TestNoGitRepo:
    def test_skips_outside_git(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            result = run_shell(
                cwd=tmpdir,
                stdin_data='{"stop_hook_active": false}',
            )
            assert result.returncode == 0
            assert "not a git repo" in result.stderr


class TestProfileSanity:
    """Verify profile.json has no dead fields."""

    def test_no_dead_config_fields(self):
        with open(PROFILE_PATH, "r", encoding="utf-8") as f:
            profile = json.load(f)

        # These fields were identified as dead code and should be removed
        assert "personality" not in profile, "personality is dead code"
        stats = profile.get("stats", {})
        assert "SNARK" not in stats, "SNARK is dead code"
        assert "PATIENCE" not in stats, "PATIENCE is dead code"

    def test_required_fields_present(self):
        with open(PROFILE_PATH, "r", encoding="utf-8") as f:
            profile = json.load(f)

        assert "name" in profile
        assert "language" in profile
        stats = profile.get("stats", {})
        assert "RIGOR" in stats
        assert "PARANOIA" in stats
