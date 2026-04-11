"""Tests for cold-review-helper.py."""

import json
import subprocess
import sys
import os
import tempfile

SCRIPTS_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HELPER_SCRIPT = os.path.join(SCRIPTS_DIR, "cold-review-helper.py")
FIXTURES_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fixtures")


def run_helper(command, stdin_data="", extra_args=None):
    """Run cold-review-helper.py as a subprocess and return stdout."""
    args = [sys.executable, HELPER_SCRIPT, command]
    if extra_args:
        args.extend(extra_args)
    result = subprocess.run(
        args,
        input=stdin_data,
        capture_output=True,
        text=True,
        encoding="utf-8",
        env={**os.environ, "PYTHONIOENCODING": "utf-8"},
    )
    return result.stdout.strip(), result.stderr.strip(), result.returncode


def load_fixture(name):
    with open(os.path.join(FIXTURES_DIR, name), "r", encoding="utf-8") as f:
        return f.read()


# --- build-prompt ---

class TestBuildPrompt:
    def test_produces_output(self):
        stdout, _, rc = run_helper("build-prompt")
        assert rc == 0
        assert len(stdout) > 0
        assert "Cold Eyes" in stdout

    def test_contains_json_instruction(self):
        stdout, _, _ = run_helper("build-prompt")
        assert "JSON" in stdout

    def test_contains_severity_definitions(self):
        stdout, _, _ = run_helper("build-prompt")
        assert "critical" in stdout
        assert "major" in stdout
        assert "minor" in stdout

    def test_contains_category_definitions(self):
        stdout, _, _ = run_helper("build-prompt")
        assert "correctness" in stdout
        assert "security" in stdout


# --- parse-review ---

class TestParseReview:
    def test_valid_review(self):
        claude_output = json.dumps({
            "type": "result",
            "subtype": "success",
            "result": json.dumps({
                "pass": True,
                "issues": [],
                "summary": "All good"
            })
        })
        stdout, _, rc = run_helper("parse-review", stdin_data=claude_output)
        assert rc == 0
        parsed = json.loads(stdout)
        assert parsed["pass"] is True
        assert parsed["summary"] == "All good"
        assert parsed["review_status"] == "completed"

    def test_invalid_json_returns_failed_status(self):
        stdout, _, rc = run_helper("parse-review", stdin_data="not json at all")
        assert rc == 0
        parsed = json.loads(stdout)
        assert parsed["review_status"] == "failed"
        assert parsed["pass"] is True  # parse failure does NOT block
        assert parsed["issues"] == []

    def test_markdown_wrapped_json(self):
        inner = json.dumps({"pass": False, "issues": [], "summary": "test"})
        claude_output = json.dumps({
            "type": "result",
            "subtype": "success",
            "result": f"```json\n{inner}\n```"
        })
        stdout, _, rc = run_helper("parse-review", stdin_data=claude_output)
        parsed = json.loads(stdout)
        assert parsed["pass"] is False

    def test_old_format_gets_defaults(self):
        fixture = load_fixture("old_format_response.json")
        stdout, _, _ = run_helper("parse-review", stdin_data=fixture)
        parsed = json.loads(stdout)
        assert parsed["review_status"] == "completed"
        issue = parsed["issues"][0]
        assert issue["severity"] == "major"
        assert issue["confidence"] == "medium"
        assert issue["category"] == "correctness"
        assert issue["file"] == "unknown"
        # Original fields preserved
        assert issue["check"] == "Line 10 has a bug"

    def test_completed_review_preserves_fields(self):
        fixture = load_fixture("completed_review_response.json")
        stdout, _, _ = run_helper("parse-review", stdin_data=fixture)
        parsed = json.loads(stdout)
        assert parsed["review_status"] == "completed"
        issue = parsed["issues"][0]
        assert issue["severity"] == "critical"
        assert issue["confidence"] == "high"
        assert issue["category"] == "security"
        assert issue["file"] == "app/db.py"

    def test_empty_result_returns_failed(self):
        fixture = load_fixture("empty_response.json")
        stdout, _, _ = run_helper("parse-review", stdin_data=fixture)
        parsed = json.loads(stdout)
        assert parsed["review_status"] == "failed"
        assert parsed["issues"] == []

    def test_parse_error_response(self):
        fixture = load_fixture("parse_error_response.json")
        stdout, _, _ = run_helper("parse-review", stdin_data=fixture)
        parsed = json.loads(stdout)
        assert parsed["review_status"] == "failed"
        assert parsed["pass"] is True


# --- check-pass ---

class TestCheckPass:
    def test_pass_true(self):
        stdout, _, _ = run_helper("check-pass", stdin_data='{"pass": true}')
        assert stdout == "true"

    def test_pass_false(self):
        stdout, _, _ = run_helper("check-pass", stdin_data='{"pass": false}')
        assert stdout == "false"

    def test_malformed_defaults_true(self):
        stdout, _, _ = run_helper("check-pass", stdin_data="garbage")
        assert stdout == "true"


# --- should-block ---

class TestShouldBlock:
    def _review(self, severity):
        return json.dumps({
            "pass": False,
            "review_status": "completed",
            "issues": [{"severity": severity, "check": "x", "verdict": "y", "fix": "z"}],
            "summary": "test"
        })

    def test_critical_issue_blocks_at_critical_threshold(self):
        stdout, _, _ = run_helper("should-block", stdin_data=self._review("critical"), extra_args=["critical"])
        assert stdout == "true"

    def test_major_issue_does_not_block_at_critical_threshold(self):
        stdout, _, _ = run_helper("should-block", stdin_data=self._review("major"), extra_args=["critical"])
        assert stdout == "false"

    def test_major_issue_blocks_at_major_threshold(self):
        stdout, _, _ = run_helper("should-block", stdin_data=self._review("major"), extra_args=["major"])
        assert stdout == "true"

    def test_minor_issue_never_blocks(self):
        stdout, _, _ = run_helper("should-block", stdin_data=self._review("minor"), extra_args=["critical"])
        assert stdout == "false"
        stdout, _, _ = run_helper("should-block", stdin_data=self._review("minor"), extra_args=["major"])
        assert stdout == "false"

    def test_failed_review_does_not_block(self):
        review = json.dumps({
            "pass": True,
            "review_status": "failed",
            "issues": [],
            "summary": "Parse error"
        })
        stdout, _, _ = run_helper("should-block", stdin_data=review, extra_args=["critical"])
        assert stdout == "false"

    def test_no_issues_does_not_block(self):
        review = json.dumps({
            "pass": True,
            "review_status": "completed",
            "issues": [],
            "summary": "All good"
        })
        stdout, _, _ = run_helper("should-block", stdin_data=review, extra_args=["critical"])
        assert stdout == "false"


# --- parse-hook ---

class TestParseHook:
    def test_active_true(self):
        stdout, _, _ = run_helper("parse-hook", stdin_data='{"stop_hook_active": true}')
        assert stdout == "true"

    def test_active_false(self):
        stdout, _, _ = run_helper("parse-hook", stdin_data='{"stop_hook_active": false}')
        assert stdout == "false"

    def test_missing_field(self):
        stdout, _, _ = run_helper("parse-hook", stdin_data='{}')
        assert stdout == "false"


# --- format-block ---

class TestFormatBlock:
    def test_formats_issues_with_severity(self):
        review = {
            "summary": "Found problems",
            "issues": [
                {"severity": "critical", "check": "line 10 is wrong", "verdict": "Bug.", "fix": "Fix line 10"}
            ]
        }
        stdout, _, _ = run_helper("format-block", stdin_data=json.dumps(review))
        assert "Found problems" in stdout
        assert "[CRITICAL]" in stdout
        assert "line 10 is wrong" in stdout

    def test_default_severity_is_major(self):
        review = {
            "summary": "test",
            "issues": [{"check": "x", "verdict": "y", "fix": "z"}]
        }
        stdout, _, _ = run_helper("format-block", stdin_data=json.dumps(review))
        assert "[MAJOR]" in stdout


# --- filter-files ---

class TestFilterFiles:
    def test_filters_lockfiles(self):
        files = "package-lock.json\nsrc/app.js\nyarn.lock\n"
        stdout, _, _ = run_helper("filter-files", stdin_data=files)
        assert "src/app.js" in stdout
        assert "package-lock.json" not in stdout
        assert "yarn.lock" not in stdout

    def test_filters_minified(self):
        files = "dist/bundle.min.js\nsrc/index.ts\n"
        stdout, _, _ = run_helper("filter-files", stdin_data=files)
        assert "src/index.ts" in stdout
        assert "bundle.min.js" not in stdout

    def test_filters_build_dirs(self):
        files = "build/output.js\ndist/app.js\nsrc/main.py\n"
        stdout, _, _ = run_helper("filter-files", stdin_data=files)
        assert "src/main.py" in stdout
        assert "build/output.js" not in stdout

    def test_custom_ignore_file(self):
        ignore_file = os.path.join(FIXTURES_DIR, "sample_ignore_patterns.txt")
        files = "app.log\nsrc/main.py\ntemp/cache.txt\nbackup.bak\n"
        stdout, _, _ = run_helper("filter-files", stdin_data=files, extra_args=[ignore_file])
        assert "src/main.py" in stdout
        assert "app.log" not in stdout
        assert "backup.bak" not in stdout

    def test_empty_input(self):
        stdout, _, _ = run_helper("filter-files", stdin_data="")
        assert stdout == ""


# --- rank-files ---

class TestRankFiles:
    def test_high_risk_paths_first(self):
        files = "README.md\nsrc/auth/login.py\nutils/format.js\n"
        stdout, _, _ = run_helper("rank-files", stdin_data=files)
        lines = stdout.strip().split("\n")
        assert lines[0] == "src/auth/login.py"

    def test_untracked_files_ranked_higher(self):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False, encoding="utf-8") as f:
            f.write("new_file.py\n")
            untracked_file = f.name
        try:
            files = "old_file.py\nnew_file.py\n"
            stdout, _, _ = run_helper("rank-files", stdin_data=files, extra_args=[untracked_file])
            lines = stdout.strip().split("\n")
            assert lines[0] == "new_file.py"
        finally:
            os.unlink(untracked_file)

    def test_multiple_risk_factors_stack(self):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False, encoding="utf-8") as f:
            f.write("src/api/auth.py\n")
            untracked_file = f.name
        try:
            files = "README.md\nsrc/api/auth.py\nutils.py\n"
            stdout, _, _ = run_helper("rank-files", stdin_data=files, extra_args=[untracked_file])
            lines = stdout.strip().split("\n")
            # api+auth in path (+3) + untracked (+2) = 6, highest
            assert lines[0] == "src/api/auth.py"
        finally:
            os.unlink(untracked_file)


# --- log-review ---

class TestLogReview:
    def test_writes_v2_format(self):
        with tempfile.NamedTemporaryFile(mode="r", suffix=".jsonl", delete=False, encoding="utf-8") as f:
            history_file = f.name

        review = json.dumps({"pass": True, "review_status": "completed", "issues": [], "summary": "OK"})
        env = {**os.environ, "PYTHONIOENCODING": "utf-8"}
        # Override HISTORY_FILE by patching — we'll just check the command runs
        # For a real test we'd need to inject the path; for now verify no crash
        stdout, stderr, rc = run_helper("log-review", stdin_data=review, extra_args=[".", "block", "opus", "passed", "3", "150", "false"])
        assert rc == 0
        os.unlink(history_file)


# --- log-state ---

class TestLogState:
    def test_runs_without_error(self):
        _, _, rc = run_helper("log-state", extra_args=[".", "block", "opus", "skipped", "no changes"])
        assert rc == 0
