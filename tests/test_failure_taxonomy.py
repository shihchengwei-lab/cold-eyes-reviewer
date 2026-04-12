"""Tests for cold_eyes.retry.taxonomy."""

from cold_eyes.retry.taxonomy import classify_failure


def _gate_result(gate_name, findings):
    return {"gate_name": gate_name, "status": "fail", "findings": findings}


class TestClassifyFailure:
    def test_test_failure(self):
        gr = _gate_result("test_runner", [{"type": "test_failure", "message": "assert 1 == 2"}])
        ft = classify_failure(gr)
        assert ft["category"] == "test_regression"
        assert ft["subcategory"] == "assertion_error"

    def test_test_error_import(self):
        gr = _gate_result("test_runner", [{"type": "test_error", "message": "ModuleNotFoundError"}])
        ft = classify_failure(gr)
        assert ft["category"] == "missing_import_or_dependency"

    def test_lint_violation(self):
        gr = _gate_result("lint_checker", [{"type": "lint_violation", "message": "E501"}])
        ft = classify_failure(gr)
        assert ft["category"] == "insufficient_validation"

    def test_llm_review_low_confidence(self):
        gr = _gate_result("llm_review", [
            {"type": "review_finding", "severity": "major", "confidence": "medium", "message": "suspicious"}
        ])
        ft = classify_failure(gr)
        assert ft["category"] == "low_confidence_suspicion"

    def test_llm_review_critical_high_confidence(self):
        gr = _gate_result("llm_review", [
            {"type": "review_finding", "severity": "critical", "confidence": "high", "message": "bug"}
        ])
        ft = classify_failure(gr)
        assert ft["category"] == "contract_break"

    def test_llm_review_critical_medium_confidence(self):
        gr = _gate_result("llm_review", [
            {"type": "review_finding", "severity": "critical", "confidence": "medium", "message": "state issue"}
        ])
        ft = classify_failure(gr)
        assert ft["category"] == "state_invariant_suspicion"

    def test_no_findings(self):
        gr = _gate_result("test_runner", [])
        ft = classify_failure(gr)
        assert ft["category"] == "unknown"
        assert ft["subcategory"] == "no_findings"

    def test_unknown_gate(self):
        gr = _gate_result("custom_tool", [{"type": "custom", "message": "err"}])
        ft = classify_failure(gr)
        assert ft["category"] == "unknown"

    def test_transient_flag(self):
        gr = _gate_result("build_checker", [{"type": "build_error", "message": "timeout"}])
        ft = classify_failure(gr)
        assert ft["is_transient"] is True

    def test_typical_fix_populated(self):
        gr = _gate_result("test_runner", [{"type": "test_failure", "message": "assert"}])
        ft = classify_failure(gr)
        assert ft["typical_fix"] != ""
