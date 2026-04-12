"""Tests for FP memory integration in calibration (WP2+WP3)."""

import os
import sys

import pytest

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from cold_eyes.policy import calibrate_evidence
from cold_eyes.memory import compute_category_baselines


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _issue(category="state_invariant", file="src/models/order.py",
           check="Missing pre-condition check before state transition",
           severity="major", confidence="high", evidence=None,
           abstain_condition=""):
    d = {
        "category": category,
        "file": file,
        "check": check,
        "verdict": "test verdict",
        "fix": "test fix",
        "severity": severity,
        "confidence": confidence,
    }
    if evidence is not None:
        d["evidence"] = evidence
    if abstain_condition:
        d["abstain_condition"] = abstain_condition
    return d


def _fp_patterns(category_patterns=None, path_patterns=None,
                 check_patterns=None, total_overrides=10, total_issues=15):
    return {
        "category_patterns": category_patterns or {},
        "path_patterns": path_patterns or {},
        "check_patterns": check_patterns or {},
        "total_overrides": total_overrides,
        "total_issues": total_issues,
    }


# ---------------------------------------------------------------------------
# Rule 3: FP pattern match downgrades confidence
# ---------------------------------------------------------------------------

class TestFpPatternCalibration:
    def test_single_category_match_downgrades_once(self):
        fp = _fp_patterns(category_patterns={"state_invariant": 5})
        issues = [_issue(confidence="high", evidence=["real evidence"])]
        result = calibrate_evidence(issues, fp_patterns=fp)
        assert result[0]["confidence"] == "medium"
        assert result[0]["fp_match_count"] == 1

    def test_double_match_downgrades_twice(self):
        fp = _fp_patterns(
            category_patterns={"state_invariant": 5},
            path_patterns={"src/models": 4},
        )
        issues = [_issue(confidence="high", evidence=["real evidence"])]
        result = calibrate_evidence(issues, fp_patterns=fp)
        assert result[0]["confidence"] == "low"
        assert result[0]["fp_match_count"] == 2

    def test_triple_match_capped_at_two_downgrades(self):
        fp = _fp_patterns(
            category_patterns={"state_invariant": 5},
            path_patterns={"src/models": 4},
            check_patterns={"missing pre-condition check before state": 3},
        )
        issues = [_issue(confidence="high", evidence=["real evidence"])]
        result = calibrate_evidence(issues, fp_patterns=fp)
        # high → medium → low (max 2 downgrades), even though 3 match types
        assert result[0]["confidence"] == "low"
        assert result[0]["fp_match_count"] == 3

    def test_no_fp_match_no_downgrade(self):
        fp = _fp_patterns(category_patterns={"auth_permission": 5})
        issues = [_issue(confidence="high", evidence=["real evidence"],
                         category="state_invariant")]
        result = calibrate_evidence(issues, fp_patterns=fp)
        assert result[0]["confidence"] == "high"
        assert "fp_match_count" not in result[0]

    def test_none_fp_patterns_no_effect(self):
        issues = [_issue(confidence="high", evidence=["e"])]
        result = calibrate_evidence(issues, fp_patterns=None)
        assert result[0]["confidence"] == "high"

    def test_empty_fp_patterns_no_effect(self):
        fp = _fp_patterns()
        issues = [_issue(confidence="high", evidence=["e"])]
        result = calibrate_evidence(issues, fp_patterns=fp)
        assert result[0]["confidence"] == "high"

    def test_medium_confidence_fp_match_goes_to_low(self):
        fp = _fp_patterns(category_patterns={"state_invariant": 5})
        issues = [_issue(confidence="medium", evidence=["e"])]
        result = calibrate_evidence(issues, fp_patterns=fp)
        assert result[0]["confidence"] == "low"

    def test_low_stays_low(self):
        fp = _fp_patterns(category_patterns={"state_invariant": 5})
        issues = [_issue(confidence="low")]
        result = calibrate_evidence(issues, fp_patterns=fp)
        assert result[0]["confidence"] == "low"

    def test_rules_stack_evidence_then_fp(self):
        """Rule 1 (no evidence → medium) + Rule 3 (FP match → low)."""
        fp = _fp_patterns(category_patterns={"state_invariant": 5})
        issues = [_issue(confidence="high")]  # no evidence
        result = calibrate_evidence(issues, fp_patterns=fp)
        # high → medium (rule 1) → low (rule 3)
        assert result[0]["confidence"] == "low"

    def test_rules_stack_abstain_then_fp(self):
        """Rule 2 (abstain → -1) + Rule 3 (FP match → -1)."""
        fp = _fp_patterns(category_patterns={"state_invariant": 5})
        issues = [_issue(confidence="high", evidence=["e"],
                         abstain_condition="unknown upstream")]
        result = calibrate_evidence(issues, fp_patterns=fp)
        # high → medium (rule 2) → low (rule 3)
        assert result[0]["confidence"] == "low"

    def test_multiple_issues_independent(self):
        fp = _fp_patterns(category_patterns={"state_invariant": 5})
        issues = [
            _issue(confidence="high", evidence=["e"], category="state_invariant"),
            _issue(confidence="high", evidence=["e"], category="auth_permission"),
        ]
        result = calibrate_evidence(issues, fp_patterns=fp)
        assert result[0]["confidence"] == "medium"  # matched
        assert result[1]["confidence"] == "high"     # not matched


# ---------------------------------------------------------------------------
# Rule 4: category confidence cap
# ---------------------------------------------------------------------------

class TestCategoryBaselines:
    def test_high_ratio_capped_low(self):
        fp = _fp_patterns(category_patterns={"noisy_cat": 6}, total_overrides=4)
        # total_reviews estimate: 4 * 3 = 12, ratio = 6/12 = 0.5 → cap low
        issues = [_issue(confidence="high", evidence=["e"], category="noisy_cat")]
        result = calibrate_evidence(issues, fp_patterns=fp)
        assert result[0]["confidence"] == "low"

    def test_medium_ratio_capped_medium(self):
        fp = _fp_patterns(category_patterns={"mid_cat": 4}, total_overrides=4)
        # total_reviews estimate: 12, ratio = 4/12 = 0.333 → cap medium
        issues = [_issue(confidence="high", evidence=["e"], category="mid_cat")]
        result = calibrate_evidence(issues, fp_patterns=fp)
        assert result[0]["confidence"] == "medium"

    def test_low_ratio_no_cap(self):
        fp = _fp_patterns(category_patterns={"ok_cat": 2}, total_overrides=10)
        # total_reviews estimate: 30, ratio = 2/30 = 0.067 → no cap from Rule 4
        # But Rule 3 still fires (category match) → high → medium
        issues = [_issue(confidence="high", evidence=["e"], category="ok_cat")]
        result = calibrate_evidence(issues, fp_patterns=fp)
        assert result[0]["confidence"] == "medium"  # Rule 3 only, no Rule 4 cap

    def test_low_ratio_no_cap_isolated(self):
        """Category not in FP patterns at all → no Rule 3, no Rule 4."""
        fp = _fp_patterns(category_patterns={"other_cat": 2}, total_overrides=10)
        issues = [_issue(confidence="high", evidence=["e"], category="clean_cat")]
        result = calibrate_evidence(issues, fp_patterns=fp)
        assert result[0]["confidence"] == "high"

    def test_cap_does_not_upgrade(self):
        """If confidence is already below cap, cap doesn't raise it."""
        fp = _fp_patterns(category_patterns={"mid_cat": 4}, total_overrides=4)
        issues = [_issue(confidence="low", category="mid_cat")]
        result = calibrate_evidence(issues, fp_patterns=fp)
        assert result[0]["confidence"] == "low"

    def test_category_not_in_patterns_no_cap(self):
        fp = _fp_patterns(category_patterns={"other": 6}, total_overrides=4)
        issues = [_issue(confidence="high", evidence=["e"], category="state_invariant")]
        result = calibrate_evidence(issues, fp_patterns=fp)
        # No FP match downgrade either (different category)
        assert result[0]["confidence"] == "high"


# ---------------------------------------------------------------------------
# compute_category_baselines: unit tests
# ---------------------------------------------------------------------------

class TestComputeCategoryBaselines:
    def test_empty_patterns(self):
        assert compute_category_baselines({}) == {}
        assert compute_category_baselines(None) == {}

    def test_no_category_patterns(self):
        fp = _fp_patterns(category_patterns={})
        assert compute_category_baselines(fp) == {}

    def test_high_ratio(self):
        fp = _fp_patterns(category_patterns={"noisy": 10}, total_overrides=5)
        caps = compute_category_baselines(fp)
        assert caps["noisy"] == "low"

    def test_medium_ratio(self):
        fp = _fp_patterns(category_patterns={"mid": 5}, total_overrides=5)
        # estimate total = 15, ratio = 5/15 = 0.333
        caps = compute_category_baselines(fp)
        assert caps["mid"] == "medium"

    def test_low_ratio_excluded(self):
        fp = _fp_patterns(category_patterns={"ok": 1}, total_overrides=10)
        caps = compute_category_baselines(fp)
        assert "ok" not in caps

    def test_explicit_total_reviews(self):
        fp = _fp_patterns(category_patterns={"cat": 5}, total_overrides=100)
        # With explicit total_reviews=10: ratio = 5/10 = 0.5 → low
        caps = compute_category_baselines(fp, total_reviews=10)
        assert caps["cat"] == "low"

    def test_mixed_categories(self):
        fp = _fp_patterns(
            category_patterns={"noisy": 10, "mid": 5, "ok": 1},
            total_overrides=5,
        )
        caps = compute_category_baselines(fp)
        assert caps.get("noisy") == "low"
        assert caps.get("mid") == "medium"
        assert "ok" not in caps
