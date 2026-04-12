"""Tests for cold_eyes.noise.fp_memory."""

from unittest.mock import patch

from cold_eyes.noise.fp_memory import apply_fp_memory


class TestApplyFpMemory:
    def test_no_memory_returns_unchanged(self):
        findings = [{"type": "test_failure", "file": "a.py"}]
        with patch("cold_eyes.noise.fp_memory._HAS_MEMORY", False):
            result = apply_fp_memory(findings)
        assert result == findings

    def test_empty_patterns_returns_unchanged(self):
        findings = [{"type": "test_failure", "file": "a.py"}]
        with patch("cold_eyes.noise.fp_memory._HAS_MEMORY", True), \
             patch("cold_eyes.noise.fp_memory.extract_fp_patterns", return_value={"total_overrides": 0}):
            result = apply_fp_memory(findings)
        assert result == findings

    def test_low_match_kept(self):
        findings = [{"type": "review_finding", "file": "a.py", "check": "null check"}]
        with patch("cold_eyes.noise.fp_memory._HAS_MEMORY", True), \
             patch("cold_eyes.noise.fp_memory.extract_fp_patterns",
                   return_value={"total_overrides": 5}), \
             patch("cold_eyes.noise.fp_memory.match_fp_pattern",
                   return_value=(1, ["category"])):
            result = apply_fp_memory(findings)
        assert len(result) == 1
        assert result[0]["fp_match_count"] == 1

    def test_high_match_removed(self):
        findings = [{"type": "review_finding", "file": "a.py", "check": "null check"}]
        with patch("cold_eyes.noise.fp_memory._HAS_MEMORY", True), \
             patch("cold_eyes.noise.fp_memory.extract_fp_patterns",
                   return_value={"total_overrides": 5}), \
             patch("cold_eyes.noise.fp_memory.match_fp_pattern",
                   return_value=(2, ["category", "path"])):
            result = apply_fp_memory(findings)
        assert len(result) == 0

    def test_empty_findings(self):
        result = apply_fp_memory([])
        assert result == []
