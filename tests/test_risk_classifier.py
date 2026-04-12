"""Tests for cold_eyes.gates.risk_classifier."""

from cold_eyes.gates.risk_classifier import classify_risk


class TestClassifyRisk:
    def test_no_files(self):
        r = classify_risk([])
        assert r["risk_level"] == "low"
        assert r["recommended_depth"] == "skip"

    def test_docs_only_is_low(self):
        r = classify_risk(["README.md", "docs/guide.md"])
        assert r["risk_level"] == "low"
        assert r["recommended_depth"] == "skip"

    def test_auth_file_triggers_risk(self):
        r = classify_risk(["src/auth_middleware.py"])
        assert "auth_permission" in r["risk_categories"]
        assert r["risk_level"] in ("medium", "high", "critical")

    def test_migration_file_triggers_risk(self):
        r = classify_risk(["migrations/001_add_users.sql"])
        assert r["risk_level"] in ("medium", "high", "critical")
        assert r["recommended_depth"] == "deep"
        assert "migration_schema" in r["risk_categories"]

    def test_many_source_files_escalates(self):
        files = [f"src/module_{i}.py" for i in range(10)]
        r = classify_risk(files)
        assert r["risk_level"] in ("medium", "high", "critical")
        assert any("large change" in f for f in r["risk_factors"])

    def test_contract_risk_categories_included(self):
        contracts = [{"risk_categories": ["state_invariant"], "priority": "must"}]
        r = classify_risk(["src/main.py"], contracts=contracts)
        assert "state_invariant" in r["risk_categories"]

    def test_must_contracts_increase_score(self):
        r_without = classify_risk(["src/main.py"])
        r_with = classify_risk(
            ["src/main.py"],
            contracts=[{"priority": "must"}, {"priority": "must"}, {"priority": "must"}],
        )
        levels = ["low", "medium", "high", "critical"]
        assert levels.index(r_with["risk_level"]) >= levels.index(r_without["risk_level"])

    def test_test_only_is_low(self):
        r = classify_risk(["tests/test_foo.py"])
        assert r["risk_level"] == "low"

    def test_recommended_depth_matches_level(self):
        # low + docs -> skip
        r = classify_risk(["CHANGELOG.md"])
        assert r["recommended_depth"] == "skip"
        # source with multiple risk signals -> deep
        r = classify_risk(["src/auth_database.py"])
        assert r["recommended_depth"] == "deep"

    def test_multiple_risk_categories(self):
        r = classify_risk(["src/auth_api_handler.py"])
        assert len(r["risk_categories"]) >= 2
