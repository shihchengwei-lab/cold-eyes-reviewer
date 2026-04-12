"""Tests for evidence-bound claim schema (Phase 3)."""

import json
import os
import sys

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from cold_eyes.schema import validate_review
from cold_eyes.review import parse_review_output
from cold_eyes.policy import calibrate_evidence, apply_policy
from cold_eyes.constants import STATE_PASSED, STATE_BLOCKED


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _wrap(result_obj):
    """Wrap a review result in Claude CLI output format."""
    return json.dumps({"result": json.dumps(result_obj)})


def _issue(severity="critical", confidence="high", evidence=None,
           abstain_condition="", what_would_falsify_this="",
           suggested_validation=""):
    """Build an issue dict with optional evidence fields."""
    d = {
        "check": "test check",
        "verdict": "test verdict",
        "fix": "test fix",
        "severity": severity,
        "confidence": confidence,
        "category": "correctness",
        "file": "test.py",
        "line_hint": "",
    }
    if evidence is not None:
        d["evidence"] = evidence
    if abstain_condition:
        d["abstain_condition"] = abstain_condition
    if what_would_falsify_this:
        d["what_would_falsify_this"] = what_would_falsify_this
    if suggested_validation:
        d["suggested_validation"] = suggested_validation
    return d


# ---------------------------------------------------------------------------
# Schema validation: evidence fields
# ---------------------------------------------------------------------------

class TestSchemaEvidenceFields:
    def test_valid_with_evidence(self):
        review = {
            "schema_version": 1, "review_status": "completed",
            "pass": False, "summary": "issue",
            "issues": [_issue(evidence=["line 5 adds eval()"])],
        }
        ok, errors = validate_review(review)
        assert ok, errors

    def test_evidence_wrong_type_rejected(self):
        review = {
            "schema_version": 1, "review_status": "completed",
            "pass": False, "summary": "issue",
            "issues": [{
                **_issue(), "evidence": "not a list",
            }],
        }
        ok, errors = validate_review(review)
        assert not ok
        assert any("evidence" in e and "list" in e for e in errors)

    def test_falsify_wrong_type_rejected(self):
        review = {
            "schema_version": 1, "review_status": "completed",
            "pass": False, "summary": "issue",
            "issues": [{
                **_issue(), "what_would_falsify_this": 123,
            }],
        }
        ok, errors = validate_review(review)
        assert not ok
        assert any("what_would_falsify_this" in e for e in errors)

    def test_suggested_validation_wrong_type_rejected(self):
        review = {
            "schema_version": 1, "review_status": "completed",
            "pass": False, "summary": "issue",
            "issues": [{
                **_issue(), "suggested_validation": ["list"],
            }],
        }
        ok, errors = validate_review(review)
        assert not ok
        assert any("suggested_validation" in e for e in errors)

    def test_abstain_condition_wrong_type_rejected(self):
        review = {
            "schema_version": 1, "review_status": "completed",
            "pass": False, "summary": "issue",
            "issues": [{
                **_issue(), "abstain_condition": 42,
            }],
        }
        ok, errors = validate_review(review)
        assert not ok
        assert any("abstain_condition" in e for e in errors)

    def test_valid_without_evidence_fields(self):
        """Backward compatible: no evidence fields is still valid."""
        review = {
            "schema_version": 1, "review_status": "completed",
            "pass": False, "summary": "issue",
            "issues": [_issue()],
        }
        ok, errors = validate_review(review)
        assert ok, errors


# ---------------------------------------------------------------------------
# Parse: evidence field defaults
# ---------------------------------------------------------------------------

class TestParseEvidenceDefaults:
    def test_defaults_added(self):
        review = {
            "review_status": "completed", "pass": False,
            "issues": [{"check": "x", "verdict": "y", "fix": "z"}],
            "summary": "test",
        }
        r = parse_review_output(_wrap(review))
        issue = r["issues"][0]
        assert issue["evidence"] == []
        assert issue["what_would_falsify_this"] == ""
        assert issue["suggested_validation"] == ""
        assert issue["abstain_condition"] == ""

    def test_existing_evidence_preserved(self):
        review = {
            "review_status": "completed", "pass": False,
            "issues": [{
                "check": "x", "verdict": "y", "fix": "z",
                "evidence": ["line 10 adds eval()"],
                "what_would_falsify_this": "if input is trusted",
                "suggested_validation": "check caller",
                "abstain_condition": "",
            }],
            "summary": "test",
        }
        r = parse_review_output(_wrap(review))
        issue = r["issues"][0]
        assert issue["evidence"] == ["line 10 adds eval()"]
        assert issue["what_would_falsify_this"] == "if input is trusted"


# ---------------------------------------------------------------------------
# calibrate_evidence: unit tests
# ---------------------------------------------------------------------------

class TestCalibrateEvidence:
    def test_high_confidence_no_evidence_downgraded(self):
        issues = [_issue(confidence="high")]  # no evidence key → defaults to []
        issues[0].setdefault("evidence", [])
        result = calibrate_evidence(issues)
        assert result[0]["confidence"] == "medium"

    def test_high_confidence_with_evidence_kept(self):
        issues = [_issue(confidence="high", evidence=["line 5 deletes auth check"])]
        result = calibrate_evidence(issues)
        assert result[0]["confidence"] == "high"

    def test_medium_confidence_no_evidence_unchanged(self):
        issues = [_issue(confidence="medium")]
        issues[0].setdefault("evidence", [])
        result = calibrate_evidence(issues)
        assert result[0]["confidence"] == "medium"

    def test_abstain_condition_downgrades_high_to_medium(self):
        issues = [_issue(confidence="high",
                         evidence=["line 10"],
                         abstain_condition="assumes no error handler upstream")]
        result = calibrate_evidence(issues)
        # evidence keeps high, but abstain downgrades high→medium
        assert result[0]["confidence"] == "medium"

    def test_abstain_condition_downgrades_medium_to_low(self):
        issues = [_issue(confidence="medium",
                         abstain_condition="assumes function is public")]
        issues[0].setdefault("evidence", [])
        result = calibrate_evidence(issues)
        assert result[0]["confidence"] == "low"

    def test_abstain_low_stays_low(self):
        issues = [_issue(confidence="low",
                         abstain_condition="unsure")]
        issues[0].setdefault("evidence", [])
        result = calibrate_evidence(issues)
        assert result[0]["confidence"] == "low"

    def test_both_rules_stack(self):
        """high + no evidence + abstain → medium (rule1) → low (rule2)."""
        issues = [_issue(confidence="high",
                         abstain_condition="assumes no validation")]
        issues[0].setdefault("evidence", [])
        result = calibrate_evidence(issues)
        assert result[0]["confidence"] == "low"

    def test_empty_abstain_string_no_downgrade(self):
        issues = [_issue(confidence="high",
                         evidence=["line 5"],
                         abstain_condition="")]
        result = calibrate_evidence(issues)
        assert result[0]["confidence"] == "high"

    def test_does_not_mutate_input(self):
        original = _issue(confidence="high")
        original.setdefault("evidence", [])
        issues = [original]
        calibrate_evidence(issues)
        assert original["confidence"] == "high"


# ---------------------------------------------------------------------------
# apply_policy integration: evidence calibration affects decisions
# ---------------------------------------------------------------------------

class TestApplyPolicyEvidenceIntegration:
    def test_high_no_evidence_filtered_by_high_confidence(self):
        """High confidence issue without evidence → downgraded to medium →
        filtered out when min_confidence=high."""
        review = {
            "review_status": "completed", "pass": False,
            "issues": [_issue(severity="critical", confidence="high")],
            "summary": "test",
        }
        outcome = apply_policy(review, "block", "critical", False,
                               min_confidence="high")
        # Downgraded to medium, filtered by high → no issues → pass
        assert outcome["action"] == "pass"
        assert outcome["state"] == STATE_PASSED

    def test_high_with_evidence_survives_high_filter(self):
        """High confidence issue with evidence → stays high → blocks."""
        review = {
            "review_status": "completed", "pass": False,
            "issues": [_issue(severity="critical", confidence="high",
                              evidence=["diff line 5 shows eval(user_input)"])],
            "summary": "test",
        }
        outcome = apply_policy(review, "block", "critical", False,
                               min_confidence="high")
        assert outcome["action"] == "block"
        assert outcome["state"] == STATE_BLOCKED

    def test_abstain_drops_below_medium_filter(self):
        """Medium confidence + abstain → low → filtered by medium."""
        review = {
            "review_status": "completed", "pass": False,
            "issues": [_issue(severity="critical", confidence="medium",
                              abstain_condition="assumes no upstream validation")],
            "summary": "test",
        }
        outcome = apply_policy(review, "block", "critical", False,
                               min_confidence="medium")
        assert outcome["action"] == "pass"
        assert outcome["state"] == STATE_PASSED

    def test_backward_compat_no_evidence_fields(self):
        """Issues from old model (no evidence fields) still work.
        High confidence without evidence key → downgraded to medium.
        With min_confidence=medium, still passes filter → blocks."""
        review = {
            "review_status": "completed", "pass": False,
            "issues": [{
                "check": "bug", "verdict": "bad", "fix": "fix it",
                "severity": "critical", "confidence": "high",
            }],
            "summary": "test",
        }
        outcome = apply_policy(review, "block", "critical", False,
                               min_confidence="medium")
        # high → medium (no evidence), medium passes medium filter → blocks
        assert outcome["action"] == "block"
