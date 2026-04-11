"""Tests for truncation policy, coverage visibility, and risk controls."""

import json
import os
import sys

import pytest

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from cold_eyes.policy import apply_policy
from cold_eyes.config import load_policy
from cold_eyes.constants import (
    STATE_PASSED, STATE_BLOCKED, STATE_OVERRIDDEN,
    STATE_INFRA_FAILED, STATE_REPORTED, STATE_SKIPPED,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _review_with_issues(severity="critical", confidence="high"):
    return {
        "review_status": "completed",
        "pass": False,
        "issues": [{
            "check": "test issue",
            "verdict": "test verdict",
            "fix": "test fix",
            "severity": severity,
            "confidence": confidence,
        }],
        "summary": "test summary",
    }


def _review_no_issues():
    return {
        "review_status": "completed",
        "pass": True,
        "issues": [],
        "summary": "all clear",
    }


def _review_infra_failed():
    return {
        "review_status": "failed",
        "pass": True,
        "issues": [],
        "summary": "timeout",
    }


# ---------------------------------------------------------------------------
# Truncation Policy: warn (default, current behavior)
# ---------------------------------------------------------------------------

class TestTruncationPolicyWarn:
    def test_warn_with_issues_blocks(self):
        review = _review_with_issues()
        outcome = apply_policy(review, "block", "critical", False,
                               truncated=True, skipped_files=["a.py"],
                               truncation_policy="warn")
        assert outcome["action"] == "block"

    def test_warn_no_issues_passes(self):
        review = _review_no_issues()
        outcome = apply_policy(review, "block", "critical", False,
                               truncated=True, skipped_files=["a.py"],
                               truncation_policy="warn")
        assert outcome["action"] == "pass"
        assert outcome["state"] == STATE_PASSED

    def test_warn_is_default(self):
        """No truncation_policy arg should behave like warn."""
        review = _review_no_issues()
        outcome = apply_policy(review, "block", "critical", False,
                               truncated=True, skipped_files=["a.py"])
        assert outcome["action"] == "pass"

    def test_warn_not_truncated_normal(self):
        review = _review_with_issues()
        outcome = apply_policy(review, "block", "critical", False,
                               truncated=False, truncation_policy="warn")
        assert outcome["action"] == "block"


# ---------------------------------------------------------------------------
# Truncation Policy: soft-pass
# ---------------------------------------------------------------------------

class TestTruncationPolicySoftPass:
    def test_soft_pass_no_issues_truncated_passes(self):
        review = _review_no_issues()
        outcome = apply_policy(review, "block", "critical", False,
                               truncated=True, skipped_files=["a.py", "b.py"],
                               truncation_policy="soft-pass")
        assert outcome["action"] == "pass"
        assert outcome["state"] == STATE_PASSED
        assert outcome["truncated"] is True
        assert outcome["skipped_count"] == 2

    def test_soft_pass_with_issues_still_blocks(self):
        review = _review_with_issues()
        outcome = apply_policy(review, "block", "critical", False,
                               truncated=True, skipped_files=["a.py"],
                               truncation_policy="soft-pass")
        assert outcome["action"] == "block"

    def test_soft_pass_not_truncated_normal(self):
        review = _review_no_issues()
        outcome = apply_policy(review, "block", "critical", False,
                               truncated=False, truncation_policy="soft-pass")
        assert outcome["action"] == "pass"

    def test_soft_pass_report_mode_unaffected(self):
        review = _review_no_issues()
        outcome = apply_policy(review, "report", "critical", False,
                               truncated=True, skipped_files=["a.py"],
                               truncation_policy="soft-pass")
        assert outcome["action"] == "pass"


# ---------------------------------------------------------------------------
# Truncation Policy: fail-closed
# ---------------------------------------------------------------------------

class TestTruncationPolicyFailClosed:
    def test_fail_closed_no_issues_truncated_blocks(self):
        review = _review_no_issues()
        outcome = apply_policy(review, "block", "critical", False,
                               truncated=True, skipped_files=["a.py"],
                               truncation_policy="fail-closed")
        assert outcome["action"] == "block"
        assert outcome["state"] == STATE_BLOCKED

    def test_fail_closed_with_issues_truncated_blocks(self):
        review = _review_with_issues()
        outcome = apply_policy(review, "block", "critical", False,
                               truncated=True, skipped_files=["a.py"],
                               truncation_policy="fail-closed")
        assert outcome["action"] == "block"

    def test_fail_closed_not_truncated_normal(self):
        review = _review_no_issues()
        outcome = apply_policy(review, "block", "critical", False,
                               truncated=False, truncation_policy="fail-closed")
        assert outcome["action"] == "pass"

    def test_fail_closed_override_bypasses(self):
        review = _review_no_issues()
        outcome = apply_policy(review, "block", "critical", True,
                               truncated=True, skipped_files=["a.py"],
                               truncation_policy="fail-closed")
        # Override (allow_once=True) should bypass fail-closed
        assert outcome["action"] == "pass"

    def test_fail_closed_report_mode_unaffected(self):
        review = _review_no_issues()
        outcome = apply_policy(review, "report", "critical", False,
                               truncated=True, skipped_files=["a.py"],
                               truncation_policy="fail-closed")
        assert outcome["action"] == "pass"

    def test_fail_closed_display_message(self):
        review = _review_no_issues()
        outcome = apply_policy(review, "block", "critical", False,
                               truncated=True, skipped_files=["a.py", "b.py"],
                               truncation_policy="fail-closed")
        assert "fail-closed" in outcome["display"]
        assert "2 files unreviewed" in outcome["display"]


# ---------------------------------------------------------------------------
# Truncation Policy: config resolution
# ---------------------------------------------------------------------------

class TestTruncationPolicyConfig:
    def test_policy_file_key(self, tmp_path):
        policy_file = tmp_path / ".cold-review-policy.yml"
        policy_file.write_text("truncation_policy: fail-closed\n")
        policy = load_policy(str(tmp_path))
        assert policy.get("truncation_policy") == "fail-closed"

    def test_unknown_key_ignored(self, tmp_path):
        policy_file = tmp_path / ".cold-review-policy.yml"
        policy_file.write_text("unknown_key: value\n")
        policy = load_policy(str(tmp_path))
        assert "unknown_key" not in policy

    def test_valid_truncation_values(self, tmp_path):
        for val in ("warn", "soft-pass", "fail-closed"):
            policy_file = tmp_path / ".cold-review-policy.yml"
            policy_file.write_text(f"truncation_policy: {val}\n")
            policy = load_policy(str(tmp_path))
            assert policy["truncation_policy"] == val


# ---------------------------------------------------------------------------
# Coverage visibility
# ---------------------------------------------------------------------------

class TestCoverageVisibility:
    """Coverage fields are added by engine.run(), not by apply_policy().
    Test apply_policy includes truncated/skipped_count in outcomes."""

    def test_pass_outcome_has_truncated(self):
        review = _review_no_issues()
        outcome = apply_policy(review, "block", "critical", False,
                               truncated=False)
        assert "truncated" in outcome
        assert outcome["truncated"] is False

    def test_block_outcome_has_skipped_count(self):
        review = _review_with_issues()
        outcome = apply_policy(review, "block", "critical", False,
                               truncated=True, skipped_files=["a.py", "b.py"])
        assert "skipped_count" in outcome
        assert outcome["skipped_count"] == 2


# ---------------------------------------------------------------------------
# State reachability
# ---------------------------------------------------------------------------

class TestStateReachability:
    def test_passed(self):
        review = _review_no_issues()
        outcome = apply_policy(review, "block", "critical", False)
        assert outcome["state"] == STATE_PASSED

    def test_blocked(self):
        review = _review_with_issues()
        outcome = apply_policy(review, "block", "critical", False)
        assert outcome["state"] == STATE_BLOCKED

    def test_overridden(self):
        review = _review_with_issues()
        outcome = apply_policy(review, "block", "critical", True,
                               override_reason="testing")
        assert outcome["state"] == STATE_OVERRIDDEN

    def test_infra_failed_block(self):
        review = _review_infra_failed()
        outcome = apply_policy(review, "block", "critical", False)
        assert outcome["state"] == STATE_INFRA_FAILED

    def test_infra_failed_report(self):
        review = _review_infra_failed()
        outcome = apply_policy(review, "report", "critical", False)
        assert outcome["state"] == STATE_INFRA_FAILED

    def test_reported(self):
        review = _review_with_issues()
        outcome = apply_policy(review, "report", "critical", False)
        assert outcome["state"] == STATE_REPORTED
