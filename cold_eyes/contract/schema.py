"""Contract schema — create and validate CorrectnessContract objects."""

from cold_eyes.type_defs import CorrectnessContract, generate_id

VALID_CHECK_TYPES = {
    "test_pass", "lint_clean", "type_check", "build_ok",
    "llm_review", "custom",
}

VALID_PRIORITIES = {"must", "should", "nice"}

REQUIRED_FIELDS = {"contract_id", "intended_change", "check_type", "priority"}


def create_contract(
    intended_change: str,
    check_type: str = "llm_review",
    priority: str = "must",
    *,
    target_files: list[str] | None = None,
    problem_being_solved: str = "",
    must_not_break: list[str] | None = None,
    validation_plan: str = "",
    likely_failure_modes: list[str] | None = None,
    risk_categories: list[str] | None = None,
    touched_interfaces: list[str] | None = None,
) -> CorrectnessContract:
    """Create a new correctness contract with sensible defaults."""
    if not intended_change:
        raise ValueError("intended_change must not be empty")
    if check_type not in VALID_CHECK_TYPES:
        raise ValueError(f"invalid check_type: {check_type}")
    if priority not in VALID_PRIORITIES:
        raise ValueError(f"invalid priority: {priority}")

    return CorrectnessContract(
        contract_id=generate_id(),
        intended_change=intended_change,
        problem_being_solved=problem_being_solved,
        non_goals=[],
        must_not_break=must_not_break or [],
        assumed_invariants=[],
        touched_interfaces=touched_interfaces or [],
        risk_categories=risk_categories or [],
        risky_surfaces=[],
        validation_plan=validation_plan,
        minimum_tests_to_pass=[],
        new_tests_to_add=[],
        likely_failure_modes=likely_failure_modes or [],
        first_debug_targets=[],
        rollback_guess="",
        check_type=check_type,
        target_files=target_files or [],
        priority=priority,
    )


def validate_contract(contract: dict) -> tuple[bool, list[str]]:
    """Validate a contract dict.

    Returns (ok, errors).  Forward-compatible: ignores unknown fields.
    """
    errors: list[str] = []

    if not isinstance(contract, dict):
        return False, ["contract is not a dict"]

    for field in REQUIRED_FIELDS:
        if field not in contract:
            errors.append(f"missing required field: {field}")

    ct = contract.get("check_type")
    if ct is not None and ct not in VALID_CHECK_TYPES:
        errors.append(f"invalid check_type: {ct}")

    pr = contract.get("priority")
    if pr is not None and pr not in VALID_PRIORITIES:
        errors.append(f"invalid priority: {pr}")

    for list_field in ("non_goals", "must_not_break", "assumed_invariants",
                       "touched_interfaces", "risk_categories", "risky_surfaces",
                       "minimum_tests_to_pass", "new_tests_to_add",
                       "likely_failure_modes", "first_debug_targets",
                       "target_files"):
        val = contract.get(list_field)
        if val is not None and not isinstance(val, list):
            errors.append(f"'{list_field}' must be a list")

    for str_field in ("intended_change", "problem_being_solved",
                      "validation_plan", "rollback_guess"):
        val = contract.get(str_field)
        if val is not None and not isinstance(val, str):
            errors.append(f"'{str_field}' must be a string")

    return len(errors) == 0, errors
