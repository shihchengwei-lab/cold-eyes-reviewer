"""Tests for shallow review path (WP1) and context retrieval (WP2)."""

import os
import sys
import pytest
from unittest.mock import patch, MagicMock

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from cold_eyes.prompt import build_prompt_text
from cold_eyes.context import build_context, _recent_commits, _co_changed_files


# ---------------------------------------------------------------------------
# WP1: Shallow prompt
# ---------------------------------------------------------------------------

class TestShallowPrompt:
    def test_deep_prompt_loads(self):
        text = build_prompt_text(language="English", depth="deep")
        assert "Cold Eyes" in text
        assert "邏輯錯誤" in text or "zero-context" in text.lower()

    def test_shallow_prompt_loads(self):
        text = build_prompt_text(language="English", depth="shallow")
        assert "Cold Eyes" in text
        assert "輕量模式" in text or "shallow" in text.lower()

    def test_shallow_prompt_critical_only(self):
        text = build_prompt_text(language="English", depth="shallow")
        assert "critical" in text.lower()
        # shallow prompt should not mention minor/major as check targets
        assert "major" not in text.split("不檢查")[0] or "minor" not in text.split("不檢查")[0]

    def test_shallow_prompt_language_substitution(self):
        text = build_prompt_text(language="日本語", depth="shallow")
        assert "日本語" in text

    def test_deep_prompt_language_substitution(self):
        text = build_prompt_text(language="日本語", depth="deep")
        assert "日本語" in text

    def test_default_depth_is_deep(self):
        deep_text = build_prompt_text(language="English")
        explicit_deep = build_prompt_text(language="English", depth="deep")
        assert deep_text == explicit_deep

    def test_shallow_differs_from_deep(self):
        shallow = build_prompt_text(language="English", depth="shallow")
        deep = build_prompt_text(language="English", depth="deep")
        assert shallow != deep

    def test_shallow_prompt_shorter_than_deep(self):
        shallow = build_prompt_text(language="English", depth="shallow")
        deep = build_prompt_text(language="English", depth="deep")
        assert len(shallow) < len(deep)

    def test_shallow_fallback_on_missing_template(self):
        import cold_eyes.prompt as prompt_mod
        orig = prompt_mod.PROMPT_TEMPLATE_SHALLOW
        try:
            prompt_mod.PROMPT_TEMPLATE_SHALLOW = "/nonexistent/path.txt"
            text = build_prompt_text(language="English", depth="shallow")
            assert "Cold Eyes" in text
            assert "shallow" in text.lower()
        finally:
            prompt_mod.PROMPT_TEMPLATE_SHALLOW = orig

    def test_deep_fallback_on_missing_template(self):
        import cold_eyes.prompt as prompt_mod
        orig = prompt_mod.PROMPT_TEMPLATE
        try:
            prompt_mod.PROMPT_TEMPLATE = "/nonexistent/path.txt"
            text = build_prompt_text(language="English", depth="deep")
            assert "Cold Eyes" in text
        finally:
            prompt_mod.PROMPT_TEMPLATE = orig


# ---------------------------------------------------------------------------
# WP1: Engine shallow model selection
# ---------------------------------------------------------------------------

class TestEngineShallowModel:
    def test_shallow_uses_shallow_model(self):
        """Shallow path should call adapter with shallow_model, not main model."""
        from cold_eyes import engine

        mock_invocation = MagicMock()
        mock_invocation.exit_code = 0
        mock_invocation.stdout = '{"pass": true, "review_status": "completed", "issues": [], "summary": "ok"}'
        mock_invocation.failure_kind = None

        mock_adapter = MagicMock()
        mock_adapter.review.return_value = mock_invocation

        with patch.object(engine, "git_cmd", return_value="/repo"), \
             patch.object(engine, "collect_files",
                          return_value=(["tests/test_foo.py"], set())), \
             patch("cold_eyes.engine.filter_file_list",
                   side_effect=lambda f, _: f), \
             patch("cold_eyes.engine.rank_file_list",
                   side_effect=lambda f, _: f), \
             patch("cold_eyes.engine.build_diff", return_value={
                 "diff_text": "--- a/tests/test_foo.py\n+++ b/tests/test_foo.py\n@@ -1 +1 @@\n-old\n+new",
                 "file_count": 1, "token_count": 50, "truncated": False,
                 "partial_files": [], "skipped_budget": [],
                 "skipped_binary": [], "skipped_unreadable": [],
             }), \
             patch("cold_eyes.engine.load_policy", return_value={}), \
             patch("cold_eyes.engine.consume_override",
                   return_value=(False, "")), \
             patch("cold_eyes.engine.build_context",
                   return_value={"context_text": "", "context_summary": "", "token_count": 0}), \
             patch("cold_eyes.engine.log_to_history"):
            result = engine.run(adapter=mock_adapter, model="opus",
                                shallow_model="haiku")

        # test-only files → shallow → should use haiku
        assert result["review_depth"] == "shallow"
        call_args = mock_adapter.review.call_args
        assert call_args[0][2] == "haiku"  # third arg is model

    def test_deep_uses_main_model(self):
        """Deep path should call adapter with main model."""
        from cold_eyes import engine

        mock_invocation = MagicMock()
        mock_invocation.exit_code = 0
        mock_invocation.stdout = '{"pass": true, "review_status": "completed", "issues": [], "summary": "ok"}'
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
             patch("cold_eyes.engine.build_context",
                   return_value={"context_text": "", "context_summary": "", "token_count": 0}), \
             patch("cold_eyes.engine.log_to_history"):
            result = engine.run(adapter=mock_adapter, model="opus",
                                shallow_model="haiku")

        assert result["review_depth"] == "deep"
        call_args = mock_adapter.review.call_args
        assert call_args[0][2] == "opus"

    def test_shallow_uses_shallow_prompt(self):
        """Shallow path should use the shallow prompt template."""
        from cold_eyes import engine

        mock_invocation = MagicMock()
        mock_invocation.exit_code = 0
        mock_invocation.stdout = '{"pass": true, "review_status": "completed", "issues": [], "summary": "ok"}'
        mock_invocation.failure_kind = None

        mock_adapter = MagicMock()
        mock_adapter.review.return_value = mock_invocation

        with patch.object(engine, "git_cmd", return_value="/repo"), \
             patch.object(engine, "collect_files",
                          return_value=(["tests/test_foo.py"], set())), \
             patch("cold_eyes.engine.filter_file_list",
                   side_effect=lambda f, _: f), \
             patch("cold_eyes.engine.rank_file_list",
                   side_effect=lambda f, _: f), \
             patch("cold_eyes.engine.build_diff", return_value={
                 "diff_text": "diff content",
                 "file_count": 1, "token_count": 50, "truncated": False,
                 "partial_files": [], "skipped_budget": [],
                 "skipped_binary": [], "skipped_unreadable": [],
             }), \
             patch("cold_eyes.engine.load_policy", return_value={}), \
             patch("cold_eyes.engine.consume_override",
                   return_value=(False, "")), \
             patch("cold_eyes.engine.build_context",
                   return_value={"context_text": "", "context_summary": "", "token_count": 0}), \
             patch("cold_eyes.engine.log_to_history"):
            engine.run(adapter=mock_adapter)

        prompt_text = mock_adapter.review.call_args[0][1]
        assert "輕量模式" in prompt_text or "shallow" in prompt_text.lower()


# ---------------------------------------------------------------------------
# WP2: Context retrieval
# ---------------------------------------------------------------------------

class TestContextRetrieval:
    def test_empty_files(self):
        result = build_context([])
        assert result["context_text"] == ""
        assert result["token_count"] == 0

    def test_recent_commits_returns_list(self):
        commits = _recent_commits("cold_eyes/engine.py", limit=3)
        assert isinstance(commits, list)
        # This file exists in the repo, so should have commits
        assert len(commits) > 0

    def test_recent_commits_nonexistent_file(self):
        commits = _recent_commits("nonexistent_file_xyz.py")
        assert commits == []

    def test_co_changed_files_returns_list(self):
        co = _co_changed_files("cold_eyes/engine.py", limit=3)
        assert isinstance(co, list)

    def test_co_changed_nonexistent_file(self):
        co = _co_changed_files("nonexistent_file_xyz.py")
        assert co == []

    def test_build_context_with_real_files(self):
        result = build_context(["cold_eyes/engine.py"], max_tokens=5000)
        assert isinstance(result["context_text"], str)
        assert result["token_count"] >= 0
        if result["context_text"]:
            assert "[Cold Eyes: Context for review]" in result["context_text"]
            assert "[End context]" in result["context_text"]

    def test_build_context_token_budget_enforced(self):
        result = build_context(["cold_eyes/engine.py"], max_tokens=10)
        assert result["token_count"] <= 10

    def test_build_context_summary_populated(self):
        result = build_context(["cold_eyes/engine.py"])
        assert result["context_summary"]

    def test_build_context_no_git_history(self):
        with patch("cold_eyes.context._recent_commits", return_value=[]), \
             patch("cold_eyes.context._co_changed_files", return_value=[]):
            result = build_context(["some_file.py"])
        assert result["context_text"] == ""
        assert result["context_summary"] == "no git history"


# ---------------------------------------------------------------------------
# WP2: Engine context integration
# ---------------------------------------------------------------------------

class TestEngineContextIntegration:
    def test_deep_path_gets_context(self):
        """Deep path should invoke build_context and prepend to diff."""
        from cold_eyes import engine

        mock_invocation = MagicMock()
        mock_invocation.exit_code = 0
        mock_invocation.stdout = '{"pass": true, "review_status": "completed", "issues": [], "summary": "ok"}'
        mock_invocation.failure_kind = None

        mock_adapter = MagicMock()
        mock_adapter.review.return_value = mock_invocation

        fake_context = {
            "context_text": "[Cold Eyes: Context]\nrecent stuff\n[End context]\n",
            "context_summary": "recent commits for 1 file(s)",
            "token_count": 20,
        }

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
             patch("cold_eyes.engine.build_context",
                   return_value=fake_context) as mock_ctx, \
             patch("cold_eyes.engine.log_to_history"):
            result = engine.run(adapter=mock_adapter)

        mock_ctx.assert_called_once()
        # diff_text sent to adapter should start with context
        sent_diff = mock_adapter.review.call_args[0][0]
        assert sent_diff.startswith("[Cold Eyes: Context]")
        assert result.get("context_summary") == "recent commits for 1 file(s)"

    def test_shallow_path_no_context(self):
        """Shallow path should not invoke build_context."""
        from cold_eyes import engine

        mock_invocation = MagicMock()
        mock_invocation.exit_code = 0
        mock_invocation.stdout = '{"pass": true, "review_status": "completed", "issues": [], "summary": "ok"}'
        mock_invocation.failure_kind = None

        mock_adapter = MagicMock()
        mock_adapter.review.return_value = mock_invocation

        with patch.object(engine, "git_cmd", return_value="/repo"), \
             patch.object(engine, "collect_files",
                          return_value=(["tests/test_foo.py"], set())), \
             patch("cold_eyes.engine.filter_file_list",
                   side_effect=lambda f, _: f), \
             patch("cold_eyes.engine.rank_file_list",
                   side_effect=lambda f, _: f), \
             patch("cold_eyes.engine.build_diff", return_value={
                 "diff_text": "diff content",
                 "file_count": 1, "token_count": 50, "truncated": False,
                 "partial_files": [], "skipped_budget": [],
                 "skipped_binary": [], "skipped_unreadable": [],
             }), \
             patch("cold_eyes.engine.load_policy", return_value={}), \
             patch("cold_eyes.engine.consume_override",
                   return_value=(False, "")), \
             patch("cold_eyes.engine.build_context") as mock_ctx, \
             patch("cold_eyes.engine.log_to_history"):
            result = engine.run(adapter=mock_adapter)

        mock_ctx.assert_not_called()
        assert result["review_depth"] == "shallow"
        assert "context_summary" not in result

    def test_context_disabled_with_zero_tokens(self):
        """context_tokens=0 should skip context retrieval."""
        from cold_eyes import engine

        mock_invocation = MagicMock()
        mock_invocation.exit_code = 0
        mock_invocation.stdout = '{"pass": true, "review_status": "completed", "issues": [], "summary": "ok"}'
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
                 "diff_text": "diff content",
                 "file_count": 1, "token_count": 50, "truncated": False,
                 "partial_files": [], "skipped_budget": [],
                 "skipped_binary": [], "skipped_unreadable": [],
             }), \
             patch("cold_eyes.engine.load_policy", return_value={}), \
             patch("cold_eyes.engine.consume_override",
                   return_value=(False, "")), \
             patch("cold_eyes.engine.build_context") as mock_ctx, \
             patch("cold_eyes.engine.log_to_history"):
            engine.run(adapter=mock_adapter, context_tokens=0)

        mock_ctx.assert_not_called()
