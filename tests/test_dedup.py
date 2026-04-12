"""Tests for cold_eyes.noise.dedup."""

from cold_eyes.noise.dedup import merge_duplicates


class TestMergeDuplicates:
    def test_no_duplicates(self):
        findings = [
            {"type": "test_failure", "file": "a.py", "check": "x", "message": "m1"},
            {"type": "lint_violation", "file": "b.py", "code": "E501", "message": "m2"},
        ]
        result = merge_duplicates(findings)
        assert len(result) == 2
        assert all(r["count"] == 1 for r in result)

    def test_exact_duplicates_merged(self):
        findings = [
            {"type": "test_failure", "file": "a.py", "check": "x", "message": "m1"},
            {"type": "test_failure", "file": "a.py", "check": "x", "message": "m1"},
            {"type": "test_failure", "file": "a.py", "check": "x", "message": "m2"},
        ]
        result = merge_duplicates(findings)
        assert len(result) == 1
        assert result[0]["count"] == 3
        assert "m2" in result[0]["supporting"]

    def test_different_files_not_merged(self):
        findings = [
            {"type": "test_failure", "file": "a.py", "check": "x"},
            {"type": "test_failure", "file": "b.py", "check": "x"},
        ]
        result = merge_duplicates(findings)
        assert len(result) == 2

    def test_empty_input(self):
        assert merge_duplicates([]) == []

    def test_supporting_messages_collected(self):
        findings = [
            {"type": "lint_violation", "file": "x.py", "code": "E501", "message": "line 10"},
            {"type": "lint_violation", "file": "x.py", "code": "E501", "message": "line 20"},
        ]
        result = merge_duplicates(findings)
        assert len(result) == 1
        assert result[0]["count"] == 2
        assert "line 20" in result[0]["supporting"]

    def test_uses_location_fallback(self):
        findings = [
            {"type": "test_failure", "location": "tests/a.py::test_x", "message": "fail"},
            {"type": "test_failure", "location": "tests/a.py::test_x", "message": "fail again"},
        ]
        result = merge_duplicates(findings)
        assert len(result) == 1
