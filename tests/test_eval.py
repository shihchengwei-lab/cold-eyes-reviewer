"""Tests for the eval runner."""

import json
import os
import sys
import pytest

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

CASES_DIR = os.path.join(PROJECT_ROOT, "evals", "cases")

from evals.eval_runner import (
    load_cases, run_deterministic, threshold_sweep, _evaluate_case,
    validate_manifest, _make_report, format_markdown, save_report, compare_reports,
    regression_check,
)


# ---------------------------------------------------------------------------
# Case loading
# ---------------------------------------------------------------------------

class TestCaseLoading:
    def test_loads_all_cases(self):
        cases = load_cases(CASES_DIR)
        assert len(cases) == 33

    def test_required_fields_present(self):
        cases = load_cases(CASES_DIR)
        required = {"id", "category", "description", "diff", "mock_response", "ground_truth"}
        for case in cases:
            for field in required:
                assert field in case, f"{case['id']} missing {field}"

    def test_valid_categories(self):
        cases = load_cases(CASES_DIR)
        valid = {"true_positive", "acceptable", "stress", "false_negative", "edge", "evidence", "fp_memory"}
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
        assert len(by_cat["true_positive"]) == 10
        assert len(by_cat["acceptable"]) == 4
        assert len(by_cat["stress"]) == 5
        assert len(by_cat["false_negative"]) == 4
        assert len(by_cat["edge"]) == 4


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
        assert report["total"] == 33


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


# ---------------------------------------------------------------------------
# Manifest validation
# ---------------------------------------------------------------------------

class TestManifest:
    def test_manifest_exists(self):
        manifest_path = os.path.join(PROJECT_ROOT, "evals", "manifest.json")
        assert os.path.isfile(manifest_path)

    def test_manifest_valid(self):
        ok, errors = validate_manifest(CASES_DIR)
        assert ok, f"Manifest validation failed: {errors}"

    def test_manifest_matches_case_count(self):
        manifest_path = os.path.join(PROJECT_ROOT, "evals", "manifest.json")
        with open(manifest_path, "r", encoding="utf-8") as f:
            manifest = json.load(f)
        cases = load_cases(CASES_DIR)
        assert manifest["total_cases"] == len(cases)

    def test_manifest_category_matches_case_file(self):
        manifest_path = os.path.join(PROJECT_ROOT, "evals", "manifest.json")
        with open(manifest_path, "r", encoding="utf-8") as f:
            manifest = json.load(f)
        case_by_id = {c["id"]: c for c in load_cases(CASES_DIR)}
        for cat, info in manifest["categories"].items():
            for cid in info["cases"]:
                assert cid in case_by_id, f"{cid} in manifest but not in cases"
                assert case_by_id[cid]["category"] == cat, \
                    f"{cid}: manifest says {cat}, file says {case_by_id[cid]['category']}"


# ---------------------------------------------------------------------------
# New category tests
# ---------------------------------------------------------------------------

class TestNewCategories:
    def test_false_negatives_pass(self):
        report = run_deterministic(CASES_DIR)
        fn_cases = [c for c in report["cases"] if c["category"] == "false_negative"]
        assert len(fn_cases) == 4
        for c in fn_cases:
            assert c["expected_block"] is False, f"{c['id']} should not expect block"
            assert c["actual_action"] in ("pass", "skip"), f"{c['id']} should pass"

    def test_edge_cases_match(self):
        report = run_deterministic(CASES_DIR)
        edge_cases = [c for c in report["cases"] if c["category"] == "edge"]
        assert len(edge_cases) == 4
        for c in edge_cases:
            assert c["match"] is True, f"{c['id']} did not match ground truth"

    def test_new_true_positives_block(self):
        cases = load_cases(CASES_DIR)
        for cid in ["tp-path-traversal", "tp-eval-injection"]:
            case = next(c for c in cases if c["id"] == cid)
            result = _evaluate_case(case)
            assert result["actual_block"] is True, f"{cid} should block"
            assert result["match"] is True, f"{cid} should match"

    def test_stress_all_minor_passes(self):
        cases = load_cases(CASES_DIR)
        case = next(c for c in cases if c["id"] == "stress-all-minor")
        result = _evaluate_case(case)
        assert result["actual_block"] is False
        assert result["match"] is True


# ---------------------------------------------------------------------------
# Report metadata
# ---------------------------------------------------------------------------

class TestReportMetadata:
    def test_deterministic_has_metadata(self):
        report = run_deterministic(CASES_DIR)
        assert "cold_eyes_version" in report
        assert "timestamp" in report
        assert "eval_schema_version" in report
        assert report["eval_schema_version"] == 1

    def test_sweep_has_metadata(self):
        report = threshold_sweep(CASES_DIR)
        assert "cold_eyes_version" in report
        assert "timestamp" in report
        assert report["timestamp"].endswith("Z")


# ---------------------------------------------------------------------------
# Markdown formatting
# ---------------------------------------------------------------------------

class TestFormatMarkdown:
    def test_deterministic_markdown(self):
        report = run_deterministic(CASES_DIR)
        md = format_markdown(report)
        assert "# Cold Eyes Eval Report" in md
        assert "deterministic" in md
        assert "| ID |" in md
        assert "Category Summary" in md

    def test_sweep_markdown(self):
        report = threshold_sweep(CASES_DIR)
        md = format_markdown(report)
        assert "Threshold Sweep" in md
        assert "Recommended:" in md
        assert "Precision" in md


# ---------------------------------------------------------------------------
# Report comparison
# ---------------------------------------------------------------------------

class TestCompareReports:
    def test_same_report_no_changes(self):
        report = run_deterministic(CASES_DIR)
        diff = compare_reports(report, report)
        assert diff["cases_added"] == []
        assert diff["cases_removed"] == []
        assert diff["cases_changed"] == []


# ---------------------------------------------------------------------------
# Report saving
# ---------------------------------------------------------------------------

class TestSaveReport:
    def test_save_creates_files(self, tmp_path):
        report = run_deterministic(CASES_DIR)
        paths = save_report(report, output_dir=str(tmp_path), fmt="both")
        assert "json" in paths
        assert "markdown" in paths
        assert os.path.isfile(paths["json"])
        assert os.path.isfile(paths["markdown"])
        with open(paths["json"], "r", encoding="utf-8") as f:
            loaded = json.load(f)
        assert loaded["mode"] == "deterministic"


# ---------------------------------------------------------------------------
# Regression check
# ---------------------------------------------------------------------------

class TestRegressionCheck:
    def test_baseline_vs_self_no_regression(self, tmp_path):
        """Running current cases against their own baseline → no regression."""
        baseline = run_deterministic(CASES_DIR)
        bp = tmp_path / "baseline.json"
        with open(bp, "w", encoding="utf-8") as f:
            json.dump(baseline, f)
        result = regression_check(str(bp), CASES_DIR)
        assert result["regressed"] is False
        assert result["regressions"] == []
        assert result["cases_added"] == []
        assert result["cases_removed"] == []

    def test_action_change_without_match_change_not_regression(self, tmp_path):
        """If actual_block changes but both sides still match → not a regression."""
        current = run_deterministic(CASES_DIR)
        baseline = json.loads(json.dumps(current))
        # Flip actual_block for one case but keep match=True in baseline
        for case in baseline["cases"]:
            if case["id"] == "ok-style-rename":
                case["actual_block"] = True
                case["actual_action"] = "block"
                break
        bp = tmp_path / "baseline.json"
        with open(bp, "w", encoding="utf-8") as f:
            json.dump(baseline, f)
        result = regression_check(str(bp), CASES_DIR)
        assert result["regressed"] is False

    def test_regression_detected_with_high_confidence(self, tmp_path):
        """Baseline at medium confidence (all pass) vs current at high → some fail = regression."""
        baseline = run_deterministic(CASES_DIR, confidence="medium")
        assert baseline["passed"] == baseline["total"]  # all match
        bp = tmp_path / "baseline.json"
        with open(bp, "w", encoding="utf-8") as f:
            json.dump(baseline, f)
        # Run with confidence=high — some TPs lose match
        result = regression_check(str(bp), CASES_DIR, confidence="high")
        assert result["regressed"] is True
        assert len(result["regressions"]) > 0
        for reg in result["regressions"]:
            assert reg["match_a"] is True
            assert reg["match_b"] is False


# ---------------------------------------------------------------------------
# FP memory eval cases
# ---------------------------------------------------------------------------

class TestFpMemoryEval:
    def test_fp_memory_cases_present(self):
        cases = load_cases(CASES_DIR)
        fp_cases = [c for c in cases if c["category"] == "fp_memory"]
        assert len(fp_cases) == 3

    def test_fp_memory_known_pattern_passes(self):
        cases = load_cases(CASES_DIR)
        case = next(c for c in cases if c["id"] == "fp-memory-known-pattern")
        result = _evaluate_case(case)
        assert result["actual_block"] is False
        assert result["match"] is True

    def test_fp_memory_category_cap_passes(self):
        cases = load_cases(CASES_DIR)
        case = next(c for c in cases if c["id"] == "fp-memory-category-cap")
        result = _evaluate_case(case)
        assert result["actual_block"] is False
        assert result["match"] is True

    def test_fp_memory_no_match_blocks(self):
        cases = load_cases(CASES_DIR)
        case = next(c for c in cases if c["id"] == "fp-memory-no-match")
        result = _evaluate_case(case)
        assert result["actual_block"] is True
        assert result["match"] is True

    def test_fp_memory_all_match_deterministic(self):
        report = run_deterministic(CASES_DIR)
        fp_cases = [c for c in report["cases"] if c["category"] == "fp_memory"]
        for c in fp_cases:
            assert c["match"] is True, f"{c['id']} did not match ground truth"
