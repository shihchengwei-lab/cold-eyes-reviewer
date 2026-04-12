"""Tests for cold_eyes.retry.brief."""

import pytest
from cold_eyes.retry.brief import create_brief, validate_brief


class TestCreateBrief:
    def test_minimal(self):
        b = create_brief("2 tests failed", "patch_localized_bug")
        assert b["failure_summary"] == "2 tests failed"
        assert b["retry_strategy"] == "patch_localized_bug"
        assert b["confidence"] == "medium"
        assert b["retry_count"] == 1

    def test_with_all_params(self):
        b = create_brief(
            "auth gate failed",
            "restore_broken_contract",
            confidence="high",
            retry_count=2,
            failed_gates=["llm_review"],
            files_to_reinspect=["auth.py"],
            must_preserve_constraints=["login flow"],
            stop_if_repeated=True,
        )
        assert b["failed_gates"] == ["llm_review"]
        assert b["stop_if_repeated"] is True

    def test_empty_summary_raises(self):
        with pytest.raises(ValueError, match="failure_summary"):
            create_brief("", "patch_localized_bug")

    def test_invalid_strategy_raises(self):
        with pytest.raises(ValueError, match="retry_strategy"):
            create_brief("test", "magic_fix")

    def test_invalid_confidence_raises(self):
        with pytest.raises(ValueError, match="confidence"):
            create_brief("test", "patch_localized_bug", confidence="ultra")


class TestValidateBrief:
    def test_valid(self):
        b = create_brief("test", "patch_localized_bug")
        ok, errors = validate_brief(b)
        assert ok is True

    def test_missing_fields(self):
        ok, errors = validate_brief({"retry_id": "abc"})
        assert ok is False
        assert any("failure_summary" in e for e in errors)

    def test_invalid_strategy(self):
        b = create_brief("test", "patch_localized_bug")
        b["retry_strategy"] = "invalid"
        ok, errors = validate_brief(b)
        assert ok is False

    def test_not_a_dict(self):
        ok, errors = validate_brief("nope")
        assert ok is False

    def test_list_field_wrong_type(self):
        b = create_brief("test", "patch_localized_bug")
        b["failed_gates"] = "not a list"
        ok, errors = validate_brief(b)
        assert ok is False
