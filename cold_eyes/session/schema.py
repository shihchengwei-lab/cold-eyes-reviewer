"""Session schema — create and validate SessionRecord objects."""

from cold_eyes.type_defs import (
    SESSION_STATES,
    SessionEvent,
    SessionRecord,
    generate_id,
    now_iso,
)

REQUIRED_FIELDS = {"session_id", "task_description", "state", "created_at", "updated_at"}


def create_session(task_description: str, changed_files: list[str] | None = None) -> SessionRecord:
    """Create a new session in the 'created' state."""
    if not task_description:
        raise ValueError("task_description must not be empty")
    ts = now_iso()
    return SessionRecord(
        session_id=generate_id(),
        task_description=task_description,
        state="created",
        created_at=ts,
        updated_at=ts,
        changed_files=changed_files or [],
        change_summary="",
        events=[],
        contracts=[],
        gate_plan=[],
        gate_results=[],
        retry_briefs=[],
        final_outcome={},
        learning_signals={},
    )


def add_event(session: SessionRecord, event_type: str, data: dict | None = None) -> SessionRecord:
    """Append an event to the session and update the timestamp.

    Returns the mutated session (same object).
    """
    if not event_type:
        raise ValueError("event_type must not be empty")
    event = SessionEvent(
        event_type=event_type,
        timestamp=now_iso(),
        data=data or {},
    )
    session["events"].append(event)
    session["updated_at"] = now_iso()
    return session


def validate_session(record: dict) -> tuple[bool, list[str]]:
    """Validate a session dict.

    Returns (ok, errors).  Forward-compatible: ignores unknown fields.
    """
    errors: list[str] = []

    if not isinstance(record, dict):
        return False, ["session is not a dict"]

    for field in REQUIRED_FIELDS:
        if field not in record:
            errors.append(f"missing required field: {field}")

    state = record.get("state")
    if state is not None and state not in SESSION_STATES:
        errors.append(f"invalid state: {state}")

    for list_field in ("events", "contracts", "gate_results", "retry_briefs",
                       "changed_files", "gate_plan"):
        val = record.get(list_field)
        if val is not None and not isinstance(val, list):
            errors.append(f"'{list_field}' must be a list")

    return len(errors) == 0, errors
