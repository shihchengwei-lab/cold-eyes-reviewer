"""Contract quality checker — detect empty, vague, or incomplete contracts."""

from cold_eyes.contract.schema import validate_contract

# Minimum thresholds for a "good" contract
_MIN_MUST_NOT_BREAK = 1
_MIN_LIKELY_FAILURE_MODES = 1


def check_quality(
    contracts: list[dict],
    changed_files: list[str] | None = None,
) -> dict:
    """Assess the quality of a set of contracts.

    Returns a dict with:
        quality_score     (float 0.0-1.0)
        quality_warnings  (list[str])
        should_escalate_to_deep_path (bool)
        coverage          (dict — files_covered / total)
    """
    warnings: list[str] = []
    changed_files = changed_files or []
    total_checks = 0
    passed_checks = 0

    if not contracts:
        return {
            "quality_score": 0.0,
            "quality_warnings": ["no contracts generated"],
            "should_escalate_to_deep_path": True,
            "coverage": {"covered": 0, "total": len(changed_files)},
        }

    # --- Per-contract checks ---
    for i, c in enumerate(contracts):
        ok, errors = validate_contract(c)
        if not ok:
            warnings.append(f"contract[{i}] invalid: {errors}")
            continue

        total_checks += 1
        score = 0

        # intended_change not too vague (>10 chars)
        ic = c.get("intended_change", "")
        if len(ic) > 10:
            score += 1
        else:
            warnings.append(f"contract[{i}] intended_change too vague")

        # must_not_break populated
        total_checks += 1
        mnb = c.get("must_not_break", [])
        if len(mnb) >= _MIN_MUST_NOT_BREAK:
            score += 1
        else:
            warnings.append(f"contract[{i}] must_not_break is empty")

        # validation_plan not empty
        total_checks += 1
        vp = c.get("validation_plan", "")
        if vp:
            score += 1
        else:
            warnings.append(f"contract[{i}] validation_plan is empty")

        # likely_failure_modes populated
        total_checks += 1
        lfm = c.get("likely_failure_modes", [])
        if len(lfm) >= _MIN_LIKELY_FAILURE_MODES:
            score += 1
        else:
            warnings.append(f"contract[{i}] likely_failure_modes is empty")

        # touched_interfaces populated (for must-priority)
        if c.get("priority") == "must":
            total_checks += 1
            ti = c.get("touched_interfaces", [])
            if ti:
                score += 1
            else:
                warnings.append(f"contract[{i}] touched_interfaces is empty for must-priority contract")

        passed_checks += score

    # --- Coverage check ---
    covered_files: set[str] = set()
    for c in contracts:
        for f in c.get("target_files", []):
            covered_files.add(f)
    uncovered = [f for f in changed_files if f not in covered_files]
    if uncovered:
        warnings.append(f"files not covered by any contract: {uncovered}")

    quality_score = passed_checks / total_checks if total_checks > 0 else 0.0
    should_escalate = quality_score < 0.4 or len(warnings) > len(contracts) * 2

    return {
        "quality_score": round(quality_score, 2),
        "quality_warnings": warnings,
        "should_escalate_to_deep_path": should_escalate,
        "coverage": {
            "covered": len(covered_files),
            "total": len(changed_files),
        },
    }
