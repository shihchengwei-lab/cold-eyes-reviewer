"""Tests for cold_eyes.noise.retry_suppression."""

from cold_eyes.noise.retry_suppression import suppress_seen, suppress_seen_with_report


class TestSuppressSeen:
    def test_no_previous(self):
        findings = [{"type": "test_failure", "file": "a.py", "check": "x"}]
        result = suppress_seen(findings, [])
        assert len(result) == 1

    def test_exact_match_suppressed(self):
        findings = [{"type": "test_failure", "file": "a.py", "check": "x"}]
        previous = [{"type": "test_failure", "file": "a.py", "check": "x"}]
        result = suppress_seen(findings, previous)
        assert len(result) == 0

    def test_different_file_not_suppressed(self):
        findings = [{"type": "test_failure", "file": "b.py", "check": "x"}]
        previous = [{"type": "test_failure", "file": "a.py", "check": "x"}]
        result = suppress_seen(findings, previous)
        assert len(result) == 1

    def test_mixed_suppression(self):
        findings = [
            {"type": "test_failure", "file": "a.py", "check": "x"},
            {"type": "lint_violation", "file": "b.py", "code": "E501"},
        ]
        previous = [{"type": "test_failure", "file": "a.py", "check": "x"}]
        result = suppress_seen(findings, previous)
        assert len(result) == 1
        assert result[0]["file"] == "b.py"

    def test_empty_findings(self):
        assert suppress_seen([], [{"type": "x"}]) == []


class TestSuppressSeenWithReport:
    def test_report_counts(self):
        findings = [
            {"type": "test_failure", "file": "a.py", "check": "x"},
            {"type": "lint_violation", "file": "b.py", "code": "E501"},
        ]
        previous = [{"type": "test_failure", "file": "a.py", "check": "x"}]
        kept, report = suppress_seen_with_report(findings, previous)
        assert report["total_input"] == 2
        assert report["kept"] == 1
        assert report["suppressed"] == 1

    def test_uses_location_fallback(self):
        findings = [{"type": "test_failure", "location": "tests/a.py::test_x"}]
        previous = [{"type": "test_failure", "location": "tests/a.py::test_x"}]
        result = suppress_seen(findings, previous)
        assert len(result) == 0
