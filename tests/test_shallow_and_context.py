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
from cold_eyes.git import estimate_tokens


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

# ---------------------------------------------------------------------------
# Token estimation (CJK-aware)
# ---------------------------------------------------------------------------

class TestEstimateTokens:
    def test_ascii_only(self):
        text = "hello world"  # 11 ASCII chars → 11 // 4 = 2
        assert estimate_tokens(text) == 11 // 4

    def test_cjk_only(self):
        text = "你好世界"  # 4 CJK chars → 4 tokens (1 char ≈ 1 token)
        assert estimate_tokens(text) == 4

    def test_mixed_content(self):
        text = "hello 你好"  # 6 ASCII + 2 CJK → 6//4 + 2 = 3
        assert estimate_tokens(text) == 6 // 4 + 2

    def test_cjk_higher_than_old_method(self):
        """CJK text should estimate higher than the old UTF-8 bytes // 4."""
        text = "這是一段中文測試文字用來驗證估算"  # 15 CJK chars
        old_estimate = len(text.encode("utf-8")) // 4  # 45 bytes // 4 = 11
        new_estimate = estimate_tokens(text)  # 15 tokens
        assert new_estimate > old_estimate

    def test_empty_string(self):
        assert estimate_tokens("") == 0

    def test_build_context_respects_cjk_budget(self):
        """Context with CJK should report accurate token count after truncation."""
        with patch("cold_eyes.context._recent_commits",
                   return_value=["abc1234 修復嚴重漏洞"]), \
             patch("cold_eyes.context._co_changed_files",
                   return_value=["auth.py"]):
            result = build_context(["some_file.py"], max_tokens=5)
        assert result["token_count"] == estimate_tokens(result["context_text"])


# ---------------------------------------------------------------------------
# WP2: Engine context integration (continued)
# ---------------------------------------------------------------------------

class TestEngineContextIntegrationContinued:
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


# ---------------------------------------------------------------------------
# Total input budget enforcement (max_input_tokens)
# ---------------------------------------------------------------------------

def _make_mock_adapter(stdout=None):
    """Helper: mock adapter returning a passing review."""
    mock_invocation = MagicMock()
    mock_invocation.exit_code = 0
    mock_invocation.stdout = stdout or (
        '{"pass": true, "review_status": "completed", '
        '"issues": [], "summary": "ok"}'
    )
    mock_invocation.failure_kind = None
    adapter = MagicMock()
    adapter.review.return_value = mock_invocation
    return adapter


def _engine_patches(**overrides):
    """Return a dict of standard engine patches for budget tests."""
    defaults = {
        "git_cmd_rv": "/repo",
        "files": (["src/main.py"], set()),
        "diff": {
            "diff_text": "--- a/src/main.py\n+++ b/src/main.py\n@@ -1 +1 @@\n-old\n+new",
            "file_count": 1, "token_count": 50, "truncated": False,
            "partial_files": [], "skipped_budget": [],
            "skipped_binary": [], "skipped_unreadable": [],
        },
        "context": {
            "context_text": "[Cold Eyes: Context]\nrecent stuff\n[End context]\n",
            "context_summary": "recent commits for 1 file(s)",
            "token_count": 200,
        },
        "hints": {
            "hint_text": "[Cold Eyes: State/Invariant Detector]\nsome hints\n[End]\n",
            "state_signals": [{"signal_type": "state_check", "line": "+if state"}],
            "repo_type": "general",
            "detector_focus": "general",
        },
    }
    defaults.update(overrides)
    return defaults


class TestMaxInputTokensBudget:
    """max_input_tokens caps the total content sent to the model."""

    def test_default_max_input_tokens(self):
        """Default = max_tokens + context_tokens + 1000."""
        from cold_eyes import engine

        adapter = _make_mock_adapter()
        p = _engine_patches()

        with patch.object(engine, "git_cmd", return_value=p["git_cmd_rv"]), \
             patch.object(engine, "collect_files", return_value=p["files"]), \
             patch("cold_eyes.engine.filter_file_list",
                   side_effect=lambda f, _: f), \
             patch("cold_eyes.engine.rank_file_list",
                   side_effect=lambda f, _: f), \
             patch("cold_eyes.engine.build_diff", return_value=p["diff"]), \
             patch("cold_eyes.engine.load_policy", return_value={}), \
             patch("cold_eyes.engine.consume_override",
                   return_value=(False, "")), \
             patch("cold_eyes.engine.build_context",
                   return_value=p["context"]) as mock_ctx, \
             patch("cold_eyes.engine.build_detector_hints",
                   return_value=p["hints"]), \
             patch("cold_eyes.engine.log_to_history"):
            result = engine.run(adapter=adapter)

        # With default budget (12000+2000+1000=15000), 50 diff tokens,
        # context (200) and hints should both fit.
        mock_ctx.assert_called_once()
        ctx_budget = mock_ctx.call_args[1]["max_tokens"]
        assert ctx_budget == 2000  # min(2000, 15000-50) = 2000
        assert result.get("hints_dropped") is not True

    def test_context_clamped_by_remaining_budget(self):
        """Context budget reduced when diff consumes most of the total budget."""
        from cold_eyes import engine

        adapter = _make_mock_adapter()
        # Diff uses 14500 of 15000 budget -> only 500 left for context
        big_diff = dict(_engine_patches()["diff"], token_count=14500)
        p = _engine_patches(diff=big_diff)

        with patch.object(engine, "git_cmd", return_value=p["git_cmd_rv"]), \
             patch.object(engine, "collect_files", return_value=p["files"]), \
             patch("cold_eyes.engine.filter_file_list",
                   side_effect=lambda f, _: f), \
             patch("cold_eyes.engine.rank_file_list",
                   side_effect=lambda f, _: f), \
             patch("cold_eyes.engine.build_diff", return_value=big_diff), \
             patch("cold_eyes.engine.load_policy", return_value={}), \
             patch("cold_eyes.engine.consume_override",
                   return_value=(False, "")), \
             patch("cold_eyes.engine.build_context",
                   return_value=p["context"]) as mock_ctx, \
             patch("cold_eyes.engine.build_detector_hints",
                   return_value=p["hints"]), \
             patch("cold_eyes.engine.log_to_history"):
            engine.run(adapter=adapter)

        # Context budget should be clamped: min(2000, 15000-14500) = 500
        ctx_budget = mock_ctx.call_args[1]["max_tokens"]
        assert ctx_budget == 500

    def test_context_skipped_when_no_budget_remains(self):
        """Context skipped entirely when diff exhausts the total budget."""
        from cold_eyes import engine

        adapter = _make_mock_adapter()
        # Diff uses all 15000 tokens
        full_diff = dict(_engine_patches()["diff"], token_count=15000)

        with patch.object(engine, "git_cmd", return_value="/repo"), \
             patch.object(engine, "collect_files",
                          return_value=(["src/main.py"], set())), \
             patch("cold_eyes.engine.filter_file_list",
                   side_effect=lambda f, _: f), \
             patch("cold_eyes.engine.rank_file_list",
                   side_effect=lambda f, _: f), \
             patch("cold_eyes.engine.build_diff", return_value=full_diff), \
             patch("cold_eyes.engine.load_policy", return_value={}), \
             patch("cold_eyes.engine.consume_override",
                   return_value=(False, "")), \
             patch("cold_eyes.engine.build_context") as mock_ctx, \
             patch("cold_eyes.engine.build_detector_hints",
                   return_value=_engine_patches()["hints"]), \
             patch("cold_eyes.engine.log_to_history"):
            engine.run(adapter=adapter)

        mock_ctx.assert_not_called()

    def test_hints_dropped_when_budget_exhausted(self):
        """Detector hints dropped (not truncated) when no budget remains."""
        from cold_eyes import engine

        adapter = _make_mock_adapter()
        p = _engine_patches()
        big_diff = dict(p["diff"], token_count=14000)
        # Make hints large enough to exceed remaining after context
        big_hints = dict(p["hints"],
                         hint_text="x" * 4000)  # ~1000 tokens ASCII

        with patch.object(engine, "git_cmd", return_value="/repo"), \
             patch.object(engine, "collect_files",
                          return_value=(["src/main.py"], set())), \
             patch("cold_eyes.engine.filter_file_list",
                   side_effect=lambda f, _: f), \
             patch("cold_eyes.engine.rank_file_list",
                   side_effect=lambda f, _: f), \
             patch("cold_eyes.engine.build_diff", return_value=big_diff), \
             patch("cold_eyes.engine.load_policy", return_value={}), \
             patch("cold_eyes.engine.consume_override",
                   return_value=(False, "")), \
             patch("cold_eyes.engine.build_context",
                   return_value=p["context"]), \
             patch("cold_eyes.engine.build_detector_hints",
                   return_value=big_hints), \
             patch("cold_eyes.engine.log_to_history"):
            result = engine.run(adapter=adapter)

        assert result.get("hints_dropped") is True
        # Hints text should NOT appear in the diff sent to model
        sent_diff = adapter.review.call_args[0][0]
        assert "x" * 4000 not in sent_diff

    def test_explicit_max_input_tokens_overrides_default(self):
        """Explicit max_input_tokens setting takes precedence."""
        from cold_eyes import engine

        adapter = _make_mock_adapter()
        p = _engine_patches()

        with patch.object(engine, "git_cmd", return_value="/repo"), \
             patch.object(engine, "collect_files",
                          return_value=(["src/main.py"], set())), \
             patch("cold_eyes.engine.filter_file_list",
                   side_effect=lambda f, _: f), \
             patch("cold_eyes.engine.rank_file_list",
                   side_effect=lambda f, _: f), \
             patch("cold_eyes.engine.build_diff", return_value=p["diff"]), \
             patch("cold_eyes.engine.load_policy", return_value={}), \
             patch("cold_eyes.engine.consume_override",
                   return_value=(False, "")), \
             patch("cold_eyes.engine.build_context",
                   return_value=p["context"]) as mock_ctx, \
             patch("cold_eyes.engine.build_detector_hints",
                   return_value=p["hints"]), \
             patch("cold_eyes.engine.log_to_history"):
            # Tight budget: 100 total, diff uses 50 -> only 50 left for context
            engine.run(adapter=adapter, max_input_tokens=100)

        ctx_budget = mock_ctx.call_args[1]["max_tokens"]
        assert ctx_budget == 50  # min(2000, 100-50)

    def test_env_var_max_input_tokens(self):
        """COLD_REVIEW_MAX_INPUT_TOKENS env var is respected."""
        from cold_eyes import engine

        adapter = _make_mock_adapter()
        p = _engine_patches()

        with patch.object(engine, "git_cmd", return_value="/repo"), \
             patch.object(engine, "collect_files",
                          return_value=(["src/main.py"], set())), \
             patch("cold_eyes.engine.filter_file_list",
                   side_effect=lambda f, _: f), \
             patch("cold_eyes.engine.rank_file_list",
                   side_effect=lambda f, _: f), \
             patch("cold_eyes.engine.build_diff", return_value=p["diff"]), \
             patch("cold_eyes.engine.load_policy", return_value={}), \
             patch("cold_eyes.engine.consume_override",
                   return_value=(False, "")), \
             patch("cold_eyes.engine.build_context",
                   return_value=p["context"]) as mock_ctx, \
             patch("cold_eyes.engine.build_detector_hints",
                   return_value=p["hints"]), \
             patch("cold_eyes.engine.log_to_history"), \
             patch.dict("os.environ",
                        {"COLD_REVIEW_MAX_INPUT_TOKENS": "80"}):
            engine.run(adapter=adapter)

        ctx_budget = mock_ctx.call_args[1]["max_tokens"]
        assert ctx_budget == 30  # min(2000, 80-50)
