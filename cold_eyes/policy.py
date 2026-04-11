"""Policy enforcement: confidence filter, block decision, formatting."""

from cold_eyes.constants import SEVERITY_ORDER, CONFIDENCE_ORDER


def filter_by_confidence(issues, min_confidence="medium"):
    """Remove issues below the confidence threshold. Deterministic hard filter."""
    threshold = CONFIDENCE_ORDER.get(min_confidence, 2)
    return [i for i in issues if CONFIDENCE_ORDER.get(i.get("confidence", "medium"), 2) >= threshold]


def format_block_reason(review, truncated=False, skipped_count=0):
    """Format review into human-readable block reason."""
    summary = review.get("summary", "")
    issues = review.get("issues", [])
    lines = [f"Cold Eyes Review \u2014 {summary}"]
    for issue in issues:
        sev = issue.get("severity", "major").upper()
        line_hint = issue.get("line_hint", "")
        check = issue.get("check", "")
        verdict = issue.get("verdict", "")
        fix = issue.get("fix", "")
        hint_part = f" (~{line_hint})" if line_hint else ""
        lines.append(f"  - [{sev}]{hint_part} \u6aa2\u67e5\uff1a{check}")
        lines.append(f"    \u5224\u6c7a\uff1a{verdict}")
        lines.append(f"    \u6307\u793a\uff1a{fix}")
    if truncated:
        lines.append(f"  \u26a0 \u5be9\u67e5\u4e0d\u5b8c\u6574\uff1adiff \u8d85\u904e token \u9810\u7b97\uff0c{skipped_count} \u500b\u6a94\u6848\u672a\u5be9\u67e5\u3002")
    return "\n".join(lines)


def apply_policy(review, mode, threshold, allow_once, min_confidence="medium",
                 truncated=False, skipped_files=None, override_reason=""):
    """Determine final outcome. Return FinalOutcome dict.

    FinalOutcome keys: action, state, reason, display, truncated, skipped_count
    The review in the outcome has issues filtered by confidence.
    """
    if skipped_files is None:
        skipped_files = []
    skipped_count = len(skipped_files)
    engine_ok = review.get("review_status") != "failed"

    # --- Infrastructure failure ---
    if not engine_ok:
        error_detail = review.get("summary", "unknown error")
        if mode == "block":
            if allow_once:
                reason_suffix = f" [{override_reason}]" if override_reason else ""
                return {
                    "action": "pass",
                    "state": "overridden",
                    "reason": override_reason,
                    "display": f"cold-review: override \u2014 infra failure bypass (ALLOW_ONCE){reason_suffix}",
                }
            return {
                "action": "block",
                "state": "infra_failed",
                "reason": (
                    f"Cold Eyes Review \u2014 infrastructure failure: {error_detail}.\n"
                    "To override: COLD_REVIEW_ALLOW_ONCE=1 COLD_REVIEW_OVERRIDE_REASON='<reason>'"
                ),
                "display": "cold-review: blocking (infrastructure failure)",
            }
        # report mode \u2014 log but pass
        return {
            "action": "pass",
            "state": "failed",
            "reason": error_detail,
            "display": f"cold-review: report logged (infra failure: {error_detail})",
        }

    # --- Confidence filter (hard gate) ---
    filtered_issues = filter_by_confidence(review.get("issues", []), min_confidence)
    review = {**review, "issues": filtered_issues}

    # --- Review completed ---
    threshold_level = SEVERITY_ORDER.get(threshold, 3)
    max_severity = 0
    for issue in filtered_issues:
        level = SEVERITY_ORDER.get(issue.get("severity", "major"), 2)
        max_severity = max(max_severity, level)

    should_block = max_severity >= threshold_level
    review_pass = review.get("pass", True)

    if mode == "report":
        state = "reported" if not review_pass else "passed"
        return {
            "action": "pass",
            "state": state,
            "reason": "",
            "display": f"cold-review: report logged (pass={review_pass})",
        }

    # block mode
    if should_block:
        if allow_once:
            reason_suffix = f" [{override_reason}]" if override_reason else ""
            return {
                "action": "pass",
                "state": "overridden",
                "reason": override_reason,
                "display": f"cold-review: override \u2014 block skipped (ALLOW_ONCE){reason_suffix}",
            }
        block_reason = format_block_reason(review, truncated, skipped_count)
        block_reason += (
            "\n\nTo override: COLD_REVIEW_ALLOW_ONCE=1 "
            "COLD_REVIEW_OVERRIDE_REASON='<reason>'"
        )
        return {
            "action": "block",
            "state": "blocked",
            "reason": block_reason,
            "display": f"cold-review: blocking (issues at or above {threshold})",
            "truncated": truncated,
            "skipped_count": skipped_count,
        }

    return {
        "action": "pass",
        "state": "passed",
        "reason": "",
        "display": "cold-review: pass",
        "truncated": truncated,
        "skipped_count": skipped_count,
    }
