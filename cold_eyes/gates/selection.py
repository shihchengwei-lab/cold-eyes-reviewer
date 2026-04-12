"""Gate selection rules — choose which gates to run for a session."""

from cold_eyes.gates.catalog import get_gate


def select_gates(
    risk_level: str,
    contracts: list[dict],
    available_gate_ids: list[str],
) -> list[dict]:
    """Select gates based on risk level and contracts.

    Returns a list of dicts, each with:
        gate_id    (str)
        reason     (str — why this gate was selected)
        blocking   (str — "hard" | "soft")
    """
    if not available_gate_ids:
        return []

    selected: list[dict] = []
    seen: set[str] = set()

    # --- Contract-driven selection ---
    _CHECK_TO_GATE = {
        "test_pass": "test_runner",
        "lint_clean": "lint_checker",
        "type_check": "type_checker",
        "build_ok": "build_checker",
        "llm_review": "llm_review",
    }

    for c in contracts:
        ct = c.get("check_type", "")
        gate_id = _CHECK_TO_GATE.get(ct)
        if gate_id and gate_id in available_gate_ids and gate_id not in seen:
            priority = c.get("priority", "should")
            blocking = "hard" if priority == "must" else "soft"
            selected.append({
                "gate_id": gate_id,
                "reason": f"contract requires {ct} (priority={priority})",
                "blocking": blocking,
            })
            seen.add(gate_id)

    # --- Risk-level escalation ---
    if risk_level in ("high", "critical"):
        # Add all available gates not yet selected
        for gid in available_gate_ids:
            if gid not in seen:
                gate = get_gate(gid)
                selected.append({
                    "gate_id": gid,
                    "reason": f"risk level {risk_level} triggers all available gates",
                    "blocking": gate.get("blocking_mode", "soft"),
                })
                seen.add(gid)

    # --- Minimum gate guarantee ---
    if not selected and "llm_review" in available_gate_ids:
        selected.append({
            "gate_id": "llm_review",
            "reason": "fallback: at least one gate must run",
            "blocking": "soft",
        })

    return selected


def build_gate_plan(
    risk_level: str,
    contracts: list[dict],
    available_gate_ids: list[str],
) -> dict:
    """Build a complete gate plan with selection reasoning.

    Returns dict with:
        selected_gates  (list[dict])
        skipped_gates   (list[dict] — gates not selected and why)
        risk_level      (str)
    """
    selected = select_gates(risk_level, contracts, available_gate_ids)
    selected_ids = {g["gate_id"] for g in selected}

    skipped = []
    for gid in available_gate_ids:
        if gid not in selected_ids:
            skipped.append({
                "gate_id": gid,
                "reason": "not required by contracts or risk level",
            })

    return {
        "selected_gates": selected,
        "skipped_gates": skipped,
        "risk_level": risk_level,
    }
