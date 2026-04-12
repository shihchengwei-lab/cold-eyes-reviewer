"""Tests for cold_eyes.noise.grouping."""

from cold_eyes.noise.grouping import group_by_root_cause


class TestGroupByRootCause:
    def test_empty_input(self):
        assert group_by_root_cause([]) == []

    def test_single_finding_singleton_cluster(self):
        findings = [{"type": "test_failure", "file": "a.py", "line": "10", "message": "fail"}]
        clusters = group_by_root_cause(findings)
        assert len(clusters) == 1
        assert clusters[0]["confidence"] == "low"  # singleton

    def test_same_file_proximity_grouped(self):
        findings = [
            {"type": "lint_violation", "file": "x.py", "line": "10", "code": "E501", "message": "a"},
            {"type": "lint_violation", "file": "x.py", "line": "15", "code": "E502", "message": "b"},
            {"type": "lint_violation", "file": "x.py", "line": "25", "code": "E503", "message": "c"},
        ]
        clusters = group_by_root_cause(findings)
        # Lines 10 and 15 should be in one cluster, 25 is within 20 of 15 so also grouped
        grouped = [c for c in clusters if c["confidence"] == "medium"]
        assert len(grouped) >= 1

    def test_same_check_across_files_grouped(self):
        findings = [
            {"type": "lint_violation", "file": "a.py", "code": "E501", "message": "long"},
            {"type": "lint_violation", "file": "b.py", "code": "E501", "message": "long"},
        ]
        clusters = group_by_root_cause(findings)
        # Should be grouped by same code
        cross_file = [c for c in clusters if len(c["affected_files"]) == 2]
        assert len(cross_file) == 1
        assert "E501" in cross_file[0]["probable_root_cause"]

    def test_unrelated_findings_separate(self):
        findings = [
            {"type": "test_failure", "file": "a.py", "line": "10", "check": "auth"},
            {"type": "lint_violation", "file": "b.py", "line": "100", "code": "E501"},
        ]
        clusters = group_by_root_cause(findings)
        assert len(clusters) == 2

    def test_cluster_has_required_fields(self):
        findings = [
            {"type": "lint_violation", "file": "x.py", "line": "10", "code": "E501", "message": "a"},
            {"type": "lint_violation", "file": "x.py", "line": "12", "code": "E501", "message": "b"},
        ]
        clusters = group_by_root_cause(findings)
        for c in clusters:
            assert "cluster_id" in c
            assert "probable_root_cause" in c
            assert "affected_files" in c
            assert "confidence" in c
