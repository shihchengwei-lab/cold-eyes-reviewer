"""Tests for cold_eyes.contract.quality_checker."""

from cold_eyes.contract.schema import create_contract
from cold_eyes.contract.quality_checker import check_quality


def _good_contract(**overrides):
    """Create a well-populated contract for testing."""
    defaults = dict(
        intended_change="add user authentication endpoint",
        check_type="llm_review",
        priority="must",
        must_not_break=["existing login flow"],
        validation_plan="run auth_test.py suite",
        likely_failure_modes=["session hijack"],
        touched_interfaces=["POST /auth/login"],
    )
    defaults.update(overrides)
    return create_contract(**defaults)


def _bare_contract():
    """Create a minimal (low quality) contract."""
    return create_contract("fix")


class TestCheckQuality:
    def test_no_contracts_scores_zero(self):
        result = check_quality([], changed_files=["a.py"])
        assert result["quality_score"] == 0.0
        assert result["should_escalate_to_deep_path"] is True
        assert any("no contracts" in w for w in result["quality_warnings"])

    def test_good_contract_scores_high(self):
        c = _good_contract()
        result = check_quality([c])
        assert result["quality_score"] >= 0.8
        assert result["should_escalate_to_deep_path"] is False

    def test_bare_contract_scores_low(self):
        c = _bare_contract()
        result = check_quality([c])
        assert result["quality_score"] < 0.5

    def test_warns_on_vague_intended_change(self):
        c = _bare_contract()
        result = check_quality([c])
        assert any("intended_change too vague" in w for w in result["quality_warnings"])

    def test_warns_on_empty_must_not_break(self):
        c = _bare_contract()
        result = check_quality([c])
        assert any("must_not_break" in w for w in result["quality_warnings"])

    def test_warns_on_empty_validation_plan(self):
        c = _bare_contract()
        result = check_quality([c])
        assert any("validation_plan" in w for w in result["quality_warnings"])

    def test_warns_on_empty_failure_modes(self):
        c = _bare_contract()
        result = check_quality([c])
        assert any("likely_failure_modes" in w for w in result["quality_warnings"])

    def test_coverage_tracks_files(self):
        c = _good_contract(target_files=["a.py"])
        result = check_quality([c], changed_files=["a.py", "b.py"])
        assert result["coverage"]["covered"] == 1
        assert result["coverage"]["total"] == 2
        assert any("not covered" in w for w in result["quality_warnings"])

    def test_full_coverage_no_warning(self):
        c = _good_contract(target_files=["a.py", "b.py"])
        result = check_quality([c], changed_files=["a.py", "b.py"])
        uncovered_warnings = [w for w in result["quality_warnings"] if "not covered" in w]
        assert uncovered_warnings == []

    def test_escalate_on_very_low_quality(self):
        c = _bare_contract()
        result = check_quality([c])
        assert result["should_escalate_to_deep_path"] is True

    def test_no_escalate_on_good_quality(self):
        c = _good_contract()
        result = check_quality([c])
        assert result["should_escalate_to_deep_path"] is False
