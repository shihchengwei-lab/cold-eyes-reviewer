"""Tests for cold_eyes.session.store."""

import pytest
from cold_eyes.session.schema import create_session, add_event
from cold_eyes.session.store import SessionStore


class TestSessionStore:
    def test_save_and_load(self, tmp_path):
        store = SessionStore(str(tmp_path))
        s = create_session("test save")
        store.save(s)
        loaded = store.load(s["session_id"])
        assert loaded["task_description"] == "test save"
        assert loaded["session_id"] == s["session_id"]

    def test_load_missing_raises(self, tmp_path):
        store = SessionStore(str(tmp_path))
        with pytest.raises(KeyError, match="session not found"):
            store.load("nonexistent")

    def test_list_sessions_newest_first(self, tmp_path):
        store = SessionStore(str(tmp_path))
        s1 = create_session("first")
        s2 = create_session("second")
        store.save(s1)
        store.save(s2)
        sessions = store.list_sessions()
        assert len(sessions) == 2
        assert sessions[0]["task_description"] == "second"
        assert sessions[1]["task_description"] == "first"

    def test_list_sessions_limit(self, tmp_path):
        store = SessionStore(str(tmp_path))
        for i in range(5):
            store.save(create_session(f"task-{i}"))
        sessions = store.list_sessions(last_n=2)
        assert len(sessions) == 2
        assert sessions[0]["task_description"] == "task-4"

    def test_list_sessions_empty(self, tmp_path):
        store = SessionStore(str(tmp_path))
        assert store.list_sessions() == []

    def test_save_overwrites_existing(self, tmp_path):
        store = SessionStore(str(tmp_path))
        s = create_session("original")
        store.save(s)
        s["task_description"] = "updated"
        store.save(s)
        loaded = store.load(s["session_id"])
        assert loaded["task_description"] == "updated"
        assert len(store.list_sessions()) == 1

    def test_update_existing(self, tmp_path):
        store = SessionStore(str(tmp_path))
        s = create_session("test update")
        store.save(s)
        add_event(s, "ping")
        store.update(s)
        loaded = store.load(s["session_id"])
        assert len(loaded["events"]) == 1

    def test_update_missing_raises(self, tmp_path):
        store = SessionStore(str(tmp_path))
        s = create_session("ghost")
        with pytest.raises(KeyError, match="session not found"):
            store.update(s)

    def test_save_invalid_raises(self, tmp_path):
        store = SessionStore(str(tmp_path))
        with pytest.raises(ValueError, match="invalid session"):
            store.save({"bad": True})

    def test_multiple_sessions_coexist(self, tmp_path):
        store = SessionStore(str(tmp_path))
        s1 = create_session("alpha")
        s2 = create_session("beta")
        store.save(s1)
        store.save(s2)
        assert store.load(s1["session_id"])["task_description"] == "alpha"
        assert store.load(s2["session_id"])["task_description"] == "beta"
