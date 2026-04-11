"""Schema validation and parser regression tests."""

import json

from cold_eyes.schema import validate_review
from cold_eyes.review import parse_review_output

# --- Fixtures: valid ---

MINIMAL_VALID = {
    "schema_version": 1,
    "review_status": "completed",
    "pass": True,
    "issues": [],
    "summary": "No issues found.",
}

FULL_VALID = {
    "schema_version": 1,
    "review_status": "completed",
    "pass": False,
    "issues": [
        {
            "severity": "critical",
            "confidence": "high",
            "category": "security",
            "file": "auth.py",
            "line_hint": "42",
            "check": "SQL injection",
            "verdict": "User input passed to query without sanitization",
            "fix": "Use parameterized queries",
        }
    ],
    "summary": "Critical security issue found.",
}

# --- Fixtures: malformed ---

MISSING_STATUS = {"pass": True, "issues": [], "summary": "ok"}
MISSING_ISSUES = {"review_status": "completed", "pass": True, "summary": "ok"}
BAD_ISSUES_TYPE = {"review_status": "completed", "pass": True, "issues": "not_a_list", "summary": "ok"}
BAD_PASS_TYPE = {"review_status": "completed", "pass": "yes", "issues": [], "summary": "ok"}
BAD_SEVERITY = {
    "review_status": "completed", "pass": False, "summary": "x",
    "issues": [{"severity": "extreme", "confidence": "high", "check": "x", "verdict": "x", "fix": "x"}],
}
ISSUE_MISSING_FIELDS = {
    "review_status": "completed", "pass": False, "summary": "x",
    "issues": [{"severity": "major"}],
}
BAD_SCHEMA_VERSION = {
    "schema_version": 999, "review_status": "completed",
    "pass": True, "issues": [], "summary": "ok",
}


class TestValidateReview:
    def test_minimal_valid(self):
        ok, errors = validate_review(MINIMAL_VALID)
        assert ok
        assert errors == []

    def test_full_valid(self):
        ok, errors = validate_review(FULL_VALID)
        assert ok

    def test_not_a_dict(self):
        ok, errors = validate_review([1, 2, 3])
        assert not ok
        assert "not a dict" in errors[0]

    def test_missing_review_status(self):
        ok, errors = validate_review(MISSING_STATUS)
        assert not ok
        assert any("review_status" in e for e in errors)

    def test_missing_issues(self):
        ok, errors = validate_review(MISSING_ISSUES)
        assert not ok
        assert any("issues" in e for e in errors)

    def test_bad_issues_type(self):
        ok, errors = validate_review(BAD_ISSUES_TYPE)
        assert not ok
        assert any("list" in e for e in errors)

    def test_bad_pass_type(self):
        ok, errors = validate_review(BAD_PASS_TYPE)
        assert not ok
        assert any("bool" in e for e in errors)

    def test_bad_severity(self):
        ok, errors = validate_review(BAD_SEVERITY)
        assert not ok
        assert any("severity" in e for e in errors)

    def test_issue_missing_required_fields(self):
        ok, errors = validate_review(ISSUE_MISSING_FIELDS)
        assert not ok
        assert any("missing" in e for e in errors)

    def test_bad_schema_version(self):
        ok, errors = validate_review(BAD_SCHEMA_VERSION)
        assert not ok
        assert any("schema_version" in e for e in errors)


class TestParserRegressions:
    """Verify parse_review_output handles known edge cases."""

    @staticmethod
    def _wrap(result_obj):
        """Wrap a review result in Claude CLI output format."""
        return json.dumps({"result": json.dumps(result_obj)})

    def test_valid_output(self):
        r = parse_review_output(self._wrap(MINIMAL_VALID))
        assert r["review_status"] == "completed"
        assert "validation_errors" not in r

    def test_empty_string(self):
        r = parse_review_output("")
        assert r["review_status"] == "failed"

    def test_invalid_json(self):
        r = parse_review_output("not json at all {{{")
        assert r["review_status"] == "failed"

    def test_half_json(self):
        r = parse_review_output('{"result": "{\\\"pass\\\": true, ')
        assert r["review_status"] == "failed"

    def test_noise_around_json(self):
        inner = json.dumps(MINIMAL_VALID)
        wrapped = json.dumps({"result": f"```json\n{inner}\n```"})
        r = parse_review_output(wrapped)
        assert r["review_status"] == "completed"

    def test_missing_issue_fields_get_defaults(self):
        review = {"review_status": "completed", "pass": False,
                  "issues": [{"check": "x", "verdict": "y", "fix": "z"}],
                  "summary": "test"}
        r = parse_review_output(self._wrap(review))
        issue = r["issues"][0]
        assert issue["severity"] == "major"
        assert issue["confidence"] == "medium"
        assert issue["file"] == "unknown"
