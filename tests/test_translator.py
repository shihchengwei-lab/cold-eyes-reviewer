"""Tests for cold_eyes.retry.translator."""

from cold_eyes.retry.brief import validate_brief
from cold_eyes.retry.translator import translate


def _failed_gate(gate_name, findings):
    return {"gate_name": gate_name, "status": "fail", "findings": findings, "raw_output": ""}


def _passing_gate(gate_name):
    return {"gate_name": gate_name, "status": "pass", "findings": [], "raw_output": ""}


class TestTranslate:
    def test_single_test_failure(self):
        gr = _failed_gate("test_runner", [
            {"type": "test_failure", "location": "tests/test_a.py::test_x", "message": "assert False"}
        ])
        brief = translate([gr])
        assert "test_runner" in brief["failed_gates"]
        assert "test_regression" in brief["probable_failure_types"]
        assert brief["retry_strategy"] == "repair_test_and_code_mismatch"
        ok, _ = validate_brief(brief)
        assert ok

    def test_llm_review_failure(self):
        gr = _failed_gate("llm_review", [
            {"type": "review_finding", "severity": "critical", "confidence": "high",
             "file": "auth.py", "check": "null check", "message": "unsafe"}
        ])
        brief = translate([gr])
        assert "llm_review" in brief["failed_gates"]
        assert "auth.py" in brief["files_to_reinspect"]

    def test_multiple_gate_failures(self):
        gr1 = _failed_gate("test_runner", [
            {"type": "test_failure", "location": "tests/test_a.py::test_x", "message": "assert False"}
        ])
        gr2 = _failed_gate("lint_checker", [
            {"type": "lint_violation", "file": "src/x.py", "line": "10", "code": "E501", "message": "too long"}
        ])
        brief = translate([gr1, gr2])
        assert len(brief["failed_gates"]) == 2

    def test_passing_gates_ignored(self):
        gr_pass = _passing_gate("test_runner")
        gr_fail = _failed_gate("lint_checker", [{"type": "lint_violation", "file": "x.py"}])
        brief = translate([gr_pass, gr_fail])
        assert brief["failed_gates"] == ["lint_checker"]

    def test_contract_constraints_preserved(self):
        gr = _failed_gate("test_runner", [{"type": "test_failure", "message": "fail"}])
        contracts = [{"must_not_break": ["login flow", "session handling"]}]
        brief = translate([gr], contracts=contracts)
        assert "login flow" in brief["must_preserve_constraints"]

    def test_high_retry_count_aborts(self):
        gr = _failed_gate("test_runner", [{"type": "test_failure", "message": "fail"}])
        brief = translate([gr], retry_count=3)
        assert brief["retry_strategy"] == "abort_and_escalate"

    def test_stop_if_repeated_after_two(self):
        gr = _failed_gate("test_runner", [{"type": "test_failure", "message": "fail"}])
        brief = translate([gr], retry_count=2)
        assert brief["stop_if_repeated"] is True

    def test_empty_gate_results(self):
        brief = translate([])
        assert brief["failure_summary"] == "unknown failure"
        ok, errors = validate_brief(brief)
        assert ok, errors
