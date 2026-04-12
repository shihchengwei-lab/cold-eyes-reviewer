"""Tests for cold_eyes.runner.metrics."""

from unittest.mock import patch

from cold_eyes.runner.metrics import aggregate_metrics, collect_metrics
from cold_eyes.runner.session_runner import run_session


def _mock_outcome(action="pass", state="passed"):
    return {"action": action, "state": state,
            "review": {"issues": [], "pass": True, "review_status": "completed", "summary": "ok"}}


def _quick_session(state="passed"):
    """Create a minimal session for metrics testing."""
    with patch("cold_eyes.engine.run", return_value=_mock_outcome()):
        return run_session("test", ["src/main.py"], available_gate_ids=["llm_review"])


class TestCollectMetrics:
    def test_passing_session(self):
        session = _quick_session()
        m = collect_metrics(session)
        assert m["final_state"] == "passed"
        assert m["total_gates_run"] >= 1
        assert m["gates_passed"] >= 1
        assert m["retry_count"] == 0

    def test_failed_session(self):
        fail_outcome = {
            "action": "block", "state": "blocked",
            "review": {"issues": [{"check": "x", "severity": "critical",
                                    "confidence": "high", "file": "a.py",
                                    "verdict": "bad", "fix": "fix"}],
                       "pass": False, "review_status": "completed", "summary": "bad"},
        }
        with patch("cold_eyes.engine.run", return_value=fail_outcome):
            session = run_session("test", ["src/main.py"],
                                  available_gate_ids=["llm_review"], max_retries=1)
        m = collect_metrics(session)
        assert m["final_state"] == "failed_terminal"
        assert m["total_findings"] >= 1

    def test_has_expected_keys(self):
        session = _quick_session()
        m = collect_metrics(session)
        expected_keys = {"session_id", "final_state", "total_gates_run",
                         "gates_passed", "gates_failed", "total_findings",
                         "retry_count", "contracts_count", "total_duration_ms"}
        assert expected_keys.issubset(m.keys())


class TestAggregateMetrics:
    def test_empty(self):
        result = aggregate_metrics([])
        assert result["session_count"] == 0

    def test_multiple_sessions(self):
        sessions = [_quick_session() for _ in range(3)]
        result = aggregate_metrics(sessions)
        assert result["session_count"] == 3
        assert result["passed_sessions"] == 3
        assert result["pass_rate"] == 1.0
        assert result["total_retries"] == 0

    def test_mixed_sessions(self):
        pass_session = _quick_session()
        fail_outcome = {
            "action": "block", "state": "blocked",
            "review": {"issues": [{"check": "x", "severity": "critical",
                                    "confidence": "high", "file": "a.py",
                                    "verdict": "bad", "fix": "fix"}],
                       "pass": False, "review_status": "completed", "summary": "bad"},
        }
        with patch("cold_eyes.engine.run", return_value=fail_outcome):
            fail_session = run_session("test", ["src/main.py"],
                                       available_gate_ids=["llm_review"], max_retries=1)
        result = aggregate_metrics([pass_session, fail_session])
        assert result["session_count"] == 2
        assert result["passed_sessions"] == 1
        assert result["failed_sessions"] == 1
        assert result["pass_rate"] == 0.5
