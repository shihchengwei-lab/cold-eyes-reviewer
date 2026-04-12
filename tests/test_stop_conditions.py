"""Tests for cold_eyes.retry.stop."""

from cold_eyes.retry.stop import should_stop
from cold_eyes.session.schema import create_session


def _session_with_briefs(briefs, gate_results=None):
    s = create_session("test")
    s["retry_briefs"] = briefs
    s["gate_results"] = gate_results or []
    return s


class TestShouldStop:
    def test_no_briefs_no_stop(self):
        s = _session_with_briefs([])
        stop, reason = should_stop(s)
        assert stop is False

    def test_max_retries(self):
        briefs = [{"retry_strategy": "x"} for _ in range(4)]
        s = _session_with_briefs(briefs)
        stop, reason = should_stop(s)
        assert stop is True
        assert "max retries" in reason

    def test_custom_max_retries(self):
        briefs = [{"retry_strategy": "x"} for _ in range(6)]
        s = _session_with_briefs(briefs)
        stop, _ = should_stop(s, max_retries=5)
        assert stop is True

    def test_same_failure_repeated(self):
        briefs = [
            {"probable_failure_types": ["test_regression"], "retry_strategy": "repair_test_and_code_mismatch"},
            {"probable_failure_types": ["test_regression"], "retry_strategy": "repair_test_and_code_mismatch"},
        ]
        s = _session_with_briefs(briefs)
        stop, reason = should_stop(s)
        assert stop is True
        assert "repeated" in reason

    def test_different_failures_no_stop(self):
        briefs = [
            {"probable_failure_types": ["test_regression"], "retry_strategy": "a"},
            {"probable_failure_types": ["lint_violation"], "retry_strategy": "b"},
        ]
        s = _session_with_briefs(briefs)
        stop, _ = should_stop(s)
        assert stop is False

    def test_no_progress_findings(self):
        gate_results = [
            {"gate_name": "test_runner", "findings": [{"x": 1}, {"x": 2}]},
            {"gate_name": "lint_checker", "findings": [{"x": 1}]},
            {"gate_name": "test_runner", "findings": [{"x": 1}, {"x": 2}]},
            {"gate_name": "lint_checker", "findings": [{"x": 1}]},
        ]
        s = _session_with_briefs([{"retry_strategy": "a"}, {"retry_strategy": "b"}], gate_results)
        s["gate_plan"] = ["test_runner", "lint_checker"]
        stop, reason = should_stop(s)
        assert stop is True
        assert "not decreasing" in reason

    def test_all_gates_passing_stops(self):
        gate_results = [
            {"gate_name": "test_runner", "status": "pass", "findings": []},
            {"gate_name": "lint_checker", "status": "pass", "findings": []},
        ]
        s = _session_with_briefs([{"retry_strategy": "a"}, {"retry_strategy": "b"}], gate_results)
        stop, reason = should_stop(s)
        assert stop is True
        assert "passing" in reason

    def test_fix_scope_expanding(self):
        briefs = [
            {"probable_failure_types": ["a"], "retry_strategy": "x", "minimal_fix_scope": ["a.py"]},
            {"probable_failure_types": ["b"], "retry_strategy": "y",
             "minimal_fix_scope": ["a.py", "b.py", "c.py", "d.py", "e.py", "f.py"]},
        ]
        s = _session_with_briefs(briefs)
        stop, reason = should_stop(s)
        assert stop is True
        assert "expanding" in reason

    def test_single_brief_no_stop(self):
        briefs = [{"probable_failure_types": ["test_regression"], "retry_strategy": "a"}]
        s = _session_with_briefs(briefs)
        stop, _ = should_stop(s)
        assert stop is False
