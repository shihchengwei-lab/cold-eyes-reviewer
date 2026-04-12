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
                # Optional evidence-bound fields — validate type if present
                if "evidence" in issue and not isinstance(issue["evidence"], list):
                    errors.append(f"issue[{i}] 'evidence' must be a list")
                if "what_would_falsify_this" in issue and not isinstance(issue["what_would_falsify_this"], str):
                    errors.append(f"issue[{i}] 'what_would_falsify_this' must be a string")
                if "suggested_validation" in issue and not isinstance(issue["suggested_validation"], str):
                    errors.append(f"issue[{i}] 'suggested_validation' must be a string")
                if "abstain_condition" in issue and not isinstance(issue["abstain_condition"], str):
                    errors.append(f"issue[{i}] 'abstain_condition' must be a string")

    # Validate pass/issues consistency
    if review.get("pass") is True and isinstance(review.get("issues"), list):
        dominated = [
            i for i in review["issues"]
            if isinstance(i, dict) and i.get("severity") in ("critical", "major")
        ]
        if dominated:
            severities = [i["severity"] for i in dominated]
            errors.append(
                f"pass=true contradicts {len(dominated)} "
                f"{'/'.join(sorted(set(severities)))} issue(s); "
                f"setting pass to false"
            )
            review["pass"] = False

    sv = review.get("schema_version")
    if sv is not None and sv != SCHEMA_VERSION:
        errors.append(f"schema_version mismatch: expected {SCHEMA_VERSION}, got {sv}")

    return len(errors) == 0, errors
