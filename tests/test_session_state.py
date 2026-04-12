"""Tests for cold_eyes.session.state_machine."""

import pytest
from cold_eyes.session.schema import create_session
from cold_eyes.session.state_machine import (
    TERMINAL_STATES,
    VALID_TRANSITIONS,
    is_terminal,
    transition,
)


class TestValidTransitions:
    def test_all_states_have_entries(self):
        from cold_eyes.type_defs import SESSION_STATES
        for state in SESSION_STATES:
            assert state in VALID_TRANSITIONS, f"missing transition entry for {state}"

    def test_terminal_states_have_no_outgoing(self):
        for state in TERMINAL_STATES:
            assert VALID_TRANSITIONS[state] == set()


class TestIsTerminal:
    def test_passed_is_terminal(self):
        assert is_terminal("passed") is True

    def test_failed_terminal_is_terminal(self):
        assert is_terminal("failed_terminal") is True

    def test_aborted_is_terminal(self):
        assert is_terminal("aborted") is True

    def test_created_is_not_terminal(self):
        assert is_terminal("created") is False

    def test_retrying_is_not_terminal(self):
        assert is_terminal("retrying") is False


class TestTransition:
    def test_created_to_contract_generated(self):
        s = create_session("test")
        transition(s, "contract_generated")
        assert s["state"] == "contract_generated"
        assert len(s["events"]) == 1
        assert s["events"][0]["from_state"] == "created"
        assert s["events"][0]["to_state"] == "contract_generated"

    def test_full_happy_path(self):
        s = create_session("test")
        for state in ["contract_generated", "gates_planned", "gates_running", "passed"]:
            transition(s, state)
        assert s["state"] == "passed"
        assert len(s["events"]) == 4

    def test_retry_loop(self):
        s = create_session("test")
        transition(s, "contract_generated")
        transition(s, "gates_planned")
        transition(s, "gates_running")
        transition(s, "gates_failed")
        transition(s, "retrying")
        transition(s, "gates_running")
        transition(s, "passed")
        assert s["state"] == "passed"

    def test_illegal_skip_to_passed(self):
        s = create_session("test")
        with pytest.raises(ValueError, match="illegal transition"):
            transition(s, "passed")

    def test_no_transition_from_passed(self):
        s = create_session("test")
        for state in ["contract_generated", "gates_planned", "gates_running", "passed"]:
            transition(s, state)
        with pytest.raises(ValueError, match="illegal transition"):
            transition(s, "retrying")

    def test_abort_from_any_non_terminal(self):
        for start_state in ["created", "contract_generated", "gates_planned",
                            "gates_running", "gates_failed", "retrying"]:
            s = create_session("test")
            s["state"] = start_state
            transition(s, "aborted", reason="user cancelled")
            assert s["state"] == "aborted"

    def test_unknown_current_state_raises(self):
        s = create_session("test")
        s["state"] = "nonsense"
        with pytest.raises(ValueError, match="unknown current state"):
            transition(s, "passed")

    def test_unknown_target_state_raises(self):
        s = create_session("test")
        with pytest.raises(ValueError, match="unknown target state"):
            transition(s, "flying")

    def test_reason_stored_in_event(self):
        s = create_session("test")
        transition(s, "aborted", reason="timeout")
        assert s["events"][0]["data"]["reason"] == "timeout"

    def test_updates_timestamp(self):
        s = create_session("test")
        old_ts = s["updated_at"]
        transition(s, "contract_generated")
        assert s["updated_at"] >= old_ts
