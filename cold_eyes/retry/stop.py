"""Stop condition engine — prevent infinite retry loops."""


def should_stop(
    session: dict,
    max_retries: int = 3,
) -> tuple[bool, str]:
    """Evaluate whether the session should stop retrying.

    Returns (should_stop: bool, reason: str).
    """
    briefs = session.get("retry_briefs", [])
    gate_results = session.get("gate_results", [])

    # --- Hard limit ---
    if len(briefs) > max_retries:
        return True, f"max retries reached ({max_retries})"

    if len(briefs) < 2:
        return False, ""

    # --- Same failure repeated ---
    last_types = briefs[-1].get("probable_failure_types", [])
    prev_types = briefs[-2].get("probable_failure_types", [])
    if last_types and last_types == prev_types:
        # Check if same strategy too
        if briefs[-1].get("retry_strategy") == briefs[-2].get("retry_strategy"):
            return True, "same failure type and strategy repeated consecutively"

    # --- No progress: findings count not decreasing ---
    # gate_results is flat; use gate_plan length as stride to compare whole iterations
    num_gates = len(session.get("gate_plan", []))
    if num_gates > 0 and len(gate_results) >= 2 * num_gates:
        recent = gate_results[-num_gates:]
        earlier = gate_results[-2 * num_gates:-num_gates]
        recent_count = sum(len(gr.get("findings", [])) for gr in recent)
        earlier_count = sum(len(gr.get("findings", [])) for gr in earlier)
        if recent_count >= earlier_count and earlier_count > 0:
            return True, "no progress: finding count not decreasing"

    # --- All contracts satisfied (early success) ---
    if _all_gates_passing(gate_results):
        return True, "all gates passing — no retry needed"

    # --- Fix scope expanding ---
    if len(briefs) >= 2:
        last_scope = len(briefs[-1].get("minimal_fix_scope", []))
        prev_scope = len(briefs[-2].get("minimal_fix_scope", []))
        if last_scope > prev_scope * 2 and last_scope > 5:
            return True, "fix scope expanding rapidly"

    return False, ""


def _all_gates_passing(gate_results: list[dict]) -> bool:
    """Check if the most recent result for each gate is passing."""
    if not gate_results:
        return False
    latest: dict[str, str] = {}
    for gr in gate_results:
        latest[gr.get("gate_name", "")] = gr.get("status", "")
    return all(s == "pass" for s in latest.values())
