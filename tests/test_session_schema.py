"""Tests for cold_eyes.session.schema."""

import pytest
from cold_eyes.session.schema import add_event, create_session, validate_session


class TestCreateSession:
    def test_minimal(self):
        s = create_session("fix auth bug")
        assert s["task_description"] == "fix auth bug"
        assert s["state"] == "created"
        assert len(s["session_id"]) == 12
        assert s["events"] == []
        assert s["contracts"] == []
        assert s["gate_results"] == []

    def test_with_changed_files(self):
        s = create_session("refactor", changed_files=["a.py", "b.py"])
        assert s["changed_files"] == ["a.py", "b.py"]

    def test_empty_description_raises(self):
        with pytest.raises(ValueError, match="task_description"):
            create_session("")

    def test_timestamps_are_set(self):
        s = create_session("test")
        assert "T" in s["created_at"]
        assert "T" in s["updated_at"]


class TestAddEvent:
    def test_appends_event(self):
        s = create_session("test")
        add_event(s, "contract_added", {"contract_id": "abc"})
        assert len(s["events"]) == 1
        assert s["events"][0]["event_type"] == "contract_added"
        assert s["events"][0]["data"] == {"contract_id": "abc"}

    def test_multiple_events(self):
        s = create_session("test")
        add_event(s, "first")
        add_event(s, "second")
        assert len(s["events"]) == 2
        assert s["events"][0]["event_type"] == "first"
        assert s["events"][1]["event_type"] == "second"

    def test_updates_timestamp(self):
        s = create_session("test")
        old_ts = s["updated_at"]
        add_event(s, "ping")
        assert s["updated_at"] >= old_ts

    def test_empty_event_type_raises(self):
        s = create_session("test")
        with pytest.raises(ValueError, match="event_type"):
            add_event(s, "")

    def test_returns_same_session(self):
        s = create_session("test")
        result = add_event(s, "ping")
        assert result is s


class TestValidateSession:
    def test_valid_session(self):
        s = create_session("test")
        ok, errors = validate_session(s)
        assert ok is True
        assert errors == []

    def test_missing_required_fields(self):
        ok, errors = validate_session({"session_id": "abc"})
        assert ok is False
        assert any("task_description" in e for e in errors)

    def test_invalid_state(self):
        s = create_session("test")
        s["state"] = "bogus"
        ok, errors = validate_session(s)
        assert ok is False
        assert any("invalid state" in e for e in errors)

    def test_not_a_dict(self):
        ok, errors = validate_session("oops")
        assert ok is False
        assert errors == ["session is not a dict"]

    def test_list_field_wrong_type(self):
        s = create_session("test")
        s["events"] = "not a list"
        ok, errors = validate_session(s)
        assert ok is False
        assert any("events" in e for e in errors)

    def test_ignores_unknown_fields(self):
        s = create_session("test")
        s["future_field"] = 42
        ok, errors = validate_session(s)
        assert ok is True
