"""Tests for cold_eyes.contract.generator."""

from cold_eyes.contract.generator import generate_contracts
from cold_eyes.contract.schema import validate_contract


class TestGenerateContracts:
    def test_empty_files_returns_empty(self):
        assert generate_contracts("test", []) == []

    def test_source_files_produce_lint_and_review(self):
        contracts = generate_contracts("add feature", ["src/main.py", "src/util.py"])
        types = {c["check_type"] for c in contracts}
        assert "lint_clean" in types
        assert "llm_review" in types

    def test_test_files_produce_test_pass(self):
        contracts = generate_contracts("fix test", ["tests/test_foo.py"])
        types = {c["check_type"] for c in contracts}
        assert "test_pass" in types

    def test_migration_files_produce_custom(self):
        contracts = generate_contracts("add migration", ["migrations/001.sql"])
        types = {c["check_type"] for c in contracts}
        assert "custom" in types
        migration_c = [c for c in contracts if c["check_type"] == "custom"][0]
        assert "migration_schema" in migration_c["risk_categories"]

    def test_risk_categories_detected_from_paths(self):
        contracts = generate_contracts("fix auth", ["src/auth_middleware.py"])
        review_c = [c for c in contracts if c["check_type"] == "llm_review"][0]
        assert "auth_permission" in review_c["risk_categories"]

    def test_explicit_risk_types_included(self):
        contracts = generate_contracts(
            "fix state bug",
            ["src/main.py"],
            risk_types=["state_invariant"],
        )
        review_c = [c for c in contracts if c["check_type"] == "llm_review"][0]
        assert "state_invariant" in review_c["risk_categories"]

    def test_docs_only_minimal_contracts(self):
        contracts = generate_contracts("update readme", ["README.md", "docs/guide.md"])
        # Docs-only: no test, no lint, but still gets llm_review (low priority)
        types = {c["check_type"] for c in contracts}
        assert "test_pass" not in types
        assert "lint_clean" not in types

    def test_mixed_files(self):
        contracts = generate_contracts(
            "full feature",
            ["src/api.py", "tests/test_api.py", "README.md"],
        )
        types = {c["check_type"] for c in contracts}
        assert "test_pass" in types
        assert "lint_clean" in types
        assert "llm_review" in types

    def test_all_contracts_validate(self):
        contracts = generate_contracts("test", ["src/main.py", "tests/test_main.py"])
        for c in contracts:
            ok, errors = validate_contract(c)
            assert ok, f"contract failed validation: {errors}"

    def test_high_risk_review_is_must_priority(self):
        contracts = generate_contracts("fix auth", ["src/auth.py"])
        review_c = [c for c in contracts if c["check_type"] == "llm_review"][0]
        assert review_c["priority"] == "must"  # because risk categories matched
