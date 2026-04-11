"""Smoke tests for cold-review.sh and profile sanity checks."""

import json
import os
import subprocess
import tempfile

SCRIPTS_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SHELL_SCRIPT = os.path.join(SCRIPTS_DIR, "cold-review.sh")
PROMPT_TEMPLATE = os.path.join(SCRIPTS_DIR, "cold-review-prompt.txt")


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


class TestPromptTemplateSanity:
    """Verify prompt template has no dead fields."""

    def test_no_stats_placeholders(self):
        with open(PROMPT_TEMPLATE, "r", encoding="utf-8") as f:
            content = f.read()
        assert "{stats_rigor}" not in content, "stats_rigor placeholder is dead code"
        assert "{stats_paranoia}" not in content, "stats_paranoia placeholder is dead code"
        assert "{name}" not in content, "name placeholder is dead code — should be hardcoded"

    def test_has_language_placeholder(self):
        with open(PROMPT_TEMPLATE, "r", encoding="utf-8") as f:
            content = f.read()
        assert "{language}" in content

    def test_has_cold_eyes_hardcoded(self):
        with open(PROMPT_TEMPLATE, "r", encoding="utf-8") as f:
            content = f.read()
        assert "Cold Eyes" in content

    def test_has_schema_version(self):
        with open(PROMPT_TEMPLATE, "r", encoding="utf-8") as f:
            content = f.read()
        assert "schema_version" in content

    def test_has_line_hint(self):
        with open(PROMPT_TEMPLATE, "r", encoding="utf-8") as f:
            content = f.read()
        assert "line_hint" in content


class TestReadmeSanity:
    """Verify README contains key product sections."""

    def test_has_strategy_presets(self):
        readme = os.path.join(SCRIPTS_DIR, "README.md")
        with open(readme, "r", encoding="utf-8") as f:
            content = f.read()
        assert "Strategy presets" in content

    def test_has_override_reason(self):
        readme = os.path.join(SCRIPTS_DIR, "README.md")
        with open(readme, "r", encoding="utf-8") as f:
            content = f.read()
        assert "COLD_REVIEW_OVERRIDE_REASON" in content


# ===========================================================================
# PATCH 9 — Shell shim hardening checks
# ===========================================================================

class TestShellShimIntegrity:
    """Verify cold-review.sh has no legacy patterns."""

    def test_no_helper_references(self):
        with open(SHELL_SCRIPT, "r", encoding="utf-8") as f:
            content = f.read()
        assert "cold-review-helper" not in content
        assert "cold_eyes/helper.py" not in content.replace("cold_eyes/cli.py", "")

    def test_no_direct_claude_call(self):
        with open(SHELL_SCRIPT, "r", encoding="utf-8") as f:
            content = f.read()
        # Should not call claude directly (only via Python engine)
        assert '"claude"' not in content or "claude --version" in content
        assert "claude -p" not in content

    def test_no_max_lines(self):
        with open(SHELL_SCRIPT, "r", encoding="utf-8") as f:
            content = f.read()
        assert "COLD_REVIEW_MAX_LINES" not in content

    def test_uses_mkdir_lock(self):
        with open(SHELL_SCRIPT, "r", encoding="utf-8") as f:
            content = f.read()
        assert "mkdir" in content
        assert "lock.d" in content
