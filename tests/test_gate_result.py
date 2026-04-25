"""Tests for cold_eyes.gates.result."""

import json

from cold_eyes.gates.result import normalize_result


class TestNormalizeGeneric:
    def test_pass(self):
        r = normalize_result("unknown_gate", "all good", 0)
        assert r["status"] == "pass"
        assert r["findings"] == []

    def test_fail(self):
        r = normalize_result("unknown_gate", "something broke", 1)
        assert r["status"] == "fail"
        assert len(r["findings"]) == 1
        assert r["findings"][0]["type"] == "raw_error"

    def test_duration_and_blocking(self):
        r = normalize_result("x", "", 0, duration_ms=500, blocking_mode="hard")
        assert r["duration_ms"] == 500
        assert r["blocking_mode"] == "hard"

    def test_raw_output_capped(self):
        r = normalize_result("x", "A" * 10000, 1)
        assert len(r["raw_output"]) == 5000


class TestParsePytest:
    def test_pass(self):
        r = normalize_result("test_runner", "5 passed in 0.5s", 0)
        assert r["status"] == "pass"

    def test_failure_extracted(self):
        output = "FAILED tests/test_foo.py::TestBar::test_baz - AssertionError: 1 != 2\n1 failed"
        r = normalize_result("test_runner", output, 1)
        assert r["status"] == "fail"
        assert len(r["findings"]) == 1
        assert r["findings"][0]["type"] == "test_failure"
        assert "test_foo.py" in r["findings"][0]["location"]

    def test_error_extracted(self):
        output = "ERROR tests/test_foo.py::test_baz\n1 error"
        r = normalize_result("test_runner", output, 1)
        assert r["findings"][0]["type"] == "test_error"

    def test_multiple_failures(self):
        output = (
            "FAILED tests/a.py::test_1 - assert False\n"
            "FAILED tests/b.py::test_2 - assert False\n"
            "2 failed"
        )
        r = normalize_result("test_runner", output, 1)
        assert len(r["findings"]) == 2


class TestParseRuff:
    def test_pass(self):
        r = normalize_result("lint_checker", "", 0)
        assert r["status"] == "pass"

    def test_violations_extracted(self):
        output = "src/main.py:10:5: E501 Line too long (130 > 120)\nsrc/util.py:3:1: F401 unused import"
        r = normalize_result("lint_checker", output, 1)
        assert r["status"] == "fail"
        assert len(r["findings"]) == 2
        assert r["findings"][0]["type"] == "lint_violation"
        assert r["findings"][0]["file"] == "src/main.py"


class TestParseLlmReview:
    def test_passed_outcome(self):
        outcome = {"state": "passed", "action": "pass", "issues": []}
        r = normalize_result("llm_review", json.dumps(outcome), 0)
        assert r["status"] == "pass"
        assert r["findings"] == []

    def test_blocked_outcome_with_issues(self):
        outcome = {
            "state": "blocked",
            "action": "block",
            "issues": [
                {"check": "missing null check", "severity": "critical",
                 "confidence": "high", "file": "auth.py", "verdict": "unsafe"},
            ],
        }
        r = normalize_result("llm_review", json.dumps(outcome), 1)
        assert r["status"] == "fail"
        assert len(r["findings"]) == 1
        assert r["findings"][0]["type"] == "review_finding"
        assert r["findings"][0]["file"] == "auth.py"

    def test_invalid_json_falls_back(self):
        r = normalize_result("llm_review", "not json", 1)
        assert r["status"] == "fail"
        assert r["findings"][0]["type"] == "raw_error"

    def test_coverage_block_is_finding_not_model_issue(self):
        outcome = {
            "state": "blocked",
            "action": "block",
            "issues": [],
            "coverage": {
                "action": "block",
                "reason": "coverage_below_minimum",
                "coverage_pct": 50.0,
                "unreviewed_files": ["src/auth.py"],
            },
        }
        r = normalize_result("llm_review", json.dumps(outcome), 0)
        assert r["status"] == "fail"
        assert r["findings"][0]["type"] == "coverage_block"
        assert r["findings"][0]["unreviewed_files"] == ["src/auth.py"]

    def test_coverage_warn_is_warning(self):
        outcome = {
            "state": "passed",
            "action": "pass",
            "issues": [],
            "coverage": {
                "action": "warn",
                "reason": "coverage_below_minimum",
            },
        }
        r = normalize_result("llm_review", json.dumps(outcome), 0)
        assert r["status"] == "pass"
        assert r["findings"] == []
        assert r["warnings"] == ["coverage warning: coverage_below_minimum"]

    def test_target_block_is_finding_not_model_issue(self):
        outcome = {
            "state": "blocked",
            "action": "block",
            "issues": [],
            "target": {
                "policy_action": "block",
                "policy_reason": "partial_stage",
                "unreviewed_files": ["src/auth.py"],
                "unreviewed_partial_stage_files": ["src/auth.py"],
                "high_risk_unreviewed_files": ["src/auth.py"],
            },
        }
        r = normalize_result("llm_review", json.dumps(outcome), 0)
        assert r["status"] == "fail"
        assert r["findings"][0]["type"] == "target_block"
        assert r["findings"][0]["partial_stage_files"] == ["src/auth.py"]
