"""Smoke tests for cold-review.sh and profile sanity checks."""

import json
import os
import shutil
import subprocess
import sys
import tempfile

import pytest

_HAS_BASH = shutil.which("bash") is not None
skip_no_bash = pytest.mark.skipif(not _HAS_BASH, reason="bash not available")

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


@skip_no_bash
class TestOffMode:
    def test_exits_zero(self):
        result = run_shell(env_override={"COLD_REVIEW_MODE": "off"})
        assert result.returncode == 0
        assert result.stdout == ""


@skip_no_bash
class TestRecursionGuard:
    def test_exits_zero_when_active(self):
        result = run_shell(env_override={"COLD_REVIEW_ACTIVE": "1"})
        assert result.returncode == 0


@skip_no_bash
class TestNoGitRepo:
    def test_skips_outside_git(self):
        # Clear any stale lock from concurrent shell tests to avoid
        # "another review in progress" masking the expected message.
        lockdir = os.path.join(os.path.expanduser("~"), ".claude", ".cold-review-lock.d")
        if os.path.isdir(lockdir):
            shutil.rmtree(lockdir, ignore_errors=True)
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

# ===========================================================================
# Shell fail-closed verification (Patch 1 + 4)
# ===========================================================================

class TestShellFailClosedPatterns:
    """Static verification that shell script has no silent-pass patterns."""

    def test_no_silent_pass_on_empty_output(self):
        with open(SHELL_SCRIPT, "r", encoding="utf-8") as f:
            content = f.read()
        assert '[[ -z "$RESULT" ]] && exit 0' not in content

    def test_has_json_error_handling(self):
        with open(SHELL_SCRIPT, "r", encoding="utf-8") as f:
            content = f.read()
        assert "except" in content

    def test_no_default_pass_on_missing_action(self):
        with open(SHELL_SCRIPT, "r", encoding="utf-8") as f:
            content = f.read()
        assert "d.get('action', 'pass')" not in content

    def test_has_infra_failure_handler(self):
        with open(SHELL_SCRIPT, "r", encoding="utf-8") as f:
            content = f.read()
        assert "infra_fail" in content


class TestShellParserFailClosed:
    """Run the shell's inline Python parser with controlled inputs.

    Extracts the parser code from cold-review.sh, substitutes $MODE,
    and verifies fail-closed behaviour for each failure scenario.
    """

    @staticmethod
    def _extract_parser_code():
        with open(SHELL_SCRIPT, "r", encoding="utf-8") as f:
            lines = f.readlines()
        in_block = False
        in_python = False
        parser_lines = []
        for line in lines:
            if "Parse result and act" in line:
                in_block = True
                continue
            if in_block and 'python -c "' in line:
                in_python = True
                continue
            if in_python:
                if line.strip() == '"':
                    break
                parser_lines.append(line)
        assert parser_lines, "Failed to extract parser code from shell script"
        return "".join(parser_lines)

    def _run_parser(self, mode, stdin_data):
        code = self._extract_parser_code().replace("'$MODE'", f"'{mode}'")
        return subprocess.run(
            ["python", "-c", code],
            input=stdin_data, capture_output=True, text=True, timeout=10,
        )

    # --- Block mode: must block on failures ---

    def test_block_on_empty_output(self):
        r = self._run_parser("block", "")
        assert "infrastructure failure" in r.stderr
        out = json.loads(r.stdout)
        assert out["decision"] == "block"

    def test_block_on_invalid_json(self):
        r = self._run_parser("block", "not json at all")
        assert "infrastructure failure" in r.stderr
        out = json.loads(r.stdout)
        assert out["decision"] == "block"

    def test_block_on_missing_action(self):
        r = self._run_parser("block", json.dumps({"display": "x"}))
        assert "infrastructure failure" in r.stderr
        out = json.loads(r.stdout)
        assert out["decision"] == "block"

    def test_block_on_non_dict_json(self):
        r = self._run_parser("block", json.dumps([1, 2, 3]))
        assert "infrastructure failure" in r.stderr
        out = json.loads(r.stdout)
        assert out["decision"] == "block"

    # --- Report mode: warn but do not block ---

    def test_report_warns_on_empty_output(self):
        r = self._run_parser("report", "")
        assert "infrastructure failure" in r.stderr
        assert r.stdout.strip() == ""

    def test_report_warns_on_invalid_json(self):
        r = self._run_parser("report", "not json")
        assert "infrastructure failure" in r.stderr
        assert r.stdout.strip() == ""

    # --- Normal operation ---

    def test_pass_action_no_block_output(self):
        data = json.dumps({"action": "pass", "display": "cold-review: pass", "reason": ""})
        r = self._run_parser("block", data)
        assert "cold-review: pass" in r.stderr
        assert r.stdout.strip() == ""

    def test_block_action_emits_decision(self):
        data = json.dumps({"action": "block", "display": "blocking", "reason": "test reason"})
        r = self._run_parser("block", data)
        out = json.loads(r.stdout)
        assert out["decision"] == "block"
        assert out["reason"] == "test reason"


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
