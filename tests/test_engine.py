"""Tests for cold_review_engine.py — policy, parsing, diff building, binary detection."""

import importlib.util
import json
import os
import tempfile

import pytest

# ---------------------------------------------------------------------------
# Import engine via importlib (underscore name, but keep it explicit)
# ---------------------------------------------------------------------------

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ENGINE_PATH = os.path.join(PROJECT_ROOT, "cold_review_engine.py")


def load_engine():
    spec = importlib.util.spec_from_file_location("cold_review_engine", ENGINE_PATH)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


engine = load_engine()


# ===========================================================================
# parse_review_output
# ===========================================================================

class TestParseReviewOutput:
    def test_valid_review(self):
        raw = json.dumps({
            "type": "result", "subtype": "success",
            "result": json.dumps({
                "pass": True, "issues": [], "summary": "All good"
            })
        })
        r = engine.parse_review_output(raw)
        assert r["pass"] is True
        assert r["review_status"] == "completed"
        assert r["summary"] == "All good"

    def test_invalid_json_returns_failed(self):
        r = engine.parse_review_output("not json at all")
        assert r["review_status"] == "failed"
        assert r["pass"] is True
        assert r["issues"] == []

    def test_markdown_wrapped_json(self):
        inner = json.dumps({"pass": False, "issues": [], "summary": "test"})
        raw = json.dumps({
            "type": "result", "subtype": "success",
            "result": f"```json\n{inner}\n```"
        })
        r = engine.parse_review_output(raw)
        assert r["pass"] is False

    def test_missing_fields_get_defaults(self):
        raw = json.dumps({
            "type": "result", "subtype": "success",
            "result": json.dumps({"issues": [{"check": "x"}]})
        })
        r = engine.parse_review_output(raw)
        assert r["review_status"] == "completed"
        assert r["pass"] is True
        issue = r["issues"][0]
        assert issue["severity"] == "major"
        assert issue["confidence"] == "medium"
        assert issue["category"] == "correctness"
        assert issue["file"] == "unknown"

    def test_empty_result_field(self):
        raw = json.dumps({"type": "result", "result": ""})
        r = engine.parse_review_output(raw)
        assert r["review_status"] == "failed"


# ===========================================================================
# apply_policy — infrastructure failure
# ===========================================================================

class TestApplyPolicyInfraFailure:
    def _infra_review(self, summary="parse error"):
        return {
            "pass": True, "review_status": "failed",
            "issues": [], "summary": summary,
        }

    def test_block_mode_blocks_on_infra_failure(self):
        outcome = engine.apply_policy(self._infra_review(), "block", "critical", False, "medium")
        assert outcome["action"] == "block"
        assert outcome["state"] == "infra_failed"
        assert "ALLOW_ONCE" in outcome["reason"]

    def test_report_mode_passes_on_infra_failure(self):
        outcome = engine.apply_policy(self._infra_review(), "report", "critical", False, "medium")
        assert outcome["action"] == "pass"
        assert outcome["state"] == "failed"

    def test_override_bypasses_infra_block(self):
        outcome = engine.apply_policy(self._infra_review(), "block", "critical", True, "medium")
        assert outcome["action"] == "pass"
        assert outcome["state"] == "overridden"

    def test_infra_block_includes_error_detail(self):
        outcome = engine.apply_policy(
            self._infra_review("claude exit 1"), "block", "critical", False, "medium"
        )
        assert "claude exit 1" in outcome["reason"]


# ===========================================================================
# apply_policy — review completed
# ===========================================================================

class TestApplyPolicyReview:
    def _review(self, severity, pass_val=False, confidence="high"):
        return {
            "pass": pass_val, "review_status": "completed",
            "issues": [{"severity": severity, "confidence": confidence,
                        "check": "x", "verdict": "y", "fix": "z"}],
            "summary": "test",
        }

    def test_critical_blocks_at_critical_threshold(self):
        outcome = engine.apply_policy(self._review("critical"), "block", "critical", False, "medium")
        assert outcome["action"] == "block"
        assert outcome["state"] == "blocked"

    def test_major_does_not_block_at_critical_threshold(self):
        outcome = engine.apply_policy(self._review("major"), "block", "critical", False, "medium")
        assert outcome["action"] == "pass"
        assert outcome["state"] == "passed"

    def test_major_blocks_at_major_threshold(self):
        outcome = engine.apply_policy(self._review("major"), "block", "major", False, "medium")
        assert outcome["action"] == "block"
        assert outcome["state"] == "blocked"

    def test_minor_never_blocks(self):
        outcome = engine.apply_policy(self._review("minor"), "block", "critical", False, "medium")
        assert outcome["action"] == "pass"
        outcome = engine.apply_policy(self._review("minor"), "block", "major", False, "medium")
        assert outcome["action"] == "pass"

    def test_override_skips_block(self):
        outcome = engine.apply_policy(self._review("critical"), "block", "critical", True, "medium")
        assert outcome["action"] == "pass"
        assert outcome["state"] == "overridden"

    def test_report_mode_never_blocks(self):
        outcome = engine.apply_policy(self._review("critical"), "report", "critical", False, "medium")
        assert outcome["action"] == "pass"
        assert outcome["state"] == "reported"

    def test_report_mode_pass_true_gives_passed_state(self):
        review = {
            "pass": True, "review_status": "completed",
            "issues": [], "summary": "ok",
        }
        outcome = engine.apply_policy(review, "report", "critical", False, "medium")
        assert outcome["state"] == "passed"

    def test_no_issues_passes(self):
        review = {
            "pass": True, "review_status": "completed",
            "issues": [], "summary": "ok",
        }
        outcome = engine.apply_policy(review, "block", "critical", False, "medium")
        assert outcome["action"] == "pass"
        assert outcome["state"] == "passed"


# ===========================================================================
# Confidence hard-filtering
# ===========================================================================

class TestConfidenceFilter:
    def test_filter_keeps_high_at_high_threshold(self):
        issues = [{"confidence": "high", "severity": "major"}]
        assert len(engine.filter_by_confidence(issues, "high")) == 1

    def test_filter_drops_medium_at_high_threshold(self):
        issues = [{"confidence": "medium", "severity": "major"}]
        assert len(engine.filter_by_confidence(issues, "high")) == 0

    def test_filter_drops_low_at_medium_threshold(self):
        issues = [{"confidence": "low", "severity": "critical"}]
        assert len(engine.filter_by_confidence(issues, "medium")) == 0

    def test_filter_keeps_all_at_low_threshold(self):
        issues = [
            {"confidence": "high", "severity": "major"},
            {"confidence": "medium", "severity": "major"},
            {"confidence": "low", "severity": "major"},
        ]
        assert len(engine.filter_by_confidence(issues, "low")) == 3

    def test_filter_default_confidence_is_medium(self):
        """Issues missing confidence field default to medium."""
        issues = [{"severity": "major"}]
        assert len(engine.filter_by_confidence(issues, "medium")) == 1
        assert len(engine.filter_by_confidence(issues, "high")) == 0

    def test_confidence_filter_affects_policy_block(self):
        """A critical+low issue should not block when confidence threshold is medium."""
        review = {
            "pass": False, "review_status": "completed",
            "issues": [{"severity": "critical", "confidence": "low",
                        "check": "x", "verdict": "y", "fix": "z"}],
            "summary": "test",
        }
        outcome = engine.apply_policy(review, "block", "critical", False, "medium")
        assert outcome["action"] == "pass"

    def test_confidence_filter_passes_high_through(self):
        """A critical+high issue should still block at medium confidence threshold."""
        review = {
            "pass": False, "review_status": "completed",
            "issues": [{"severity": "critical", "confidence": "high",
                        "check": "x", "verdict": "y", "fix": "z"}],
            "summary": "test",
        }
        outcome = engine.apply_policy(review, "block", "critical", False, "medium")
        assert outcome["action"] == "block"

    def test_mixed_confidence_filters_correctly(self):
        """Only high-confidence issues survive when threshold is high."""
        review = {
            "pass": False, "review_status": "completed",
            "issues": [
                {"severity": "critical", "confidence": "low", "check": "a", "verdict": "b", "fix": "c"},
                {"severity": "critical", "confidence": "high", "check": "x", "verdict": "y", "fix": "z"},
            ],
            "summary": "test",
        }
        outcome = engine.apply_policy(review, "block", "critical", False, "high")
        assert outcome["action"] == "block"
        # Only 1 issue should remain after filtering
        assert len(review["issues"]) == 2  # original unchanged
        # The filtered review in policy should have 1


# ===========================================================================
# Token budget & diff building
# ===========================================================================

class TestBuildDiff:
    def test_token_budget_truncation(self, tmp_path):
        # Create two files, budget only fits one
        f1 = tmp_path / "small.py"
        f1.write_text("x = 1\n" * 10)  # ~60 chars → ~15 tokens
        f2 = tmp_path / "big.py"
        f2.write_text("y = 2\n" * 1000)  # ~6000 chars → ~1500 tokens

        old_cwd = os.getcwd()
        os.chdir(tmp_path)
        try:
            diff, fc, tc, trunc, skipped = engine.build_diff(
                ["small.py", "big.py"], {"small.py", "big.py"}, max_tokens=100
            )
            # With 100 token budget, at least one file should be truncated or skipped
            assert trunc or "[truncated:" in diff
        finally:
            os.chdir(old_cwd)

    def test_skipped_files_recorded(self, tmp_path):
        f1 = tmp_path / "a.py"
        f1.write_text("a = 1\n")
        f2 = tmp_path / "b.py"
        f2.write_text("b = 2\n" * 500)
        f3 = tmp_path / "c.py"
        f3.write_text("c = 3\n")

        old_cwd = os.getcwd()
        os.chdir(tmp_path)
        try:
            diff, fc, tc, trunc, skipped = engine.build_diff(
                ["a.py", "b.py", "c.py"], {"a.py", "b.py", "c.py"}, max_tokens=50
            )
            # With tight budget, some files should be skipped
            assert len(skipped) > 0 or "[truncated:" in diff
        finally:
            os.chdir(old_cwd)


# ===========================================================================
# Binary detection
# ===========================================================================

class TestBinaryDetection:
    def test_text_file_not_binary(self, tmp_path):
        f = tmp_path / "hello.py"
        f.write_text("print('hello')\n")
        assert engine.is_binary(str(f)) is False

    def test_binary_file_detected(self, tmp_path):
        f = tmp_path / "image.png"
        f.write_bytes(b"\x89PNG\r\n\x1a\n\x00\x00\x00")
        assert engine.is_binary(str(f)) is True

    def test_nonexistent_file(self):
        assert engine.is_binary("/no/such/file") is False

    def test_binary_skipped_in_diff(self, tmp_path):
        f = tmp_path / "data.bin"
        f.write_bytes(b"\x00" * 100)

        old_cwd = os.getcwd()
        os.chdir(tmp_path)
        try:
            diff, fc, tc, trunc, skipped = engine.build_diff(
                ["data.bin"], {"data.bin"}, max_tokens=12000
            )
            assert any("binary" in s for s in skipped)
            assert fc == 0  # binary file not counted
        finally:
            os.chdir(old_cwd)


# ===========================================================================
# File filtering & ranking
# ===========================================================================

class TestFileFiltering:
    def test_filters_lockfiles(self):
        files = ["package-lock.json", "src/app.js", "yarn.lock"]
        result = engine.filter_file_list(files)
        assert result == ["src/app.js"]

    def test_filters_minified(self):
        files = ["dist/bundle.min.js", "src/index.ts"]
        result = engine.filter_file_list(files)
        assert result == ["src/index.ts"]

    def test_custom_ignore(self, tmp_path):
        ignore = tmp_path / ".cold-review-ignore"
        ignore.write_text("*.log\n*.bak\n")
        files = ["app.log", "src/main.py", "backup.bak"]
        result = engine.filter_file_list(files, str(ignore))
        assert result == ["src/main.py"]


class TestFileRanking:
    def test_risk_paths_first(self):
        files = ["README.md", "src/auth/login.py", "utils/format.js"]
        result = engine.rank_file_list(files, set())
        assert result[0] == "src/auth/login.py"

    def test_untracked_ranked_higher(self):
        files = ["old.py", "new.py"]
        result = engine.rank_file_list(files, {"new.py"})
        assert result[0] == "new.py"

    def test_multiple_factors_stack(self):
        files = ["README.md", "src/api/auth.py", "utils.py"]
        result = engine.rank_file_list(files, {"src/api/auth.py"})
        assert result[0] == "src/api/auth.py"


# ===========================================================================
# Prompt assembly (no profile)
# ===========================================================================

class TestBuildPrompt:
    def test_contains_cold_eyes(self):
        prompt = engine.build_prompt_text("English")
        assert "Cold Eyes" in prompt

    def test_no_stats_in_prompt(self):
        prompt = engine.build_prompt_text("English")
        assert "RIGOR" not in prompt
        assert "PARANOIA" not in prompt

    def test_language_substituted(self):
        prompt = engine.build_prompt_text("日本語")
        assert "日本語" in prompt

    def test_default_language(self):
        prompt = engine.build_prompt_text()
        assert "繁體中文" in prompt


# ===========================================================================
# FinalOutcome format
# ===========================================================================

class TestFinalOutcome:
    def test_outcome_has_required_keys(self):
        review = {"pass": True, "review_status": "completed", "issues": [], "summary": "ok"}
        outcome = engine.apply_policy(review, "block", "critical", False, "medium")
        for key in ("action", "state", "reason", "display"):
            assert key in outcome

    def test_block_outcome_has_reason(self):
        review = {
            "pass": False, "review_status": "completed",
            "issues": [{"severity": "critical", "confidence": "high",
                        "check": "x", "verdict": "y", "fix": "z"}],
            "summary": "bad",
        }
        outcome = engine.apply_policy(review, "block", "critical", False, "medium")
        assert outcome["reason"] != ""
        assert "Cold Eyes Review" in outcome["reason"]


# ===========================================================================
# History logging
# ===========================================================================

class TestHistory:
    def test_log_review_writes_v2(self, tmp_path):
        history = tmp_path / "history.jsonl"
        original = engine.HISTORY_FILE
        engine.HISTORY_FILE = str(history)
        try:
            review = {"pass": True, "review_status": "completed", "issues": [], "summary": "ok"}
            engine.log_to_history("/tmp", "block", "opus", "passed",
                                 review=review, file_count=3, line_count=100,
                                 truncated=False, token_count=800)
            lines = history.read_text().strip().split("\n")
            assert len(lines) == 1
            entry = json.loads(lines[0])
            assert entry["version"] == 2
            assert entry["state"] == "passed"
            assert entry["diff_stats"]["tokens"] == 800
            assert entry["review"]["pass"] is True
        finally:
            engine.HISTORY_FILE = original

    def test_log_state_writes_reason(self, tmp_path):
        history = tmp_path / "history.jsonl"
        original = engine.HISTORY_FILE
        engine.HISTORY_FILE = str(history)
        try:
            engine.log_to_history("/tmp", "block", "opus", "infra_failed",
                                 reason="claude exit 1")
            entry = json.loads(history.read_text().strip())
            assert entry["state"] == "infra_failed"
            assert entry["reason"] == "claude exit 1"
            assert entry["review"] is None
        finally:
            engine.HISTORY_FILE = original

    def test_log_review_includes_min_confidence(self, tmp_path):
        history = tmp_path / "history.jsonl"
        original = engine.HISTORY_FILE
        engine.HISTORY_FILE = str(history)
        try:
            review = {"pass": True, "review_status": "completed", "issues": [], "summary": "ok"}
            engine.log_to_history("/tmp", "block", "opus", "passed",
                                 review=review, file_count=3, line_count=100,
                                 truncated=False, token_count=800,
                                 min_confidence="high")
            entry = json.loads(history.read_text().strip())
            assert entry["min_confidence"] == "high"
        finally:
            engine.HISTORY_FILE = original

    def test_log_state_includes_min_confidence(self, tmp_path):
        history = tmp_path / "history.jsonl"
        original = engine.HISTORY_FILE
        engine.HISTORY_FILE = str(history)
        try:
            engine.log_to_history("/tmp", "block", "opus", "skipped",
                                 reason="no changes", min_confidence="low")
            entry = json.loads(history.read_text().strip())
            assert entry["min_confidence"] == "low"
        finally:
            engine.HISTORY_FILE = original


# ===========================================================================
# Truncation visibility in block messages
# ===========================================================================

class TestTruncationVisibility:
    def _review(self, severity="critical", confidence="high"):
        return {
            "pass": False, "review_status": "completed",
            "issues": [{"severity": severity, "confidence": confidence,
                        "check": "x", "verdict": "y", "fix": "z"}],
            "summary": "test",
        }

    def test_block_reason_includes_truncation_warning(self):
        review = self._review()
        reason = engine.format_block_reason(review, truncated=True, skipped_count=3)
        assert "\u5be9\u67e5\u4e0d\u5b8c\u6574" in reason
        assert "3" in reason

    def test_block_reason_no_warning_when_not_truncated(self):
        review = self._review()
        reason = engine.format_block_reason(review, truncated=False, skipped_count=0)
        assert "\u5be9\u67e5\u4e0d\u5b8c\u6574" not in reason

    def test_policy_passes_truncation_to_block_reason(self):
        review = self._review()
        outcome = engine.apply_policy(
            review, "block", "critical", False, "medium",
            truncated=True, skipped_files=["a.py", "b.py"]
        )
        assert outcome["action"] == "block"
        assert "\u5be9\u67e5\u4e0d\u5b8c\u6574" in outcome["reason"]
        assert "2" in outcome["reason"]

    def test_outcome_includes_truncation_fields(self):
        review = self._review()
        outcome = engine.apply_policy(
            review, "block", "critical", False, "medium",
            truncated=True, skipped_files=["a.py"]
        )
        assert outcome["truncated"] is True
        assert outcome["skipped_count"] == 1

    def test_outcome_no_truncation_by_default(self):
        review = {"pass": True, "review_status": "completed", "issues": [], "summary": "ok"}
        outcome = engine.apply_policy(review, "block", "critical", False, "medium")
        assert outcome["truncated"] is False
        assert outcome["skipped_count"] == 0
