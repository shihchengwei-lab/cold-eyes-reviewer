"""Tests for cold_eyes.contract.schema."""

import pytest
from cold_eyes.contract.schema import create_contract, validate_contract


class TestCreateContract:
    def test_minimal(self):
        c = create_contract("add login endpoint")
        assert c["intended_change"] == "add login endpoint"
        assert c["check_type"] == "llm_review"
        assert c["priority"] == "must"
        assert len(c["contract_id"]) == 12

    def test_with_all_params(self):
        c = create_contract(
            "fix auth bypass",
            check_type="test_pass",
            priority="should",
            target_files=["auth.py"],
            problem_being_solved="CVE-2026-1234",
            must_not_break=["login flow"],
            validation_plan="run auth_test.py",
            likely_failure_modes=["session hijack"],
            risk_categories=["auth_permission"],
            touched_interfaces=["POST /login"],
        )
        assert c["check_type"] == "test_pass"
        assert c["target_files"] == ["auth.py"]
        assert c["must_not_break"] == ["login flow"]
        assert c["risk_categories"] == ["auth_permission"]

    def test_empty_intended_change_raises(self):
        with pytest.raises(ValueError, match="intended_change"):
            create_contract("")

    def test_invalid_check_type_raises(self):
        with pytest.raises(ValueError, match="check_type"):
            create_contract("test", check_type="magic")

    def test_invalid_priority_raises(self):
        with pytest.raises(ValueError, match="priority"):
            create_contract("test", priority="critical")

    def test_defaults_are_empty_lists(self):
        c = create_contract("test")
        assert c["non_goals"] == []
        assert c["must_not_break"] == []
        assert c["target_files"] == []
        assert c["likely_failure_modes"] == []


class TestValidateContract:
    def test_valid_contract(self):
        c = create_contract("test")
        ok, errors = validate_contract(c)
        assert ok is True
        assert errors == []

    def test_missing_required_fields(self):
        ok, errors = validate_contract({"contract_id": "abc"})
        assert ok is False
        assert any("intended_change" in e for e in errors)
        assert any("check_type" in e for e in errors)
        assert any("priority" in e for e in errors)

    def test_invalid_check_type(self):
        c = create_contract("test")
        c["check_type"] = "invalid"
        ok, errors = validate_contract(c)
        assert ok is False
        assert any("check_type" in e for e in errors)

    def test_invalid_priority(self):
        c = create_contract("test")
        c["priority"] = "ultra"
        ok, errors = validate_contract(c)
        assert ok is False
        assert any("priority" in e for e in errors)

    def test_not_a_dict(self):
        ok, errors = validate_contract([])
        assert ok is False
        assert errors == ["contract is not a dict"]

    def test_list_field_wrong_type(self):
        c = create_contract("test")
        c["must_not_break"] = "not a list"
        ok, errors = validate_contract(c)
        assert ok is False
        assert any("must_not_break" in e for e in errors)

    def test_string_field_wrong_type(self):
        c = create_contract("test")
        c["validation_plan"] = 123
        ok, errors = validate_contract(c)
        assert ok is False
        assert any("validation_plan" in e for e in errors)

    def test_ignores_unknown_fields(self):
        c = create_contract("test")
        c["new_v3_field"] = True
        ok, errors = validate_contract(c)
        assert ok is True
