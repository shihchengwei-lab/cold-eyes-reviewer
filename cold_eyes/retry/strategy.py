"""Retry strategy selector — choose fix approach from failure patterns."""

def select_strategy(
    retry_brief: dict,
    previous_briefs: list[dict] | None = None,
) -> dict:
    """Refine or override the retry strategy in a brief.

    Returns dict with:
        action         ("retry" | "escalate" | "abort")
        strategy       (str — from VALID_STRATEGIES)
        modifications  (list[str] — suggested changes to approach)
        re_run_gates   (list[str] — gates to re-run after fix)
    """
    previous_briefs = previous_briefs or []
    strategy = retry_brief.get("retry_strategy", "patch_localized_bug")
    retry_count = retry_brief.get("retry_count", 1)
    failed_gates = retry_brief.get("failed_gates", [])

    # --- Escalation / abort conditions ---
    if strategy == "abort_and_escalate" or retry_count >= 3:
        return {
            "action": "abort",
            "strategy": "abort_and_escalate",
            "modifications": ["max retries exceeded or strategy is abort"],
            "re_run_gates": [],
        }

    # Check for repeated identical strategy
    if previous_briefs:
        prev_strategies = [b.get("retry_strategy") for b in previous_briefs]
        consecutive_same = 0
        for ps in reversed(prev_strategies):
            if ps == strategy:
                consecutive_same += 1
            else:
                break
        if consecutive_same >= 2:
            return {
                "action": "escalate",
                "strategy": "reduce_scope_and_retry",
                "modifications": [
                    f"strategy '{strategy}' repeated {consecutive_same} times without progress",
                    "reducing scope or escalating",
                ],
                "re_run_gates": failed_gates,
            }

    # --- Modifications based on strategy ---
    modifications: list[str] = []
    if strategy == "repair_test_and_code_mismatch":
        modifications.append("focus on aligning test expectations with new code behavior")
    elif strategy == "restore_broken_contract":
        modifications.append("identify which contract invariant was broken and restore it")
    elif strategy == "add_missing_validation":
        modifications.append("add the missing check rather than modifying existing logic")
    elif strategy == "reduce_scope_and_retry":
        modifications.append("split the change into smaller pieces and retry each")
    elif strategy == "generate_targeted_test_then_fix":
        modifications.append("write a test that reproduces the issue first, then fix")

    return {
        "action": "retry",
        "strategy": strategy,
        "modifications": modifications,
        "re_run_gates": failed_gates,
    }
