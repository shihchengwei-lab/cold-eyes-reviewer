"""Tests for the triage module (classify_file_role + classify_depth)."""

import os
import sys
import pytest
from unittest.mock import patch, MagicMock

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from cold_eyes.triage import classify_file_role, classify_depth


# ---------------------------------------------------------------------------
# classify_file_role
# ---------------------------------------------------------------------------

class TestClassifyFileRole:
    # test role
    def test_tests_dir(self):
        assert classify_file_role("tests/test_engine.py") == "test"

    def test_test_prefix(self):
        assert classify_file_role("test_utils.py") == "test"

    def test_test_suffix(self):
        assert classify_file_role("src/engine_test.py") == "test"

    def test_spec_dir(self):
        assert classify_file_role("spec/models/user_spec.rb") == "test"

    # docs role
    def test_markdown(self):
        assert classify_file_role("README.md") == "docs"

    def test_docs_dir(self):
        assert classify_file_role("docs/architecture.md") == "docs"

    def test_changelog(self):
        assert classify_file_role("CHANGELOG") == "docs"

    # config role
    def test_yaml(self):
        assert classify_file_role(".github/workflows/test.yml") == "config"

    def test_toml(self):
        assert classify_file_role("pyproject.toml") == "config"

    def test_root_json(self):
        assert classify_file_role("package.json") == "config"

    def test_nested_json_is_source(self):
        assert classify_file_role("src/data/fixtures.json") == "source"

    def test_dotenv(self):
        assert classify_file_role(".env.example") == "config"

    # generated role
    def test_min_js(self):
        assert classify_file_role("assets/app.min.js") == "generated"

    def test_min_css(self):
        assert classify_file_role("static/style.min.css") == "generated"

    def test_pb_go(self):
        assert classify_file_role("proto/service.pb.go") == "generated"

    def test_generated_suffix(self):
        assert classify_file_role("models/user_generated.py") == "generated"

    def test_dist_dir(self):
        assert classify_file_role("dist/bundle.js") == "generated"

    # migration role
    def test_migrations_dir(self):
        assert classify_file_role("migrations/001_init.sql") == "migration"

    def test_alembic_dir(self):
        assert classify_file_role("alembic/versions/abc123.py") == "migration"

    def test_migrate_dir(self):
        assert classify_file_role("db/migrate/20210101_create.rb") == "migration"

    # source role (fallback)
    def test_python_source(self):
        assert classify_file_role("cold_eyes/engine.py") == "source"

    def test_js_source(self):
        assert classify_file_role("src/components/App.jsx") == "source"

    # windows paths
    def test_backslash_paths(self):
        assert classify_file_role("tests\\test_foo.py") == "test"


# ---------------------------------------------------------------------------
# classify_depth
# ---------------------------------------------------------------------------

class TestClassifyDepth:
    # skip cases
    def test_empty_files_skip(self):
        result = classify_depth([])
        assert result["review_depth"] == "skip"

    def test_docs_only_skip(self):
        result = classify_depth(["README.md", "docs/guide.md"])
        assert result["review_depth"] == "skip"

    def test_generated_only_skip(self):
        result = classify_depth(["dist/bundle.js", "assets/app.min.js"])
        assert result["review_depth"] == "skip"

    def test_config_only_skip(self):
        result = classify_depth(["pyproject.toml", ".github/workflows/ci.yml"])
        assert result["review_depth"] == "skip"

    def test_mixed_skip_roles_skip(self):
        result = classify_depth(["README.md", "pyproject.toml", "dist/out.js"])
        assert result["review_depth"] == "skip"

    # deep cases — config with secrets keywords
    def test_env_config_deep(self):
        result = classify_depth([".env.production"])
        assert result["review_depth"] == "deep"
        assert "secrets_privacy" in result["risk_types"]

    # deep cases — risk category match
    def test_auth_file_deep(self):
        result = classify_depth(["src/auth/middleware.py"])
        assert result["review_depth"] == "deep"
        assert "auth_permission" in result["risk_types"]

    def test_database_file_deep(self):
        result = classify_depth(["src/db/repository.py"])
        assert result["review_depth"] == "deep"
        assert "persistence" in result["risk_types"]

    def test_api_route_deep(self):
        result = classify_depth(["src/api/handler.py"])
        assert result["review_depth"] == "deep"
        assert "public_api" in result["risk_types"]

    # deep cases — source files
    def test_source_file_deep(self):
        result = classify_depth(["src/utils/helpers.py"])
        assert result["review_depth"] == "deep"

    def test_migration_file_deep(self):
        result = classify_depth(["migrations/001_add_table.sql"])
        assert result["review_depth"] == "deep"

    # shallow cases — test-only
    def test_test_only_shallow(self):
        result = classify_depth(["tests/test_foo.py", "tests/test_bar.py"])
        assert result["review_depth"] == "shallow"

    # mixed: source + docs → deep (source dominates)
    def test_source_plus_docs_deep(self):
        result = classify_depth(["README.md", "src/main.py"])
        assert result["review_depth"] == "deep"

    # risk_types populated
    def test_risk_types_populated(self):
        result = classify_depth(["src/auth/guard.py", "src/db/query.py"])
        assert "auth_permission" in result["risk_types"]
        assert "persistence" in result["risk_types"]

    # why_depth_selected populated
    def test_why_populated(self):
        result = classify_depth(["README.md"])
        assert result["why_depth_selected"]
        assert "docs" in result["why_depth_selected"]


# ---------------------------------------------------------------------------
# Triage safety — skip must not miss real problems
# ---------------------------------------------------------------------------

class TestTriageSafety:
    def test_config_with_password_keyword_not_skipped(self):
        """Config files containing password-related names should not be skipped."""
        result = classify_depth(["config/password_policy.yml"])
        assert result["review_depth"] != "skip"

    def test_env_production_not_skipped(self):
        result = classify_depth([".env.production"])
        assert result["review_depth"] == "deep"

    def test_config_with_token_keyword_not_skipped(self):
        result = classify_depth(["settings/api_token.toml"])
        assert result["review_depth"] != "skip"

    def test_docs_plus_source_not_skipped(self):
        """Docs + source mix should deep-review (source dominates)."""
        result = classify_depth(["README.md", "src/auth.py"])
        assert result["review_depth"] == "deep"

    def test_generated_plus_migration_not_skipped(self):
        """Generated + migration mix should deep-review."""
        result = classify_depth(["dist/bundle.js", "migrations/002_alter.sql"])
        assert result["review_depth"] == "deep"

    def test_pure_generated_stays_skip(self):
        """Pure generated files should still be skipped."""
        result = classify_depth(["dist/bundle.js", "assets/app.min.css"])
        assert result["review_depth"] == "skip"

    def test_test_with_auth_keyword_goes_deep(self):
        """Test files with auth keywords hit risk category → deep (risk overrides role)."""
        result = classify_depth(["tests/test_auth.py", "tests/test_permissions.py"])
        assert result["review_depth"] == "deep"
        assert "auth_permission" in result["risk_types"]

    def test_pure_test_files_shallow(self):
        """Test files without risk keywords should be shallow."""
        result = classify_depth(["tests/test_utils.py", "tests/test_math.py"])
        assert result["review_depth"] == "shallow"

    def test_single_source_file_deep(self):
        """Even a single plain source file should get deep review."""
        result = classify_depth(["lib/utils.py"])
        assert result["review_depth"] == "deep"


# ---------------------------------------------------------------------------
# Engine triage integration
# ---------------------------------------------------------------------------

class TestEngineTriageIntegration:
    def test_skip_does_not_call_model(self):
        """Engine skip path should not invoke the model adapter."""
        from cold_eyes import engine

        mock_adapter = MagicMock()
        with patch.object(engine, "git_cmd", return_value="/repo"), \
             patch.object(engine, "collect_files",
                          return_value=(["README.md", "CHANGELOG.md"], set())), \
             patch("cold_eyes.engine.filter_file_list",
                   side_effect=lambda f, _: f), \
             patch("cold_eyes.engine.rank_file_list",
                   side_effect=lambda f, _: f), \
             patch("cold_eyes.engine.load_policy", return_value={}), \
             patch("cold_eyes.engine.consume_override",
                   return_value=(False, "")), \
             patch("cold_eyes.engine.log_to_history"):
            result = engine.run(adapter=mock_adapter)

        mock_adapter.review.assert_not_called()
        assert result["state"] == "skipped"
        assert result["review_depth"] == "skip"

    def test_deep_path_calls_model(self):
        """Engine deep path should proceed to model call."""
        from cold_eyes import engine

        mock_invocation = MagicMock()
        mock_invocation.exit_code = 0
        mock_invocation.stdout = '{"pass": true, "review_status": "clean", "issues": [], "summary": "ok"}'
        mock_invocation.failure_kind = None

        mock_adapter = MagicMock()
        mock_adapter.review.return_value = mock_invocation

        with patch.object(engine, "git_cmd", return_value="/repo"), \
             patch.object(engine, "collect_files",
                          return_value=(["src/main.py"], set())), \
             patch("cold_eyes.engine.filter_file_list",
                   side_effect=lambda f, _: f), \
             patch("cold_eyes.engine.rank_file_list",
                   side_effect=lambda f, _: f), \
             patch("cold_eyes.engine.build_diff", return_value={
                 "diff_text": "--- a/src/main.py\n+++ b/src/main.py\n@@ -1 +1 @@\n-old\n+new",
                 "file_count": 1, "token_count": 50, "truncated": False,
                 "partial_files": [], "skipped_budget": [],
                 "skipped_binary": [], "skipped_unreadable": [],
             }), \
             patch("cold_eyes.engine.load_policy", return_value={}), \
             patch("cold_eyes.engine.consume_override",
                   return_value=(False, "")), \
             patch("cold_eyes.engine.log_to_history"):
            result = engine.run(adapter=mock_adapter)

        mock_adapter.review.assert_called_once()
        assert result["review_depth"] == "deep"
