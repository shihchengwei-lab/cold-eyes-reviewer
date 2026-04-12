"""Failure-to-retry translator — combine signals into a retry brief."""

from cold_eyes.retry.brief import create_brief
from cold_eyes.retry.signal_parser import extract_signals
from cold_eyes.retry.taxonomy import classify_failure


def translate(
    gate_results: list[dict],
    contracts: list[dict] | None = None,
    retry_count: int = 1,
) -> dict:
    """Translate failed gate results into a structured retry brief.

    Combines failure taxonomy, signal extraction, and contract context
    to produce an actionable brief for the next attempt.
    """
    contracts = contracts or []
    failed_gates: list[str] = []
    failure_types: list[str] = []
    root_causes: list[str] = []
    files_to_inspect: list[str] = []
    signals: list[str] = []
    must_preserve: list[str] = []
    tests_to_run: list[str] = []

    for gr in gate_results:
        if gr.get("status") != "fail":
            continue

        gate_name = gr.get("gate_name", "unknown")
        failed_gates.append(gate_name)

        # Classify failure
        ft = classify_failure(gr)
        category = ft.get("category", "unknown")
        if category not in failure_types:
            failure_types.append(category)
        if ft.get("typical_fix"):
            root_causes.append(ft["typical_fix"])

        # Extract signals
        sigs = extract_signals(gr)
        signals.extend(sigs)

        # Collect files from findings
        for f in gr.get("findings", []):
            file_ = f.get("file", "") or f.get("location", "")
            if file_ and file_ not in files_to_inspect:
                files_to_inspect.append(file_)

    # Contract context: must_not_break -> must_preserve
    for c in contracts:
        for constraint in c.get("must_not_break", []):
            if constraint not in must_preserve:
                must_preserve.append(constraint)
        for test in c.get("minimum_tests_to_pass", []):
            if test not in tests_to_run:
                tests_to_run.append(test)

    # Build summary
    summary_parts = []
    if failed_gates:
        summary_parts.append(f"{len(failed_gates)} gate(s) failed: {', '.join(failed_gates)}")
    if failure_types:
        summary_parts.append(f"types: {', '.join(failure_types)}")
    failure_summary = "; ".join(summary_parts) or "unknown failure"

    # Choose strategy based on dominant failure type
    strategy = _pick_strategy(failure_types, retry_count)

    # Confidence based on signal quality
    confidence = _assess_confidence(signals, failure_types)

    return create_brief(
        failure_summary=failure_summary,
        retry_strategy=strategy,
        confidence=confidence,
        retry_count=retry_count,
        failed_gates=failed_gates,
        probable_failure_types=failure_types,
        most_likely_root_causes=root_causes,
        minimal_fix_scope=files_to_inspect[:5],
        files_to_reinspect=files_to_inspect[:10],
        must_preserve_constraints=must_preserve,
        tests_to_run_after_fix=tests_to_run,
        stop_if_repeated=retry_count >= 2,
    )


def _pick_strategy(failure_types: list[str], retry_count: int) -> str:
    """Select retry strategy from failure types."""
    if retry_count >= 3:
        return "abort_and_escalate"

    _TYPE_TO_STRATEGY = {
        "test_regression": "repair_test_and_code_mismatch",
        "missing_import_or_dependency": "patch_localized_bug",
        "build_or_install_failure": "patch_localized_bug",
        "syntax_or_parse_failure": "patch_localized_bug",
        "contract_break": "restore_broken_contract",
        "state_invariant_suspicion": "restore_broken_contract",
        "schema_or_migration_risk": "reduce_scope_and_retry",
        "insufficient_validation": "add_missing_validation",
        "low_confidence_suspicion": "generate_targeted_test_then_fix",
    }

    for ft in failure_types:
        if ft in _TYPE_TO_STRATEGY:
            return _TYPE_TO_STRATEGY[ft]

    return "patch_localized_bug"


def _assess_confidence(signals: list[str], failure_types: list[str]) -> str:
    """Rough confidence based on signal clarity."""
    if not signals:
        return "low"
    if len(signals) >= 3 and len(failure_types) == 1:
        return "high"
    return "medium"
