"""Smoke tests for cold-review.sh and profile sanity checks."""

import json
import os
import shutil
import subprocess
import sys
import tempfile

import pytest

def _check_bash():
    """Return True only if bash can actually execute scripts.

    shutil.which("bash") may find WSL bash on Windows CI, which fails
    with 'no installed distributions' when there's no Linux distro.
    """
    bash_path = shutil.which("bash")
    if not bash_path:
        return False
    if os.name == "nt" and "\\WindowsApps\\" in bash_path:
        # WindowsApps bash is the WSL launcher.  The shell smoke tests exercise
        # the documented Git Bash path and pass Windows script paths directly.
        return False
    try:
        r = subprocess.run(
            ["bash", "--version"], capture_output=True, timeout=5,
        )
        return r.returncode == 0
    except (OSError, subprocess.TimeoutExpired):
        return False

_HAS_BASH = _check_bash()
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
        encoding="utf-8",
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

    def test_exits_zero_when_stop_hook_already_active(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            os.makedirs(os.path.join(tmpdir, ".claude"), exist_ok=True)
            result = run_shell(
                stdin_data='{"stop_hook_active": true}',
                env_override={"HOME": tmpdir},
            )
            assert result.returncode == 0
            assert result.stdout == ""


@skip_no_bash
class TestNoGitRepo:
    def test_skips_outside_git(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            # Use isolated HOME so this test gets its own lock directory,
            # avoiding conflicts with concurrent CI workflows.
            os.makedirs(os.path.join(tmpdir, ".claude"), exist_ok=True)
            result = run_shell(
                cwd=tmpdir,
                stdin_data='{"stop_hook_active": false}',
                env_override={"HOME": tmpdir},
            )
            assert result.returncode == 0
            assert "not a git repo" in result.stderr


def _make_bash_only_bin(tmpdir):
    """Create a temp bin dir containing only a bash symlink/copy.

    On Linux, bash and python3 share /usr/bin/ so restricting PATH to
    bash's parent dir still exposes python.  This helper isolates bash
    into its own directory.
    """
    bin_dir = os.path.join(tmpdir, "bin")
    os.makedirs(bin_dir, exist_ok=True)
    bash_path = shutil.which("bash")
    dest = os.path.join(bin_dir, "bash")
    try:
        os.symlink(bash_path, dest)
    except OSError:
        # Windows or no symlink permission — copy instead
        shutil.copy2(bash_path, dest)
    return bin_dir


@skip_no_bash
class TestNoPythonInterpreter:
    """Verify fail-closed when python interpreter is missing."""

    def test_block_mode_emits_block_on_missing_python(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            os.makedirs(os.path.join(tmpdir, ".claude"), exist_ok=True)
            bin_dir = _make_bash_only_bin(tmpdir)
            result = run_shell(
                cwd=tmpdir,
                env_override={
                    "COLD_REVIEW_MODE": "block",
                    "HOME": tmpdir,
                    "PATH": bin_dir,
                },
            )
            assert result.returncode == 0
            assert "python interpreter not found" in result.stderr
            out = json.loads(result.stdout)
            assert out["decision"] == "block"
            notice = os.path.join(tmpdir, ".claude", "cold-review-agent-notice.txt")
            assert os.path.isfile(notice)
            with open(notice, "r", encoding="utf-8") as f:
                assert "gate is not reliable" in f.read()

    def test_report_mode_warns_on_missing_python(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            os.makedirs(os.path.join(tmpdir, ".claude"), exist_ok=True)
            bin_dir = _make_bash_only_bin(tmpdir)
            result = run_shell(
                cwd=tmpdir,
                env_override={
                    "COLD_REVIEW_MODE": "report",
                    "HOME": tmpdir,
                    "PATH": bin_dir,
                },
            )
            assert result.returncode == 0
            assert "python interpreter not found" in result.stderr
            assert result.stdout.strip() == ""


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
            if in_block and '-c "' in line and ('python' in line or 'PYTHON_CMD' in line):
                in_python = True
                continue
            if in_python:
                if line.strip() == '"':
                    break
                parser_lines.append(line)
        assert parser_lines, "Failed to extract parser code from shell script"
        return "".join(parser_lines)

    def _run_parser(self, mode, stdin_data):
        code = self._extract_parser_code()
        with tempfile.TemporaryDirectory() as tmpdir:
            notice = os.path.join(tmpdir, "notice.txt")
            env = {
                **os.environ,
                "COLD_REVIEW_PARSE_MODE": mode,
                "COLD_REVIEW_NOTICE_FILE": notice,
            }
            result = subprocess.run(
                ["python", "-c", code],
                input=stdin_data, capture_output=True, text=True, timeout=10,
                env=env,
            )
            result.notice_path = notice
            result.notice_text = ""
            if os.path.isfile(notice):
                with open(notice, "r", encoding="utf-8") as f:
                    result.notice_text = f.read()
            return result

    # --- Block mode: must block on failures ---

    def test_block_on_empty_output(self):
        r = self._run_parser("block", "")
        assert "infrastructure failure" in r.stderr
        assert "gate is not reliable" in r.notice_text
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
        assert "gate is not reliable" in r.notice_text
        out = json.loads(r.stdout)
        assert out["decision"] == "block"

    def test_infra_failed_result_writes_notice(self):
        data = json.dumps({
            "action": "block",
            "state": "infra_failed",
            "display": "infra",
            "reason": "infra failed",
        })
        r = self._run_parser("block", data)
        assert "reviewer infrastructure problem" in r.notice_text

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

    def test_block_action_preserves_agent_brief_reason(self):
        reason = (
            "Agent repair task:\nfix it\n\n"
            "Fresh-review rerun protocol:\n- end the turn so Cold Eyes runs again\n\n"
            "User-facing talking points (only if a user update is necessary; summarize in your own words; do not quote verbatim):\nplain text\n\n"
            "Local checks to fix:\n- [hard] test_runner: status=fail"
        )
        data = json.dumps({"action": "block", "display": "blocking", "reason": reason})
        r = self._run_parser("block", data)
        out = json.loads(r.stdout)
        assert set(out) == {"decision", "reason"}
        assert out["decision"] == "block"
        assert "Agent repair task" in out["reason"]
        assert "Fresh-review rerun protocol" in out["reason"]
        assert "Local checks to fix" in out["reason"]
        assert "end the turn" in out["reason"]

    def test_coverage_block_action_emits_json_decision_only(self):
        data = json.dumps({
            "action": "block",
            "state": "blocked",
            "final_action": "coverage_block",
            "display": "coverage block",
            "reason": "coverage below minimum",
            "coverage": {"action": "block"},
        })
        r = self._run_parser("block", data)
        assert "coverage block" in r.stderr
        out = json.loads(r.stdout)
        assert out["decision"] == "block"
        assert out["reason"] == "coverage below minimum"

    def test_target_block_action_emits_json_decision_only(self):
        data = json.dumps({
            "action": "block",
            "state": "blocked",
            "final_action": "target_block",
            "display": "target block",
            "reason": "review target incomplete",
            "target": {"policy_action": "block"},
        })
        r = self._run_parser("block", data)
        assert "target block" in r.stderr
        out = json.loads(r.stdout)
        assert out["decision"] == "block"
        assert out["reason"] == "review target incomplete"


class TestShellShimIntegrity:
    """Verify cold-review.sh has no legacy patterns."""

    def test_no_helper_references(self):
        with open(SHELL_SCRIPT, "r", encoding="utf-8") as f:
            content = f.read()
        assert "cold-review-helper" not in content
        assert "cold_eyes/helper.py" not in content.replace("cold_eyes/cli.py", "")

    def test_passes_hook_input_path_to_engine(self):
        with open(SHELL_SCRIPT, "r", encoding="utf-8") as f:
            content = f.read()
        assert "HOOK_INPUT_FILE" in content
        assert "--hook-input-path" in content

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
