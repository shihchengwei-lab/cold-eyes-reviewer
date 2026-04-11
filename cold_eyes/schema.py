"""Review output schema definition and validation."""

from cold_eyes.constants import SCHEMA_VERSION, SEVERITY_ORDER, CONFIDENCE_ORDER

# --- Schema definition ---

REQUIRED_FIELDS = {"review_status", "pass", "issues", "summary"}

VALID_REVIEW_STATUSES = {"completed", "failed"}
VALID_SEVERITIES = set(SEVERITY_ORDER.keys())
VALID_CONFIDENCES = set(CONFIDENCE_ORDER.keys())

ISSUE_REQUIRED_FIELDS = {"check", "verdict", "fix", "severity", "confidence"}


def validate_review(review):
    """Validate a parsed review dict against the schema.

    Returns (ok: bool, errors: list[str]).
    Does NOT reject on extra fields — forward-compatible.
    """
    errors = []

    if not isinstance(review, dict):
        return False, ["review is not a dict"]

    for field in REQUIRED_FIELDS:
        if field not in review:
            errors.append(f"missing required field: {field}")

    if "review_status" in review:
        if review["review_status"] not in VALID_REVIEW_STATUSES:
            errors.append(f"invalid review_status: {review['review_status']}")

    if "pass" in review and not isinstance(review["pass"], bool):
        errors.append(f"'pass' must be bool, got {type(review['pass']).__name__}")

    if "issues" in review:
        if not isinstance(review["issues"], list):
            errors.append("'issues' must be a list")
        else:
            for i, issue in enumerate(review["issues"]):
                if not isinstance(issue, dict):
                    errors.append(f"issue[{i}] is not a dict")
                    continue
                for field in ISSUE_REQUIRED_FIELDS:
                    if field not in issue:
                        errors.append(f"issue[{i}] missing: {field}")
                if "severity" in issue and issue["severity"] not in VALID_SEVERITIES:
                    errors.append(f"issue[{i}] invalid severity: {issue['severity']}")
                if "confidence" in issue and issue["confidence"] not in VALID_CONFIDENCES:
                    errors.append(f"issue[{i}] invalid confidence: {issue['confidence']}")

    sv = review.get("schema_version")
    if sv is not None and sv != SCHEMA_VERSION:
        errors.append(f"schema_version mismatch: expected {SCHEMA_VERSION}, got {sv}")

    return len(errors) == 0, errors
