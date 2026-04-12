"""Retry brief schema — structured instructions for the next retry."""

from cold_eyes.type_defs import RetryBrief, generate_id


REQUIRED_FIELDS = {"retry_id", "failure_summary", "retry_strategy", "confidence", "retry_count"}

VALID_STRATEGIES = {
    "patch_localized_bug",
    "restore_broken_contract",
    "reintroduce_missing_guard",
    "repair_test_and_code_mismatch",
    "add_missing_validation",
    "reduce_scope_and_retry",
    "generate_targeted_test_then_fix",
    "abort_and_escalate",
}

VALID_CONFIDENCES = {"high", "medium", "low"}


def create_brief(
    failure_summary: str,
    retry_strategy: str,
    confidence: str = "medium",
    retry_count: int = 1,
    *,
    failed_gates: list[str] | None = None,
    probable_failure_types: list[str] | None = None,
    most_likely_root_causes: list[str] | None = None,
    minimal_fix_scope: list[str] | None = None,
    files_to_reinspect: list[str] | None = None,
    must_preserve_constraints: list[str] | None = None,
    tests_to_run_after_fix: list[str] | None = None,
    tests_to_add_or_adjust: list[str] | None = None,
    do_not_repeat: list[str] | None = None,
    stop_if_repeated: bool = False,
) -> RetryBrief:
    """Create a structured retry brief."""
    if not failure_summary:
        raise ValueError("failure_summary must not be empty")
    if retry_strategy not in VALID_STRATEGIES:
        raise ValueError(f"invalid retry_strategy: {retry_strategy}")
    if confidence not in VALID_CONFIDENCES:
        raise ValueError(f"invalid confidence: {confidence}")

    return RetryBrief(
        retry_id=generate_id(),
        failure_summary=failure_summary,
        failed_gates=failed_gates or [],
        probable_failure_types=probable_failure_types or [],
        most_likely_root_causes=most_likely_root_causes or [],
        minimal_fix_scope=minimal_fix_scope or [],
        files_to_reinspect=files_to_reinspect or [],
        must_preserve_constraints=must_preserve_constraints or [],
        tests_to_run_after_fix=tests_to_run_after_fix or [],
        tests_to_add_or_adjust=tests_to_add_or_adjust or [],
        do_not_repeat=do_not_repeat or [],
        retry_strategy=retry_strategy,
        confidence=confidence,
        stop_if_repeated=stop_if_repeated,
        retry_count=retry_count,
    )


def validate_brief(brief: dict) -> tuple[bool, list[str]]:
    """Validate a retry brief dict. Returns (ok, errors)."""
    errors: list[str] = []

    if not isinstance(brief, dict):
        return False, ["brief is not a dict"]

    for field in REQUIRED_FIELDS:
        if field not in brief:
            errors.append(f"missing required field: {field}")

    strategy = brief.get("retry_strategy")
    if strategy is not None and strategy not in VALID_STRATEGIES:
        errors.append(f"invalid retry_strategy: {strategy}")

    conf = brief.get("confidence")
    if conf is not None and conf not in VALID_CONFIDENCES:
        errors.append(f"invalid confidence: {conf}")

    for list_field in ("failed_gates", "probable_failure_types",
                       "most_likely_root_causes", "minimal_fix_scope",
                       "files_to_reinspect", "must_preserve_constraints",
                       "tests_to_run_after_fix", "tests_to_add_or_adjust",
                       "do_not_repeat"):
        val = brief.get(list_field)
        if val is not None and not isinstance(val, list):
            errors.append(f"'{list_field}' must be a list")

    return len(errors) == 0, errors
