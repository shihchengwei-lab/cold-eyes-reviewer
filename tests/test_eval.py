"""Tests for the eval runner."""

import json
import os
import sys
import pytest

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

CASES_DIR = os.path.join(PROJECT_ROOT, "evals", "cases")

from evals.eval_runner import load_cases, run_deterministic, threshold_sweep, _evaluate_case


# ---------------------------------------------------------------------------
# Case loading
# ---------------------------------------------------------------------------

class TestCaseLoading:
    def test_loads_all_cases(self):
        cases = load_cases(CASES_DIR)
        assert len(cases) == 14

    def test_required_fields_present(self):
        cases = load_cases(CASES_DIR)
        required = {"id", "category", "description", "diff", "mock_response", "ground_truth"}
        for case in cases:
            for field in required:
                assert field in case, f"{case['id']} missing {field}"

    def test_valid_categories(self):
        cases = load_cases(CASES_DIR)
        valid = {"true_positive", "acceptable", "stress"}
        for case in cases:
            assert case["category"] in valid, f"{case['id']} has invalid category"

    def test_unique_ids(self):
        cases = load_cases(CASES_DIR)
        ids = [c["id"] for c in cases]
        assert len(ids) == len(set(ids)), "Duplicate case IDs found"

    def test_ground_truth_has_should_block(self):
        cases = load_cases(CASES_DIR)
        for case in cases:
            assert "should_block" in case["ground_truth"], f"{case['id']} missing should_block"

    def test_mock_response_has_result(self):
        cases = load_cases(CASES_DIR)
        for case in cases:
            assert "result" in case["mock_response"], f"{case['id']} mock_response missing result"

    def test_category_counts(self):
        cases = load_cases(CASES_DIR)
        by_cat = {}
        for c in cases:
            by_cat.setdefault(c["category"], []).append(c["id"])
        assert len(by_cat["true_positive"]) == 6
        assert len(by_cat["acceptable"]) == 4
        assert len(by_cat["stress"]) == 4


# ---------------------------------------------------------------------------
# Deterministic mode
# ---------------------------------------------------------------------------

class TestDeterministic:
    def test_all_pass_default_settings(self):
        report = run_deterministic(CASES_DIR)
        assert report["passed"] == report["total"]
        assert report["failed"] == 0

    def test_report_structure(self):
        report = run_deterministic(CASES_DIR)
        assert report["mode"] == "deterministic"
        assert "threshold" in report
        assert "confidence" in report
        assert "total" in report
        assert "passed" in report
        assert "failed" in report
        assert "cases" in report

    def test_case_result_structure(self):
        report = run_deterministic(CASES_DIR)
        for case in report["cases"]:
            assert "id" in case
            assert "category" in case
            assert "expected_block" in case
            assert "actual_block" in case or "actual_action" in case
            assert "match" in case

    def test_true_positives_block(self):
        report = run_deterministic(CASES_DIR)
        tp_cases = [c for c in report["cases"] if c["category"] == "true_positive"]
        for c in tp_cases:
            assert c["expected_block"] is True, f"{c['id']} should expect block"
            assert c["actual_action"] == "block", f"{c['id']} should block"

    def test_acceptable_pass(self):
        report = run_deterministic(CASES_DIR)
        ok_cases = [c for c in report["cases"] if c["category"] == "acceptable"]
        for c in ok_cases:
            assert c["expected_block"] is False, f"{c['id']} should expect pass"
            assert c["actual_action"] in ("pass", "skip"), f"{c['id']} should pass"

    def test_high_confidence_drops_recall(self):
        """With confidence=high, medium-confidence issues get filtered out."""
        report = run_deterministic(CASES_DIR, confidence="high")
        # At least one TP should not block (the one with medium confidence)
        tp_cases = [c for c in report["cases"] if c["category"] == "true_positive"]
        blocked = sum(1 for c in tp_cases if c["actual_action"] == "block")
        assert blocked < len(tp_cases), "High confidence should filter some TPs"

    def test_total_equals_case_count(self):
        report = run_deterministic(CASES_DIR)
        assert report["total"] == 14


# ---------------------------------------------------------------------------
# Threshold sweep
# ---------------------------------------------------------------------------

class TestSweep:
    def test_sweep_report_structure(self):
        report = threshold_sweep(CASES_DIR)
        assert report["mode"] == "sweep"
        assert "combinations" in report
        assert "sweep" in report
        assert "recommended" in report

    def test_sweep_covers_all_combinations(self):
        report = threshold_sweep(CASES_DIR)
        assert report["combinations"] == 6  # 2 thresholds x 3 confidences

    def test_sweep_entry_structure(self):
        report = threshold_sweep(CASES_DIR)
        for entry in report["sweep"]:
            assert "threshold" in entry
            assert "confidence" in entry
            assert "precision" in entry
            assert "recall" in entry
            assert "f1" in entry
            assert "true_positives" in entry
            assert "false_positives" in entry
            assert "false_negatives" in entry
            assert "true_negatives" in entry

    def test_precision_recall_valid(self):
        report = threshold_sweep(CASES_DIR)
        for entry in report["sweep"]:
            assert 0.0 <= entry["precision"] <= 1.0
            assert 0.0 <= entry["recall"] <= 1.0
            assert 0.0 <= entry["f1"] <= 1.0

    def test_recommended_defaults(self):
        """Default settings (critical/medium) should be the recommended combo."""
        report = threshold_sweep(CASES_DIR)
        rec = report["recommended"]
        assert rec["threshold"] == "critical"
        assert rec["confidence"] == "medium"
        assert rec["f1"] == 1.0

    def test_high_confidence_reduces_recall(self):
        report = threshold_sweep(CASES_DIR)
        high = [e for e in report["sweep"] if e["confidence"] == "high"]
        medium = [e for e in report["sweep"] if e["confidence"] == "medium"]
        # For same threshold, high confidence should have <= recall vs medium
        for h, m in zip(sorted(high, key=lambda x: x["threshold"]),
                        sorted(medium, key=lambda x: x["threshold"])):
            assert h["recall"] <= m["recall"]


# ---------------------------------------------------------------------------
# Single case evaluation
# ---------------------------------------------------------------------------

class TestEvaluateCase:
    def test_sql_injection_blocks(self):
        cases = load_cases(CASES_DIR)
        case = next(c for c in cases if c["id"] == "tp-sql-injection")
        result = _evaluate_case(case)
        assert result["actual_block"] is True
        assert result["match"] is True

    def test_style_rename_passes(self):
        cases = load_cases(CASES_DIR)
        case = next(c for c in cases if c["id"] == "ok-style-rename")
        result = _evaluate_case(case)
        assert result["actual_block"] is False
        assert result["match"] is True

    def test_truncated_case_still_blocks(self):
        cases = load_cases(CASES_DIR)
        case = next(c for c in cases if c["id"] == "stress-large-diff")
        result = _evaluate_case(case)
        assert result["actual_block"] is True

    def test_mixed_severity_blocks_on_critical(self):
        cases = load_cases(CASES_DIR)
        case = next(c for c in cases if c["id"] == "stress-mixed-severity")
        result = _evaluate_case(case)
        assert result["actual_block"] is True
