"""Session state machine — enforce valid lifecycle transitions."""

from cold_eyes.type_defs import SESSION_STATES, now_iso

# Allowed transitions: from_state -> set of valid to_states
VALID_TRANSITIONS: dict[str, set[str]] = {
    "created":              {"contract_generated", "aborted"},
    "contract_generated":   {"gates_planned", "aborted"},
    "gates_planned":        {"gates_running", "aborted"},
    "gates_running":        {"passed", "gates_failed", "aborted"},
    "gates_failed":         {"retrying", "failed_terminal", "aborted"},
    "retrying":             {"gates_running", "failed_terminal", "aborted"},
    "passed":               set(),            # terminal
    "failed_terminal":      set(),            # terminal
    "aborted":              set(),            # terminal
}

TERMINAL_STATES = {"passed", "failed_terminal", "aborted"}


def is_terminal(state: str) -> bool:
    """Return True if *state* is a terminal (no further transitions)."""
    return state in TERMINAL_STATES


def transition(session: dict, new_state: str, reason: str = "") -> dict:
    """Move *session* to *new_state* if the transition is valid.

    Mutates and returns the same session dict.
    Raises ``ValueError`` on illegal transitions.
    """
    current = session.get("state", "")
    if current not in VALID_TRANSITIONS:
        raise ValueError(f"unknown current state: {current}")
    if new_state not in SESSION_STATES:
        raise ValueError(f"unknown target state: {new_state}")
    if new_state not in VALID_TRANSITIONS[current]:
        raise ValueError(
            f"illegal transition: {current} -> {new_state} "
            f"(allowed: {sorted(VALID_TRANSITIONS[current])})"
        )

    event = {
        "event_type": "state_change",
        "timestamp": now_iso(),
        "from_state": current,
        "to_state": new_state,
    }
    if reason:
        event["data"] = {"reason": reason}

    session["state"] = new_state
    session["updated_at"] = now_iso()
    session.setdefault("events", []).append(event)
    return session
