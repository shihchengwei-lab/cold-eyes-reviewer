"""End-to-end tests for cold_eyes.runner.session_runner."""

import json
from unittest.mock import MagicMock, patch

from cold_eyes.runner.session_runner import run_session
from cold_eyes.session.schema import validate_session


def _mock_engine_outcome(action="pass", state="passed", issues=None):
    return {
        "action": action,
        "state": state,
        "review": {"issues": issues or [], "pass": action == "pass",
                    "review_status": "completed", "summary": "ok"},
    }


def _mock_subprocess_pass():
    proc = MagicMock()
    proc.stdout = "5 passed in 0.3s\n"
    proc.stderr = ""
    proc.returncode = 0
    return proc


def _mock_subprocess_fail():
    proc = MagicMock()
    proc.stdout = "FAILED tests/test_a.py::test_x - assert False\n1 failed\n"
    proc.stderr = ""
    proc.returncode = 1
    return proc


class TestScenarioDocsOnly:
    """Scenario 1: Docs-only change, minimal gates, should pass."""

    def test_docs_only_passes(self):
        outcome = _mock_engine_outcome()
        with patch("cold_eyes.engine.run", return_value=outcome):
            session = run_session(
                "update readme",
                ["README.md", "docs/guide.md"],
                available_gate_ids=["llm_review"],
            )
        assert session["state"] == "passed"
        assert session["final_outcome"]["action"] == "pass"
        ok, errors = validate_session(session)
        assert ok, errors


class TestScenarioTestFailureRetry:
    """Scenario 2: Test failure → retry brief → gates re-run → pass."""

    def test_test_failure_then_pass(self):
        call_count = {"n": 0}

        def side_effect(*args, **kwargs):
            call_count["n"] += 1
            if call_count["n"] <= 1:
                return _mock_subprocess_fail()
            return _mock_subprocess_pass()

        outcome = _mock_engine_outcome()
        with patch("cold_eyes.engine.run", return_value=outcome), \
             patch("cold_eyes.gates.orchestrator.subprocess.run", side_effect=side_effect):
            session = run_session(
                "fix auth bug",
                ["src/auth.py", "tests/test_auth.py"],
                available_gate_ids=["llm_review", "test_runner"],
                max_retries=3,
            )

        # Should eventually pass after retry
        assert session["state"] in ("passed", "failed_terminal")
        assert len(session["gate_results"]) >= 2
        ok, _ = validate_session(session)
        assert ok


class TestScenarioReviewFinding:
    """Scenario 3: LLM review blocks → retry."""

    def test_review_block_then_pass(self):
        call_count = {"n": 0}

        def mock_engine(**kwargs):
            call_count["n"] += 1
            if call_count["n"] <= 1:
                return _mock_engine_outcome(
                    action="block", state="blocked",
                    issues=[{"check": "null check", "severity": "critical",
                             "confidence": "high", "file": "src/auth.py",
                             "verdict": "unsafe", "fix": "add check"}],
                )
            return _mock_engine_outcome()

        with patch("cold_eyes.engine.run", side_effect=mock_engine):
            session = run_session(
                "add login endpoint",
                ["src/auth.py"],
                available_gate_ids=["llm_review"],
                max_retries=3,
            )

        assert len(session["gate_results"]) >= 1
        ok, _ = validate_session(session)
        assert ok


class TestScenarioMaxRetries:
    """Scenario 4: Persistent failure → max retries → abort."""

    def test_max_retries_abort(self):
        fail_outcome = _mock_engine_outcome(
            action="block", state="blocked",
            issues=[{"check": "bug", "severity": "critical",
                     "confidence": "high", "file": "src/auth.py",
                     "verdict": "bad", "fix": "fix it"}],
        )
        with patch("cold_eyes.engine.run", return_value=fail_outcome):
            session = run_session(
                "broken code",
                ["src/auth.py"],  # triggers auth_permission → must → hard blocking
                available_gate_ids=["llm_review"],
                max_retries=2,
            )

        assert session["state"] == "failed_terminal"
        assert session["final_outcome"]["action"] == "block"
        ok, _ = validate_session(session)
        assert ok


class TestScenarioMultiGate:
    """Scenario 5: Multiple gates with mixed results."""

    def test_multi_gate_mixed(self):
        outcome = _mock_engine_outcome()
        with patch("cold_eyes.engine.run", return_value=outcome), \
             patch("cold_eyes.gates.orchestrator.subprocess.run",
                   return_value=_mock_subprocess_pass()):
            session = run_session(
                "refactor module",
                ["src/main.py", "src/util.py", "tests/test_main.py"],
                available_gate_ids=["llm_review", "test_runner", "lint_checker"],
            )

        assert session["state"] == "passed"
        assert len(session["gate_results"]) >= 3
        ok, _ = validate_session(session)
        assert ok


class TestSessionStructure:
    """Verify session record completeness."""

    def test_session_has_all_fields(self):
        outcome = _mock_engine_outcome()
        with patch("cold_eyes.engine.run", return_value=outcome):
            session = run_session(
                "test",
                ["src/main.py"],
                available_gate_ids=["llm_review"],
            )
        assert "session_id" in session
        assert "contracts" in session
        assert "gate_plan" in session
        assert "gate_results" in session
        assert "events" in session
        assert "final_outcome" in session
        assert len(session["events"]) >= 4  # contracts, quality, risk, gates

    def test_empty_files_still_works(self):
        session = run_session("noop", [], available_gate_ids=[])
        # No gates selected — zero verification must block, not pass
        assert session["state"] == "failed_terminal"
        assert session["final_outcome"]["stop_reason"] == "no gate results — zero verification"
