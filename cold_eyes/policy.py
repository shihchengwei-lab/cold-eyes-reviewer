"""Policy enforcement: confidence filter, block decision, formatting."""

from cold_eyes.constants import (
    SEVERITY_ORDER, CONFIDENCE_ORDER,
    STATE_PASSED, STATE_BLOCKED, STATE_OVERRIDDEN, STATE_INFRA_FAILED, STATE_REPORTED,
)
try:
    from cold_eyes.memory import match_fp_pattern, compute_category_baselines
except ImportError:
    match_fp_pattern = None
    compute_category_baselines = None


_CONFIDENCE_DOWNGRADE = {"high": "medium", "medium": "low", "low": "low"}


def calibrate_evidence(issues, fp_patterns=None):
    """Adjust confidence based on evidence, abstain conditions, and FP memory.

    Rules applied in order per issue:
    1. confidence=high with empty evidence → medium
    2. has non-empty abstain_condition → confidence -1 level
    3. matches known FP pattern → confidence -1 per match type (max -2)
    4. category confidence cap — if category has high override ratio, cap confidence
    Returns new list (shallow copies).
    """
    category_caps = (compute_category_baselines(fp_patterns)
                     if fp_patterns and compute_category_baselines else {})

    calibrated = []
    for issue in issues:
        issue = dict(issue)
        evidence = issue.get("evidence", [])
        # Rule 1: high confidence without evidence → medium
        if issue.get("confidence") == "high" and not evidence:
            issue["confidence"] = "medium"
        # Rule 2: has abstain_condition → -1 level
        if issue.get("abstain_condition"):
            issue["confidence"] = _CONFIDENCE_DOWNGRADE.get(
                issue["confidence"], issue["confidence"])
        # Rule 3: matches known FP pattern → -1 per match (max 2 downgrades)
        if fp_patterns and match_fp_pattern:
            match_count, _ = match_fp_pattern(issue, fp_patterns)
            downgrades = min(match_count, 2)
            for _ in range(downgrades):
                issue["confidence"] = _CONFIDENCE_DOWNGRADE.get(
                    issue["confidence"], issue["confidence"])
            if match_count > 0:
                issue["fp_match_count"] = match_count
        # Rule 4: category confidence cap
        cat = issue.get("category", "")
        if cat and cat in category_caps:
            cap = category_caps[cat]
            cap_level = CONFIDENCE_ORDER.get(cap, 2)
            cur_level = CONFIDENCE_ORDER.get(issue["confidence"], 2)
            if cur_level > cap_level:
                issue["confidence"] = cap
        calibrated.append(issue)
    return calibrated


def filter_by_confidence(issues, min_confidence="medium"):
    """Remove issues below the confidence threshold. Deterministic hard filter."""
    threshold = CONFIDENCE_ORDER.get(min_confidence, 2)
    return [i for i in issues if CONFIDENCE_ORDER.get(i.get("confidence", "medium"), 2) >= threshold]


def _is_chinese(language):
    """True if language string looks like it requests Chinese output."""
    if not language:
        return True  # default is Chinese
    low = language.lower()
    return any(k in low for k in ("中文", "chinese", "zh", "繁體", "簡體"))


def format_block_reason(review, truncated=False, skipped_count=0, language=None):
    """Format review into human-readable block reason."""
    use_zh = _is_chinese(language)
    if use_zh:
        check_l, verdict_l, fix_l = "\u6aa2\u67e5", "\u5224\u6c7a", "\u6307\u793a"
        trunc_msg = (
            f"\u26a0 \u5be9\u67e5\u4e0d\u5b8c\u6574\uff1adiff \u8d85\u904e token \u9810\u7b97\uff0c"
            f"{skipped_count} \u500b\u6a94\u6848\u672a\u5be9\u67e5\u3002"
        )
    else:
        check_l, verdict_l, fix_l = "Check", "Verdict", "Fix"
        trunc_msg = f"\u26a0 Incomplete review: diff exceeded token budget, {skipped_count} files not reviewed."

    summary = review.get("summary", "")
    issues = review.get("issues", [])
    lines = [f"Cold Eyes Review \u2014 {summary}"]
    for issue in issues:
        sev = issue.get("severity", "major").upper()
        file_name = issue.get("file", "")
        line_hint = issue.get("line_hint", "")
        check = issue.get("check", "")
        verdict = issue.get("verdict", "")
        fix = issue.get("fix", "")
        file_part = f" {file_name}" if file_name and file_name != "unknown" else ""
        hint_part = f" (~{line_hint})" if line_hint else ""
        lines.append(f"  - [{sev}]{file_part}{hint_part} {check_l}\uff1a{check}" if use_zh
                     else f"  - [{sev}]{file_part}{hint_part} {check_l}: {check}")
        lines.append(f"    {verdict_l}\uff1a{verdict}" if use_zh
                     else f"    {verdict_l}: {verdict}")
        lines.append(f"    {fix_l}\uff1a{fix}" if use_zh
                     else f"    {fix_l}: {fix}")
    if truncated:
        lines.append(f"  {trunc_msg}")
    return "\n".join(lines)


def apply_policy(review, mode, threshold, allow_once, min_confidence="medium",
                 truncated=False, skipped_files=None, override_reason="",
                 language=None, truncation_policy="warn", fp_patterns=None):
    """Determine final outcome. Return FinalOutcome dict.

    FinalOutcome keys: action, state, reason, display, truncated, skipped_count
    The review in the outcome has issues filtered by confidence.
    fp_patterns: FP memory patterns from extract_fp_patterns() (optional).
    """
    if skipped_files is None:
        skipped_files = []
    skipped_count = len(skipped_files)
    engine_ok = review.get("review_status") != "failed"

    override_instruction = "To override: python cli.py arm-override --reason '<reason>'"

    # --- Infrastructure failure ---
    if not engine_ok:
        error_detail = review.get("summary", "unknown error")
        if mode == "block":
            if allow_once:
                reason_suffix = f" [{override_reason}]" if override_reason else ""
                return {
                    "action": "pass",
                    "state": STATE_OVERRIDDEN,
                    "reason": override_reason,
                    "display": f"cold-review: override \u2014 infra failure bypass{reason_suffix}",
                }
            return {
                "action": "block",
                "state": STATE_INFRA_FAILED,
                "reason": (
                    f"Cold Eyes Review \u2014 infrastructure failure: {error_detail}.\n"
                    f"{override_instruction}"
                ),
                "display": "cold-review: blocking (infrastructure failure)",
            }
        # report mode — log but pass; state is infra_failed (consistent)
        return {
            "action": "pass",
            "state": STATE_INFRA_FAILED,
            "reason": error_detail,
            "display": f"cold-review: report logged (infra failure: {error_detail})",
        }

    # --- Evidence calibration (before confidence filter) ---
    calibrated_issues = calibrate_evidence(review.get("issues", []), fp_patterns=fp_patterns)

    # --- Confidence filter (hard gate) ---
    filtered_issues = filter_by_confidence(calibrated_issues, min_confidence)
    review = {**review, "issues": filtered_issues}

    # --- Review completed ---
    threshold_level = SEVERITY_ORDER.get(threshold, 0)
    max_severity = 0
    for issue in filtered_issues:
        level = SEVERITY_ORDER.get(issue.get("severity", "major"), 2)
        max_severity = max(max_severity, level)

    should_block = max_severity >= threshold_level
    effective_pass = len(filtered_issues) == 0

    # --- Truncation policy (block mode only) ---
    # fail-closed is NEVER bypassed by override — check it unconditionally
    if truncated and mode == "block" and truncation_policy == "fail-closed":
        block_reason = format_block_reason(review, truncated, skipped_count, language)
        block_reason += f"\n\n{override_instruction}"
        return {
            "action": "block",
            "state": STATE_BLOCKED,
            "reason": block_reason,
            "display": f"cold-review: blocking (truncation policy: fail-closed, {skipped_count} files unreviewed)",
            "truncated": True,
            "skipped_count": skipped_count,
        }
    if truncated and mode == "block" and not allow_once:
        if truncation_policy == "soft-pass" and effective_pass:
            return {
                "action": "pass",
                "state": STATE_PASSED,
                "reason": f"truncated ({skipped_count} files unreviewed), no issues in reviewed portion",
                "display": f"cold-review: soft-pass (truncated, {skipped_count} files unreviewed)",
                "truncated": True,
                "skipped_count": skipped_count,
            }
        # "warn" — fall through to existing logic

    if mode == "report":
        state = STATE_REPORTED if not effective_pass else STATE_PASSED
        return {
            "action": "pass",
            "state": state,
            "reason": "",
            "display": f"cold-review: report logged (pass={effective_pass})",
        }

    # block mode
    if should_block:
        if allow_once:
            reason_suffix = f" [{override_reason}]" if override_reason else ""
            return {
                "action": "pass",
                "state": STATE_OVERRIDDEN,
                "reason": override_reason,
                "display": f"cold-review: override \u2014 block skipped{reason_suffix}",
            }
        block_reason = format_block_reason(review, truncated, skipped_count, language)
        block_reason += f"\n\n{override_instruction}"
        return {
            "action": "block",
            "state": STATE_BLOCKED,
            "reason": block_reason,
            "display": f"cold-review: blocking (issues at or above {threshold})",
            "truncated": truncated,
            "skipped_count": skipped_count,
        }

    return {
        "action": "pass",
        "state": STATE_PASSED,
        "reason": "",
        "display": "cold-review: pass",
        "truncated": truncated,
        "skipped_count": skipped_count,
    }
