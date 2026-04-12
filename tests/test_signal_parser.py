"""Tests for cold_eyes.retry.signal_parser."""

from cold_eyes.retry.signal_parser import extract_signals


class TestExtractPytest:
    def test_test_failure(self):
        gr = {
            "gate_name": "test_runner",
            "findings": [{"type": "test_failure", "location": "tests/test_a.py::test_x", "message": "assert False"}],
            "raw_output": "",
        }
        signals = extract_signals(gr)
        assert any("test_a.py" in s for s in signals)

    def test_traceback_extraction(self):
        gr = {
            "gate_name": "test_runner",
            "findings": [],
            "raw_output": 'File "src/main.py", line 42, in foo\n    raise ValueError\n',
        }
        signals = extract_signals(gr)
        assert any("src/main.py:42" in s for s in signals)

    def test_ignores_site_packages(self):
        gr = {
            "gate_name": "test_runner",
            "findings": [],
            "raw_output": 'File "/site-packages/pytest/foo.py", line 1\n',
        }
        signals = extract_signals(gr)
        assert not any("site-packages" in s for s in signals)


class TestExtractRuff:
    def test_lint_violation(self):
        gr = {
            "gate_name": "lint_checker",
            "findings": [
                {"type": "lint_violation", "file": "src/x.py",
                 "line": "10", "code": "E501", "message": "E501 line too long"},
            ],
        }
        signals = extract_signals(gr)
        assert len(signals) == 1
        assert "E501" in signals[0]
        assert "src/x.py" in signals[0]


class TestExtractLlmReview:
    def test_review_finding(self):
        gr = {
            "gate_name": "llm_review",
            "findings": [
                {"type": "review_finding", "check": "null check",
                 "severity": "critical", "file": "auth.py", "message": "unsafe"},
            ],
        }
        signals = extract_signals(gr)
        assert any("auth.py" in s for s in signals)
        assert any("critical" in s for s in signals)


class TestExtractGeneric:
    def test_unknown_gate_uses_message(self):
        gr = {
            "gate_name": "custom",
            "findings": [{"message": "something went wrong"}],
        }
        signals = extract_signals(gr)
        assert signals == ["something went wrong"]

    def test_no_findings_uses_raw(self):
        gr = {"gate_name": "custom", "findings": [], "raw_output": "error!"}
        signals = extract_signals(gr)
        assert any("error!" in s for s in signals)

    def test_empty_result(self):
        gr = {"gate_name": "custom", "findings": [], "raw_output": ""}
        signals = extract_signals(gr)
        assert signals == []
