"""Tests for cold_eyes package — policy, parsing, diff building, binary detection."""

import json
import os
import sys
import tempfile

import pytest

# ---------------------------------------------------------------------------
# Import from cold_eyes package
# ---------------------------------------------------------------------------

from cold_eyes import constants
from cold_eyes.constants import (
    STATE_PASSED, STATE_BLOCKED, STATE_OVERRIDDEN, STATE_SKIPPED,
    STATE_INFRA_FAILED, STATE_REPORTED,
)
from cold_eyes import engine as _engine_mod
from cold_eyes import git as _git_mod
from cold_eyes.review import parse_review_output
from cold_eyes.policy import apply_policy, filter_by_confidence, format_block_reason
from cold_eyes.filter import filter_file_list, rank_file_list
from cold_eyes.git import build_diff, is_binary, collect_files, git_cmd, GitCommandError, ConfigError
from cold_eyes.prompt import build_prompt_text
from cold_eyes.history import log_to_history, aggregate_overrides, compute_stats, prune_history, archive_history, quality_report
from cold_eyes.config import load_policy, _parse_flat_yaml, POLICY_FILENAME
from cold_eyes.claude import (
    ModelAdapter, ClaudeCliAdapter, MockAdapter, ReviewInvocation,
)
from cold_eyes.doctor import run_doctor


# Compatibility shim: tests reference `engine.X` throughout
class _EngineCompat:
    """Proxy that exposes all functions from the package as engine.X."""
    SCHEMA_VERSION = constants.SCHEMA_VERSION
    SEVERITY_ORDER = constants.SEVERITY_ORDER
    CONFIDENCE_ORDER = constants.CONFIDENCE_ORDER
    BUILTIN_IGNORE = constants.BUILTIN_IGNORE
    RISK_PATTERN = constants.RISK_PATTERN
    DEPLOY_FILES = constants.DEPLOY_FILES
    HISTORY_FILE = constants.HISTORY_FILE

    parse_review_output = staticmethod(parse_review_output)
    apply_policy = staticmethod(apply_policy)
    filter_by_confidence = staticmethod(filter_by_confidence)
    format_block_reason = staticmethod(format_block_reason)
    filter_file_list = staticmethod(filter_file_list)
    rank_file_list = staticmethod(rank_file_list)
    build_diff = staticmethod(build_diff)
    is_binary = staticmethod(is_binary)
    collect_files = staticmethod(collect_files)
    git_cmd = staticmethod(git_cmd)
    build_prompt_text = staticmethod(build_prompt_text)
    log_to_history = staticmethod(log_to_history)
    aggregate_overrides = staticmethod(aggregate_overrides)
    compute_stats = staticmethod(compute_stats)
    load_policy = staticmethod(load_policy)
    run_doctor = staticmethod(run_doctor)
    _infra_review = staticmethod(_engine_mod._infra_review)

engine = _EngineCompat()


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
        assert r["pass"] is False  # corrected: major issue forces pass=false
        issue = r["issues"][0]
        assert issue["severity"] == "major"
        assert issue["confidence"] == "medium"
        assert issue["category"] == "correctness"
        assert issue["file"] == "unknown"

    def test_empty_result_field(self):
        raw = json.dumps({"type": "result", "result": ""})
        r = engine.parse_review_output(raw)
        assert r["review_status"] == "failed"

    def test_system_init_preamble_before_result(self):
        # Regression: claude CLI sometimes emits {"type":"system","subtype":"init",...}
        # before the actual result JSON.  json.loads then fails with
        # "Extra data: line 3 column 1 (char N)".  We must extract the result object.
        init = json.dumps({
            "type": "system", "subtype": "init",
            "cwd": "/x", "session_id": "abc", "model": "sonnet",
        })
        payload = json.dumps({"pass": False, "issues": [], "summary": "found"})
        result = json.dumps({
            "type": "result", "subtype": "success", "result": payload,
        })
        raw = init + "\n" + result
        r = engine.parse_review_output(raw)
        assert r["review_status"] == "completed"
        assert r["summary"] == "found"
        assert r["pass"] is False

    def test_multiple_preambles_before_result(self):
        # Defense in depth: even with several system messages, the result wins.
        init = json.dumps({"type": "system", "subtype": "init"})
        status = json.dumps({"type": "system", "subtype": "status"})
        payload = json.dumps({"pass": True, "issues": [], "summary": "ok"})
        result = json.dumps({
            "type": "result", "subtype": "success", "result": payload,
        })
        raw = "\n".join([init, status, result])
        r = engine.parse_review_output(raw)
        assert r["review_status"] == "completed"
        assert r["summary"] == "ok"

    def test_natural_language_preamble_inside_result_string(self):
        # Regression: sonnet sometimes narrates before emitting the JSON
        # inside the "result" string, e.g.
        #   "正在審查這批副標題改寫。\n\n{...JSON...}"
        # Previously json.loads(cleaned) failed at char 0 because the string
        # starts with prose, and the whole review was lost as infra_failed.
        payload_json = json.dumps(
            {"pass": False, "issues": [], "summary": "caught"},
            ensure_ascii=False,
        )
        result_str = "正在審查這批副標題改寫。\n\n" + payload_json
        raw = json.dumps({"type": "result", "result": result_str})
        r = engine.parse_review_output(raw)
        assert r["review_status"] == "completed"
        assert r["summary"] == "caught"
        assert r["pass"] is False

    def test_trailing_narration_after_embedded_json(self):
        # raw_decode stops cleanly at end of JSON; trailing prose is ignored.
        payload_json = json.dumps({"pass": True, "issues": [], "summary": "x"})
        result_str = payload_json + "\n\n結論：看起來沒問題。"
        raw = json.dumps({"type": "result", "result": result_str})
        r = engine.parse_review_output(raw)
        assert r["summary"] == "x"
        assert r["pass"] is True

    def test_narration_both_sides_picks_review_shaped_object(self):
        # If the LLM emits multiple {}-looking runs, pick the one with
        # review-result keys.
        noise = json.dumps({"unrelated": "object"})
        payload = json.dumps({"pass": True, "issues": [], "summary": "right one"})
        result_str = f"開場白 {noise} 中段 {payload} 結尾備註"
        raw = json.dumps({"type": "result", "result": result_str})
        r = engine.parse_review_output(raw)
        assert r["summary"] == "right one"

    def test_no_extractable_json_falls_to_parse_error(self):
        # Pure prose with no {} — infra_failed with a helpful summary.
        raw = json.dumps({"type": "result", "result": "抱歉無法完成審查。"})
        r = engine.parse_review_output(raw)
        assert r["review_status"] == "failed"
        assert "no JSON object found" in r["summary"]


# ===========================================================================
# apply_policy — infrastructure failure
# ===========================================================================

class TestApplyPolicyInfraFailure:
    def _infra_review(self, summary="parse error"):
        return {
            "pass": True, "review_status": "failed",
            "issues": [], "summary": summary,
        }

    def test_block_mode_passes_on_infra_failure(self):
        # Infra failures no longer block the user — reviewer bugs are our
        # problem, not a canon violation.
        outcome = engine.apply_policy(self._infra_review(), "block", "critical", False, "medium")
        assert outcome["action"] == "pass"
        assert outcome["state"] == STATE_INFRA_FAILED

    def test_report_mode_passes_on_infra_failure(self):
        outcome = engine.apply_policy(self._infra_review(), "report", "critical", False, "medium")
        assert outcome["action"] == "pass"
        assert outcome["state"] == STATE_INFRA_FAILED

    def test_override_flag_no_longer_affects_infra(self):
        # allow_once used to convert infra block → OVERRIDDEN; now infra
        # never blocks, so allow_once has no effect on the outcome.
        outcome = engine.apply_policy(self._infra_review(), "block", "critical", True, "medium")
        assert outcome["action"] == "pass"
        assert outcome["state"] == STATE_INFRA_FAILED

    def test_infra_failure_surfaces_error_detail(self):
        outcome = engine.apply_policy(
            self._infra_review("claude exit 1"), "block", "critical", False, "medium"
        )
        assert "claude exit 1" in outcome["reason"]
        assert "claude exit 1" in outcome["display"]


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
        assert outcome["state"] == STATE_BLOCKED

    def test_major_does_not_block_at_critical_threshold(self):
        outcome = engine.apply_policy(self._review("major"), "block", "critical", False, "medium")
        assert outcome["action"] == "pass"
        assert outcome["state"] == STATE_PASSED

    def test_major_blocks_at_major_threshold(self):
        outcome = engine.apply_policy(self._review("major"), "block", "major", False, "medium")
        assert outcome["action"] == "block"
        assert outcome["state"] == STATE_BLOCKED

    def test_minor_never_blocks(self):
        outcome = engine.apply_policy(self._review("minor"), "block", "critical", False, "medium")
        assert outcome["action"] == "pass"
        outcome = engine.apply_policy(self._review("minor"), "block", "major", False, "medium")
        assert outcome["action"] == "pass"

    def test_override_skips_block(self):
        outcome = engine.apply_policy(self._review("critical"), "block", "critical", True, "medium")
        assert outcome["action"] == "pass"
        assert outcome["state"] == STATE_OVERRIDDEN

    def test_report_mode_never_blocks(self):
        outcome = engine.apply_policy(self._review("critical"), "report", "critical", False, "medium")
        assert outcome["action"] == "pass"
        assert outcome["state"] == STATE_REPORTED

    def test_report_mode_pass_true_gives_passed_state(self):
        review = {
            "pass": True, "review_status": "completed",
            "issues": [], "summary": "ok",
        }
        outcome = engine.apply_policy(review, "report", "critical", False, "medium")
        assert outcome["state"] == STATE_PASSED

    def test_no_issues_passes(self):
        review = {
            "pass": True, "review_status": "completed",
            "issues": [], "summary": "ok",
        }
        outcome = engine.apply_policy(review, "block", "critical", False, "medium")
        assert outcome["action"] == "pass"
        assert outcome["state"] == STATE_PASSED


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
                {"severity": "critical", "confidence": "high", "check": "x", "verdict": "y", "fix": "z",
                 "evidence": ["line 5 uses eval()"]},
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
            meta = engine.build_diff(
                ["small.py", "big.py"], {"small.py", "big.py"}, max_tokens=100
            )
            assert meta["truncated"] or "[truncated:" in meta["diff_text"]
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
            meta = engine.build_diff(
                ["a.py", "b.py", "c.py"], {"a.py", "b.py", "c.py"}, max_tokens=50
            )
            all_skipped = (meta["partial_files"] + meta["skipped_budget"]
                           + meta["skipped_binary"] + meta["skipped_unreadable"])
            assert len(all_skipped) > 0 or "[truncated:" in meta["diff_text"]
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
            meta = engine.build_diff(
                ["data.bin"], {"data.bin"}, max_tokens=12000
            )
            assert "data.bin" in meta["skipped_binary"]
            assert meta["file_count"] == 0
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
    def test_log_review_writes_history_schema_v2(self, tmp_path):
        history = tmp_path / "history.jsonl"
        original = engine.HISTORY_FILE
        constants.HISTORY_FILE = str(history)
        try:
            review = {"pass": True, "review_status": "completed", "issues": [], "summary": "ok"}
            engine.log_to_history("/tmp", "block", "opus", STATE_PASSED,
                                 review=review, file_count=3, line_count=100,
                                 truncated=False, token_count=800)
            lines = history.read_text().strip().split("\n")
            assert len(lines) == 1
            entry = json.loads(lines[0])
            assert entry["version"] == 2
            assert entry["state"] == STATE_PASSED
            assert entry["diff_stats"]["tokens"] == 800
            assert entry["review"]["pass"] is True
        finally:
            engine.HISTORY_FILE = original

    def test_log_state_writes_reason(self, tmp_path):
        history = tmp_path / "history.jsonl"
        original = engine.HISTORY_FILE
        constants.HISTORY_FILE = str(history)
        try:
            engine.log_to_history("/tmp", "block", "opus", STATE_INFRA_FAILED,
                                 reason="claude exit 1")
            entry = json.loads(history.read_text().strip())
            assert entry["state"] == STATE_INFRA_FAILED
            assert entry["reason"] == "claude exit 1"
            assert entry["review"] is None
        finally:
            engine.HISTORY_FILE = original

    def test_log_review_includes_min_confidence(self, tmp_path):
        history = tmp_path / "history.jsonl"
        original = engine.HISTORY_FILE
        constants.HISTORY_FILE = str(history)
        try:
            review = {"pass": True, "review_status": "completed", "issues": [], "summary": "ok"}
            engine.log_to_history("/tmp", "block", "opus", STATE_PASSED,
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
        constants.HISTORY_FILE = str(history)
        try:
            engine.log_to_history("/tmp", "block", "opus", STATE_SKIPPED,
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


# ---------------------------------------------------------------------------
# Doctor
# ---------------------------------------------------------------------------

class TestDoctor:

    def test_returns_required_keys(self, tmp_path):
        result = engine.run_doctor(
            scripts_dir=str(tmp_path), settings_path=str(tmp_path / "none.json")
        )
        assert result["action"] == "doctor"
        assert isinstance(result["checks"], list)
        assert isinstance(result["all_ok"], bool)

    def test_checks_have_required_fields(self, tmp_path):
        result = engine.run_doctor(
            scripts_dir=str(tmp_path), settings_path=str(tmp_path / "none.json")
        )
        for check in result["checks"]:
            assert "name" in check
            assert "status" in check
            assert "detail" in check
            assert check["status"] in ("ok", "fail", "info")

    def test_python_check_ok(self, tmp_path):
        result = engine.run_doctor(
            scripts_dir=str(tmp_path), settings_path=str(tmp_path / "none.json")
        )
        py = next(c for c in result["checks"] if c["name"] == "python")
        assert py["status"] == "ok"
        assert str(sys.version_info.major) in py["detail"]

    def test_git_check_ok(self, tmp_path):
        result = engine.run_doctor(
            scripts_dir=str(tmp_path), settings_path=str(tmp_path / "none.json")
        )
        git = next(c for c in result["checks"] if c["name"] == "git")
        assert git["status"] == "ok"

    def test_deploy_files_missing(self, tmp_path):
        result = engine.run_doctor(
            scripts_dir=str(tmp_path), settings_path=str(tmp_path / "none.json")
        )
        deploy = next(c for c in result["checks"] if c["name"] == "deploy_files")
        assert deploy["status"] == "fail"
        assert "missing" in deploy["detail"]

    def test_deploy_files_present(self, tmp_path):
        for f in engine.DEPLOY_FILES:
            p = tmp_path / f
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text("x")
        result = engine.run_doctor(
            scripts_dir=str(tmp_path), settings_path=str(tmp_path / "none.json")
        )
        deploy = next(c for c in result["checks"] if c["name"] == "deploy_files")
        assert deploy["status"] == "ok"

    def test_settings_json_missing(self, tmp_path):
        result = engine.run_doctor(
            scripts_dir=str(tmp_path),
            settings_path=str(tmp_path / "nonexistent.json")
        )
        hook = next(c for c in result["checks"] if c["name"] == "settings_hook")
        assert hook["status"] == "fail"

    def test_settings_json_no_hook(self, tmp_path):
        settings = tmp_path / "settings.json"
        settings.write_text(json.dumps({"hooks": {"Stop": []}}))
        result = engine.run_doctor(
            scripts_dir=str(tmp_path), settings_path=str(settings)
        )
        hook = next(c for c in result["checks"] if c["name"] == "settings_hook")
        assert hook["status"] == "fail"

    def test_settings_json_with_hook(self, tmp_path):
        settings = tmp_path / "settings.json"
        settings.write_text(json.dumps({
            "hooks": {"Stop": [{"hooks": [
                {"command": "bash /home/user/.claude/scripts/cold-review.sh"}
            ]}]}
        }))
        result = engine.run_doctor(
            scripts_dir=str(tmp_path), settings_path=str(settings)
        )
        hook = next(c for c in result["checks"] if c["name"] == "settings_hook")
        assert hook["status"] == "ok"

    def test_ignore_file_info_when_missing(self, tmp_path):
        result = engine.run_doctor(
            scripts_dir=str(tmp_path), settings_path=str(tmp_path / "none.json"),
            repo_root=str(tmp_path)
        )
        ignore = next(c for c in result["checks"] if c["name"] == "ignore_file")
        assert ignore["status"] == "info"

    def test_all_ok_false_when_deploy_missing(self, tmp_path):
        result = engine.run_doctor(
            scripts_dir=str(tmp_path), settings_path=str(tmp_path / "none.json")
        )
        assert result["all_ok"] is False

    def test_legacy_helper_detected(self, tmp_path):
        (tmp_path / "cold-review-helper.py").write_text("legacy")
        result = engine.run_doctor(
            scripts_dir=str(tmp_path), settings_path=str(tmp_path / "none.json")
        )
        helper = next(c for c in result["checks"] if c["name"] == "legacy_helper")
        assert helper["status"] == "fail"
        assert "split-brain" in helper["detail"]

    def test_no_legacy_helper_ok(self, tmp_path):
        result = engine.run_doctor(
            scripts_dir=str(tmp_path), settings_path=str(tmp_path / "none.json")
        )
        helper = next(c for c in result["checks"] if c["name"] == "legacy_helper")
        assert helper["status"] == "ok"

    def test_shell_with_legacy_patterns_detected(self, tmp_path):
        (tmp_path / "cold-review.sh").write_text('HELPER="cold-review-helper.py"')
        result = engine.run_doctor(
            scripts_dir=str(tmp_path), settings_path=str(tmp_path / "none.json")
        )
        sv = next(c for c in result["checks"] if c["name"] == "shell_version")
        assert sv["status"] == "fail"

    def test_clean_shell_ok(self, tmp_path):
        (tmp_path / "cold-review.sh").write_text('#!/bin/bash\npython cli.py run')
        result = engine.run_doctor(
            scripts_dir=str(tmp_path), settings_path=str(tmp_path / "none.json")
        )
        sv = next(c for c in result["checks"] if c["name"] == "shell_version")
        assert sv["status"] == "ok"


# ---------------------------------------------------------------------------
# Scope
# ---------------------------------------------------------------------------

class TestCollectFilesScope:

    def test_engine_default_scope_is_staged(self, monkeypatch, tmp_path):
        scopes = []

        monkeypatch.delenv("COLD_REVIEW_SCOPE", raising=False)
        monkeypatch.setattr(_engine_mod, "git_cmd", lambda *args: str(tmp_path))
        monkeypatch.setattr(_engine_mod, "load_policy", lambda repo_root: {})
        monkeypatch.setattr(constants, "HISTORY_FILE", str(tmp_path / "history.jsonl"))

        def fake_collect(scope, base=None):
            scopes.append(scope)
            return [], set()

        monkeypatch.setattr(_engine_mod, "collect_files", fake_collect)
        result = _engine_mod.run(adapter=MockAdapter())

        assert result["state"] == STATE_SKIPPED
        assert scopes == ["staged"]

    def test_default_scope_is_staged(self, monkeypatch):
        calls = []
        original = _git_mod.git_cmd

        def spy(*args):
            calls.append(args)
            return original(*args)

        monkeypatch.setattr(_git_mod, "git_cmd", spy)
        engine.collect_files()
        assert calls == [("diff", "--cached", "--name-only")]

    def test_staged_scope_no_untracked(self, monkeypatch):
        calls = []

        def spy(*args):
            calls.append(args)
            return ""

        monkeypatch.setattr(_git_mod, "git_cmd", spy)
        files, untracked = engine.collect_files("staged")
        assert untracked == set()
        # Should only call diff --cached
        assert all(
            "ls-files" not in c for c in calls
        )

    def test_head_scope_no_untracked(self, monkeypatch):
        calls = []

        def spy(*args):
            calls.append(args)
            return ""

        monkeypatch.setattr(_git_mod, "git_cmd", spy)
        files, untracked = engine.collect_files("head")
        assert untracked == set()

    def test_pr_diff_scope_uses_triple_dot(self, monkeypatch):
        calls = []

        def spy(*args):
            calls.append(args)
            if "main...HEAD" in args:
                return "file1.py\nfile2.py"
            return ""

        monkeypatch.setattr(_git_mod, "git_cmd", spy)
        files, untracked = engine.collect_files("pr-diff", base="main")
        assert files == ["file1.py", "file2.py"]
        assert untracked == set()
        assert any("main...HEAD" in c for c in calls)

    def test_pr_diff_no_base_raises_config_error(self):
        with pytest.raises(ConfigError, match="pr-diff scope requires --base"):
            engine.collect_files("pr-diff")

    def test_pr_diff_empty_base_raises_config_error(self):
        with pytest.raises(ConfigError, match="pr-diff scope requires --base"):
            engine.collect_files("pr-diff", base="")

    def test_pr_diff_invalid_base_raises_git_error(self, monkeypatch):
        def raise_on_diff(*args):
            if "nonexistent...HEAD" in args:
                raise GitCommandError(list(args), 128, "unknown revision")
            return ""
        monkeypatch.setattr(_git_mod, "git_cmd", raise_on_diff)
        with pytest.raises(GitCommandError):
            engine.collect_files("pr-diff", base="nonexistent")


class TestBuildDiffScope:

    def test_staged_scope_uses_cached_only(self, monkeypatch):
        calls = []

        def mock_git(*args):
            calls.append(args)
            if args[0] == "diff" and "--cached" in args:
                return "diff --git a/x.py\n+added"
            return ""

        monkeypatch.setattr(_git_mod, "git_cmd", mock_git)
        meta = engine.build_diff(["x.py"], set(), 12000, scope="staged")
        diff_calls = [c for c in calls if c[0] == "diff"]
        for c in diff_calls:
            assert "--cached" in c

    def test_head_scope_uses_head(self, monkeypatch):
        calls = []

        def mock_git(*args):
            calls.append(args)
            if args[0] == "diff" and "HEAD" in args:
                return "diff --git a/x.py\n+added"
            return ""

        monkeypatch.setattr(_git_mod, "git_cmd", mock_git)
        meta = engine.build_diff(["x.py"], set(), 12000, scope="head")
        diff_calls = [c for c in calls if c[0] == "diff"]
        for c in diff_calls:
            assert "HEAD" in c

    def test_working_scope_uses_both(self, monkeypatch):
        calls = []

        def mock_git(*args):
            calls.append(args)
            return "some diff"

        monkeypatch.setattr(_git_mod, "git_cmd", mock_git)
        engine.build_diff(["x.py"], set(), 12000, scope="working")
        diff_calls = [c for c in calls if c[0] == "diff"]
        has_cached = any("--cached" in c for c in diff_calls)
        has_bare = any("--cached" not in c and "HEAD" not in c for c in diff_calls)
        assert has_cached
        assert has_bare

    def test_pr_diff_scope_uses_base(self, monkeypatch):
        calls = []

        def mock_git(*args):
            calls.append(args)
            if "main...HEAD" in args:
                return "diff --git a/x.py\n+pr change"
            return ""

        monkeypatch.setattr(_git_mod, "git_cmd", mock_git)
        meta = engine.build_diff(
            ["x.py"], set(), 12000, scope="pr-diff", base="main"
        )
        diff_calls = [c for c in calls if c[0] == "diff"]
        assert any("main...HEAD" in c for c in diff_calls)
        assert "pr change" in meta["diff_text"]


class TestHistoryScope:

    def test_log_history_includes_scope(self, tmp_path):
        history = tmp_path / "history.jsonl"
        constants.HISTORY_FILE = str(history)
        engine.log_to_history("/tmp", "block", "opus", STATE_PASSED,
                              min_confidence="medium", scope="staged")
        entry = json.loads(history.read_text().strip())
        assert entry["scope"] == "staged"

    def test_log_history_default_scope(self, tmp_path):
        history = tmp_path / "history.jsonl"
        constants.HISTORY_FILE = str(history)
        engine.log_to_history("/tmp", "block", "opus", STATE_PASSED)
        entry = json.loads(history.read_text().strip())
        assert entry["scope"] == "staged"


# ---------------------------------------------------------------------------
# line_hint
# ---------------------------------------------------------------------------

class TestLineHint:

    def test_parse_default_empty_string(self):
        raw = json.dumps({
            "type": "result", "subtype": "success",
            "result": json.dumps({
                "pass": False, "issues": [{"check": "x", "severity": "critical"}],
                "summary": "bug"
            })
        })
        r = engine.parse_review_output(raw)
        assert r["issues"][0]["line_hint"] == ""

    def test_parse_preserves_line_hint(self):
        raw = json.dumps({
            "type": "result", "subtype": "success",
            "result": json.dumps({
                "pass": False,
                "issues": [{"check": "x", "severity": "critical", "line_hint": "L42"}],
                "summary": "bug"
            })
        })
        r = engine.parse_review_output(raw)
        assert r["issues"][0]["line_hint"] == "L42"

    def test_block_reason_includes_line_hint(self):
        review = {
            "summary": "test",
            "issues": [{"severity": "critical", "line_hint": "L42",
                        "check": "bad", "verdict": "wrong", "fix": "fix it"}]
        }
        reason = engine.format_block_reason(review)
        assert "(~L42)" in reason
        assert "[CRITICAL]" in reason

    def test_block_reason_no_parens_when_empty(self):
        review = {
            "summary": "test",
            "issues": [{"severity": "critical", "line_hint": "",
                        "check": "bad", "verdict": "wrong", "fix": "fix it"}]
        }
        reason = engine.format_block_reason(review)
        assert "()" not in reason
        assert "[CRITICAL]" in reason


# ---------------------------------------------------------------------------
# schema_version
# ---------------------------------------------------------------------------

class TestSchemaVersion:

    def test_parse_sets_default(self):
        raw = json.dumps({
            "type": "result", "subtype": "success",
            "result": json.dumps({"pass": True, "issues": [], "summary": "ok"})
        })
        r = engine.parse_review_output(raw)
        assert r["schema_version"] == engine.SCHEMA_VERSION

    def test_parse_preserves_explicit(self):
        raw = json.dumps({
            "type": "result", "subtype": "success",
            "result": json.dumps({
                "schema_version": 1, "pass": True, "issues": [], "summary": "ok"
            })
        })
        r = engine.parse_review_output(raw)
        assert r["schema_version"] == 1

    def test_parse_failure_includes_schema_version(self):
        r = engine.parse_review_output("not json")
        assert r["schema_version"] == engine.SCHEMA_VERSION

    def test_infra_review_includes_schema_version(self):
        r = engine._infra_review("timeout")
        assert r["schema_version"] == engine.SCHEMA_VERSION

    def test_history_includes_schema_version(self, tmp_path):
        history = tmp_path / "history.jsonl"
        constants.HISTORY_FILE = str(history)
        review = {"schema_version": 1, "pass": True, "review_status": "completed",
                  "issues": [], "summary": "ok"}
        engine.log_to_history("/tmp", "block", "opus", STATE_PASSED, review=review)
        entry = json.loads(history.read_text().strip())
        assert entry["schema_version"] == 1

    def test_history_state_log_includes_schema_version(self, tmp_path):
        history = tmp_path / "history.jsonl"
        constants.HISTORY_FILE = str(history)
        engine.log_to_history("/tmp", "block", "opus", STATE_SKIPPED, reason="no changes")
        entry = json.loads(history.read_text().strip())
        assert entry["schema_version"] == engine.SCHEMA_VERSION


# ===========================================================================
# override_reason
# ===========================================================================

class TestOverrideReason:

    def _review(self, severity="critical", confidence="high"):
        return {
            "pass": False, "review_status": "completed",
            "issues": [{"severity": severity, "confidence": confidence,
                        "check": "x", "verdict": "y", "fix": "z"}],
            "summary": "test",
        }

    def _infra_review(self):
        return {"pass": True, "review_status": "failed",
                "issues": [], "summary": "parse error"}

    # -- override paths --

    def test_override_with_reason_records_reason(self):
        outcome = engine.apply_policy(
            self._review(), "block", "critical", True, "medium",
            override_reason="false_positive")
        assert outcome["reason"] == "false_positive"

    def test_override_without_reason_empty(self):
        outcome = engine.apply_policy(
            self._review(), "block", "critical", True, "medium")
        assert outcome["reason"] == ""

    def test_override_reason_in_display(self):
        outcome = engine.apply_policy(
            self._review(), "block", "critical", True, "medium",
            override_reason="false_positive")
        assert "[false_positive]" in outcome["display"]

    def test_override_empty_reason_no_brackets(self):
        outcome = engine.apply_policy(
            self._review(), "block", "critical", True, "medium")
        assert "[" not in outcome["display"]

    def test_infra_does_not_consume_override(self):
        # Infra failures no longer block, so arming an override for them is
        # a no-op. The override_reason does not appear in the outcome.
        outcome = engine.apply_policy(
            self._infra_review(), "block", "critical", True, "medium",
            override_reason="infrastructure")
        assert outcome["action"] == "pass"
        assert outcome["state"] == STATE_INFRA_FAILED
        assert "[infrastructure]" not in outcome["display"]

    # -- block paths --

    def test_block_includes_override_hint(self):
        outcome = engine.apply_policy(
            self._review(), "block", "critical", False, "medium")
        assert "arm-override" in outcome["reason"]

    def test_infra_failure_does_not_emit_override_hint(self):
        # Infra failures pass rather than block, so no override hint is needed.
        outcome = engine.apply_policy(
            self._infra_review(), "block", "critical", False, "medium")
        assert "arm-override" not in outcome["reason"]
        assert outcome["action"] == "pass"

    def test_pass_no_override_hint(self):
        review = {"pass": True, "review_status": "completed",
                  "issues": [], "summary": "ok"}
        outcome = engine.apply_policy(review, "block", "critical", False, "medium")
        assert "arm-override" not in outcome["reason"]


class TestHistoryOverrideReason:

    def test_log_with_override_reason(self, tmp_path):
        history = tmp_path / "history.jsonl"
        constants.HISTORY_FILE = str(history)
        engine.log_to_history("/tmp", "block", "opus", STATE_OVERRIDDEN,
                              override_reason="false_positive")
        entry = json.loads(history.read_text().strip())
        assert entry["override_reason"] == "false_positive"

    def test_log_without_override_reason(self, tmp_path):
        history = tmp_path / "history.jsonl"
        constants.HISTORY_FILE = str(history)
        engine.log_to_history("/tmp", "block", "opus", STATE_PASSED)
        entry = json.loads(history.read_text().strip())
        assert "override_reason" not in entry

    def test_log_empty_override_reason_not_written(self, tmp_path):
        history = tmp_path / "history.jsonl"
        constants.HISTORY_FILE = str(history)
        engine.log_to_history("/tmp", "block", "opus", STATE_OVERRIDDEN,
                              override_reason="")
        entry = json.loads(history.read_text().strip())
        assert "override_reason" not in entry


class TestAggregateOverrides:

    def _write_entry(self, path, state, override_reason=None):
        entry = {"version": 2, "state": state, "mode": "block", "model": "opus"}
        if override_reason is not None:
            entry["override_reason"] = override_reason
        with open(path, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry) + "\n")

    def test_empty_history(self, tmp_path):
        history = tmp_path / "history.jsonl"
        history.write_text("")
        result = engine.aggregate_overrides(str(history))
        assert result["total_overrides"] == 0
        assert result["reasons"] == []
        assert result["recent"] == []

    def test_counts_overrides(self, tmp_path):
        history = tmp_path / "history.jsonl"
        self._write_entry(str(history), STATE_OVERRIDDEN, "false_positive")
        self._write_entry(str(history), STATE_PASSED)
        self._write_entry(str(history), STATE_OVERRIDDEN, "acceptable_risk")
        result = engine.aggregate_overrides(str(history))
        assert result["total_overrides"] == 2

    def test_groups_by_reason(self, tmp_path):
        history = tmp_path / "history.jsonl"
        self._write_entry(str(history), STATE_OVERRIDDEN, "false_positive")
        self._write_entry(str(history), STATE_OVERRIDDEN, "false_positive")
        self._write_entry(str(history), STATE_OVERRIDDEN, "acceptable_risk")
        result = engine.aggregate_overrides(str(history))
        assert result["reasons"][0] == {"reason": "false_positive", "count": 2}
        assert result["reasons"][1] == {"reason": "acceptable_risk", "count": 1}


class TestComputeStats:

    def _write_entry(self, path, state, cwd="/repo/a", timestamp=None,
                     override_reason=None):
        from datetime import datetime, timezone
        entry = {
            "version": 2,
            "timestamp": timestamp or datetime.now(timezone.utc).strftime(
                "%Y-%m-%dT%H:%M:%SZ"),
            "cwd": cwd,
            "state": state,
            "mode": "block",
            "model": "opus",
        }
        if override_reason is not None:
            entry["override_reason"] = override_reason
        with open(path, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry) + "\n")

    def test_empty_history(self, tmp_path):
        h = tmp_path / "history.jsonl"
        h.write_text("")
        result = engine.compute_stats(str(h))
        assert result["action"] == "stats"
        assert result["total"] == 0
        assert result["by_state"] == {}
        assert result["period"] == "all"

    def test_nonexistent_file(self, tmp_path):
        result = engine.compute_stats(str(tmp_path / "nope.jsonl"))
        assert result["total"] == 0

    def test_state_counts(self, tmp_path):
        h = str(tmp_path / "history.jsonl")
        self._write_entry(h, STATE_PASSED)
        self._write_entry(h, STATE_PASSED)
        self._write_entry(h, STATE_BLOCKED)
        self._write_entry(h, STATE_OVERRIDDEN, override_reason="fp")
        self._write_entry(h, STATE_SKIPPED)
        self._write_entry(h, STATE_INFRA_FAILED)
        result = engine.compute_stats(h)
        assert result["total"] == 6
        assert result["by_state"][STATE_PASSED] == 2
        assert result["by_state"][STATE_BLOCKED] == 1
        assert result["by_state"][STATE_OVERRIDDEN] == 1
        assert result["by_state"][STATE_SKIPPED] == 1
        assert result["by_state"][STATE_INFRA_FAILED] == 1

    def test_time_filter_last(self, tmp_path):
        from datetime import datetime, timezone, timedelta
        h = str(tmp_path / "history.jsonl")
        old = (datetime.now(timezone.utc) - timedelta(days=10)).strftime(
            "%Y-%m-%dT%H:%M:%SZ")
        recent = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        self._write_entry(h, STATE_PASSED, timestamp=old)
        self._write_entry(h, STATE_BLOCKED, timestamp=recent)
        result = engine.compute_stats(h, last="7d")
        assert result["total"] == 1
        assert result["by_state"][STATE_BLOCKED] == 1
        assert result["period"] == "last 7d"

    def test_time_filter_hours(self, tmp_path):
        from datetime import datetime, timezone, timedelta
        h = str(tmp_path / "history.jsonl")
        old = (datetime.now(timezone.utc) - timedelta(hours=48)).strftime(
            "%Y-%m-%dT%H:%M:%SZ")
        recent = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        self._write_entry(h, STATE_PASSED, timestamp=old)
        self._write_entry(h, STATE_BLOCKED, timestamp=recent)
        result = engine.compute_stats(h, last="24h")
        assert result["total"] == 1

    def test_time_filter_weeks(self, tmp_path):
        from datetime import datetime, timezone, timedelta
        h = str(tmp_path / "history.jsonl")
        old = (datetime.now(timezone.utc) - timedelta(weeks=3)).strftime(
            "%Y-%m-%dT%H:%M:%SZ")
        recent = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        self._write_entry(h, STATE_PASSED, timestamp=old)
        self._write_entry(h, STATE_BLOCKED, timestamp=recent)
        result = engine.compute_stats(h, last="2w")
        assert result["total"] == 1

    def test_invalid_last_ignored(self, tmp_path):
        h = str(tmp_path / "history.jsonl")
        self._write_entry(h, STATE_PASSED)
        self._write_entry(h, STATE_BLOCKED)
        result = engine.compute_stats(h, last="xyz")
        assert result["total"] == 2
        assert result["period"] == "all"

    def test_by_reason(self, tmp_path):
        h = str(tmp_path / "history.jsonl")
        self._write_entry(h, STATE_OVERRIDDEN, override_reason="false_positive")
        self._write_entry(h, STATE_OVERRIDDEN, override_reason="false_positive")
        self._write_entry(h, STATE_OVERRIDDEN, override_reason="acceptable_risk")
        self._write_entry(h, STATE_PASSED)
        result = engine.compute_stats(h, by_reason=True)
        assert "by_reason" in result
        assert result["by_reason"][0] == {"reason": "false_positive", "count": 2}
        assert result["by_reason"][1] == {"reason": "acceptable_risk", "count": 1}

    def test_by_reason_not_included_by_default(self, tmp_path):
        h = str(tmp_path / "history.jsonl")
        self._write_entry(h, STATE_PASSED)
        result = engine.compute_stats(h)
        assert "by_reason" not in result

    def test_by_path(self, tmp_path):
        h = str(tmp_path / "history.jsonl")
        self._write_entry(h, STATE_BLOCKED, cwd="/repo/a")
        self._write_entry(h, STATE_BLOCKED, cwd="/repo/a")
        self._write_entry(h, STATE_PASSED, cwd="/repo/a")
        self._write_entry(h, STATE_BLOCKED, cwd="/repo/b")
        self._write_entry(h, STATE_OVERRIDDEN, cwd="/repo/b", override_reason="fp")
        result = engine.compute_stats(h, by_path=True)
        assert "by_path" in result
        a = next(p for p in result["by_path"] if p["path"] == "/repo/a")
        b = next(p for p in result["by_path"] if p["path"] == "/repo/b")
        assert a["total"] == 3
        assert a["blocked"] == 2
        assert b["total"] == 2
        assert b["blocked"] == 1
        assert b["overridden"] == 1
        # sorted by blocked desc
        assert result["by_path"][0]["path"] == "/repo/a"

    def test_by_path_not_included_by_default(self, tmp_path):
        h = str(tmp_path / "history.jsonl")
        self._write_entry(h, STATE_PASSED)
        result = engine.compute_stats(h)
        assert "by_path" not in result

    def test_combined_flags(self, tmp_path):
        h = str(tmp_path / "history.jsonl")
        self._write_entry(h, STATE_OVERRIDDEN, cwd="/repo/x", override_reason="fp")
        self._write_entry(h, STATE_BLOCKED, cwd="/repo/x")
        result = engine.compute_stats(h, by_reason=True, by_path=True)
        assert "by_reason" in result
        assert "by_path" in result
        assert result["total"] == 2

    def test_malformed_lines_skipped(self, tmp_path):
        h = tmp_path / "history.jsonl"
        h.write_text("not json\n{bad\n")
        result = engine.compute_stats(str(h))
        assert result["total"] == 0


class TestParseFlatYaml:

    def test_basic_key_value(self):
        result = _parse_flat_yaml("mode: block\nmodel: opus\n")
        assert result == {"mode": "block", "model": "opus"}

    def test_comments_and_blanks(self):
        text = "# comment\nmode: block\n\n# another\nmodel: opus\n"
        result = _parse_flat_yaml(text)
        assert result == {"mode": "block", "model": "opus"}

    def test_quoted_values(self):
        text = 'language: "繁體中文（台灣）"\n'
        result = _parse_flat_yaml(text)
        assert result["language"] == "繁體中文（台灣）"

    def test_single_quoted_values(self):
        text = "language: '繁體中文'\n"
        result = _parse_flat_yaml(text)
        assert result["language"] == "繁體中文"

    def test_colon_in_value(self):
        text = "language: foo: bar\n"
        result = _parse_flat_yaml(text)
        assert result["language"] == "foo: bar"

    def test_empty_value(self):
        text = "mode:\n"
        result = _parse_flat_yaml(text)
        assert result["mode"] == ""

    def test_spaces_around(self):
        text = "  mode  :  block  \n"
        result = _parse_flat_yaml(text)
        assert result["mode"] == "block"

    def test_no_colon_ignored(self):
        text = "no colon here\nmode: block\n"
        result = _parse_flat_yaml(text)
        assert result == {"mode": "block"}


class TestLoadPolicy:

    def test_load_from_repo(self, tmp_path):
        policy_file = tmp_path / POLICY_FILENAME
        policy_file.write_text("mode: report\nconfidence: high\n", encoding="utf-8")
        result = engine.load_policy(str(tmp_path))
        assert result == {"mode": "report", "confidence": "high"}

    def test_no_file(self, tmp_path):
        result = engine.load_policy(str(tmp_path))
        assert result == {}

    def test_none_root(self):
        result = engine.load_policy(None)
        assert result == {}

    def test_empty_root(self):
        result = engine.load_policy("")
        assert result == {}

    def test_integer_conversion(self, tmp_path):
        policy_file = tmp_path / POLICY_FILENAME
        policy_file.write_text("max_tokens: 8000\ncheck_timeout_sec: 90\n", encoding="utf-8")
        result = engine.load_policy(str(tmp_path))
        assert result["max_tokens"] == 8000
        assert result["check_timeout_sec"] == 90

    def test_invalid_integer_dropped(self, tmp_path):
        policy_file = tmp_path / POLICY_FILENAME
        policy_file.write_text("max_tokens: abc\n", encoding="utf-8")
        result = engine.load_policy(str(tmp_path))
        assert "max_tokens" not in result

    def test_unknown_keys_ignored(self, tmp_path):
        policy_file = tmp_path / POLICY_FILENAME
        policy_file.write_text("mode: block\nfoo: bar\nbaz: 42\n", encoding="utf-8")
        result = engine.load_policy(str(tmp_path))
        assert result == {"mode": "block"}

    def test_threshold_alias(self, tmp_path):
        policy_file = tmp_path / POLICY_FILENAME
        policy_file.write_text("threshold: major\n", encoding="utf-8")
        result = engine.load_policy(str(tmp_path))
        assert result == {"block_threshold": "major"}

    def test_block_threshold_direct(self, tmp_path):
        policy_file = tmp_path / POLICY_FILENAME
        policy_file.write_text("block_threshold: major\n", encoding="utf-8")
        result = engine.load_policy(str(tmp_path))
        assert result == {"block_threshold": "major"}

    def test_empty_values_skipped(self, tmp_path):
        policy_file = tmp_path / POLICY_FILENAME
        policy_file.write_text("mode:\nmodel: opus\n", encoding="utf-8")
        result = engine.load_policy(str(tmp_path))
        assert result == {"model": "opus"}

    def test_full_policy(self, tmp_path):
        policy_file = tmp_path / POLICY_FILENAME
        policy_file.write_text(
            "mode: report\n"
            "model: sonnet\n"
            "max_tokens: 6000\n"
            "block_threshold: major\n"
            "confidence: high\n"
            "language: English\n"
            "scope: staged\n",
            encoding="utf-8",
        )
        result = engine.load_policy(str(tmp_path))
        assert result == {
            "mode": "report",
            "model": "sonnet",
            "max_tokens": 6000,
            "block_threshold": "major",
            "confidence": "high",
            "language": "English",
            "scope": "staged",
        }

    def test_local_check_policy_keys(self, tmp_path):
        policy_file = tmp_path / POLICY_FILENAME
        policy_file.write_text("checks: off\ncheck_timeout_sec: 45\n", encoding="utf-8")

        result = engine.load_policy(str(tmp_path))

        assert result == {"checks": "off", "check_timeout_sec": 45}


class TestResolve:

    def test_cli_wins(self):
        from cold_eyes.engine import _resolve
        result = _resolve("report", "COLD_REVIEW_MODE", {"mode": "off"}, "mode", "block")
        assert result == "report"

    def test_env_var_over_policy(self, monkeypatch):
        from cold_eyes.engine import _resolve
        monkeypatch.setenv("COLD_REVIEW_MODE", "report")
        result = _resolve(None, "COLD_REVIEW_MODE", {"mode": "off"}, "mode", "block")
        assert result == "report"

    def test_policy_over_default(self):
        from cold_eyes.engine import _resolve
        result = _resolve(None, "COLD_REVIEW_MODE_NONEXISTENT", {"mode": "report"}, "mode", "block")
        assert result == "report"

    def test_default_fallback(self):
        from cold_eyes.engine import _resolve
        result = _resolve(None, "COLD_REVIEW_MODE_NONEXISTENT", {}, "mode", "block")
        assert result == "block"

    def test_cast_applied(self):
        from cold_eyes.engine import _resolve
        result = _resolve("8000", "X", {}, "x", 12000, cast=int)
        assert result == 8000
        assert isinstance(result, int)


class TestDoctorPolicyFile:

    def test_policy_found(self, tmp_path):
        policy_file = tmp_path / POLICY_FILENAME
        policy_file.write_text("mode: report\n", encoding="utf-8")
        result = engine.run_doctor(scripts_dir=str(tmp_path),
                                   settings_path=str(tmp_path / "s.json"),
                                   repo_root=str(tmp_path))
        pf = next(c for c in result["checks"] if c["name"] == "policy_file")
        assert pf["status"] == "ok"
        assert "mode" in pf["detail"]

    def test_policy_not_found(self, tmp_path):
        result = engine.run_doctor(scripts_dir=str(tmp_path),
                                   settings_path=str(tmp_path / "s.json"),
                                   repo_root=str(tmp_path))
        pf = next(c for c in result["checks"] if c["name"] == "policy_file")
        assert pf["status"] == "info"

    def test_policy_empty(self, tmp_path):
        policy_file = tmp_path / POLICY_FILENAME
        policy_file.write_text("# only comments\n", encoding="utf-8")
        result = engine.run_doctor(scripts_dir=str(tmp_path),
                                   settings_path=str(tmp_path / "s.json"),
                                   repo_root=str(tmp_path))
        pf = next(c for c in result["checks"] if c["name"] == "policy_file")
        assert pf["status"] == "info"


class TestMockAdapter:

    def test_returns_fixed_response(self):
        adapter = MockAdapter(response='{"pass": true}', exit_code=0)
        inv = adapter.review("diff", "prompt", "opus")
        assert inv.stdout == '{"pass": true}'
        assert inv.exit_code == 0

    def test_backward_compat_tuple_destructure(self):
        adapter = MockAdapter(response='{"pass": true}', exit_code=0)
        out, code = adapter.review("diff", "prompt", "opus")
        assert out == '{"pass": true}'
        assert code == 0

    def test_records_inputs(self):
        adapter = MockAdapter()
        adapter.review("my diff", "my prompt", "sonnet")
        assert adapter.last_diff == "my diff"
        assert adapter.last_prompt == "my prompt"
        assert adapter.last_model == "sonnet"
        assert adapter.call_count == 1

    def test_call_count_increments(self):
        adapter = MockAdapter()
        adapter.review("a", "b", "c")
        adapter.review("d", "e", "f")
        assert adapter.call_count == 2

    def test_error_exit_code(self):
        adapter = MockAdapter(response="", exit_code=-1, failure_kind="timeout")
        inv = adapter.review("diff", "prompt", "opus")
        assert inv.stdout == ""
        assert inv.exit_code == -1
        assert inv.failure_kind == "timeout"

    def test_stderr_captured(self):
        adapter = MockAdapter(response="", exit_code=1, stderr="auth failed")
        inv = adapter.review("diff", "prompt", "opus")
        assert inv.stderr == "auth failed"


class TestClaudeCliAdapter:

    def test_inherits_model_adapter(self):
        adapter = ClaudeCliAdapter()
        assert isinstance(adapter, ModelAdapter)

    def test_custom_timeout(self):
        adapter = ClaudeCliAdapter(timeout=60)
        assert adapter.timeout == 60

    def test_default_timeout(self):
        adapter = ClaudeCliAdapter()
        assert adapter.timeout == 300


# ===========================================================================
# PATCH 4 — Typed git failures
# ===========================================================================

class TestGitCommandError:

    def test_git_cmd_raises_on_nonzero(self, monkeypatch):
        """git_cmd must raise GitCommandError when exit code != 0."""
        import subprocess
        def fake_run(*a, **kw):
            return subprocess.CompletedProcess(a, returncode=128, stdout="", stderr="fatal: bad")
        monkeypatch.setattr(subprocess, "run", fake_run)
        with pytest.raises(GitCommandError) as exc_info:
            git_cmd("diff", "--name-only")
        assert exc_info.value.returncode == 128
        assert "bad" in exc_info.value.stderr

    def test_git_cmd_success_returns_stdout(self, monkeypatch):
        import subprocess
        def fake_run(*a, **kw):
            return subprocess.CompletedProcess(a, returncode=0, stdout="file.py\n", stderr="")
        monkeypatch.setattr(subprocess, "run", fake_run)
        assert git_cmd("diff", "--name-only") == "file.py"

    def test_engine_git_failure_is_infra_failed(self, monkeypatch, tmp_path):
        """Engine maps GitCommandError from collect_files to infra_failed."""
        def raise_git(*args, **kwargs):
            raise GitCommandError(["diff"], 128, "fatal")
        monkeypatch.setattr(_engine_mod, "git_cmd", lambda *a: "")  # rev-parse ok
        monkeypatch.setattr(_engine_mod, "collect_files", raise_git)
        monkeypatch.setattr(constants, "HISTORY_FILE", str(tmp_path / "h.jsonl"))
        result = _engine_mod.run(mode="block", adapter=MockAdapter())
        assert result["state"] == STATE_INFRA_FAILED
        assert result["action"] == "pass"

    def test_engine_config_error_is_infra_failed(self, monkeypatch, tmp_path):
        """Engine maps ConfigError from collect_files to infra_failed."""
        def raise_config(*args, **kwargs):
            raise ConfigError("pr-diff scope requires --base")
        monkeypatch.setattr(_engine_mod, "git_cmd", lambda *a: "")
        monkeypatch.setattr(_engine_mod, "collect_files", raise_config)
        monkeypatch.setattr(constants, "HISTORY_FILE", str(tmp_path / "h.jsonl"))
        result = _engine_mod.run(mode="block", adapter=MockAdapter())
        assert result["state"] == STATE_INFRA_FAILED
        assert "pr-diff" in result["reason"]


# ===========================================================================
# PATCH 6 — ReviewInvocation + stderr/failure_kind
# ===========================================================================

class TestReviewInvocation:

    def test_review_invocation_fields(self):
        inv = ReviewInvocation("out", "err", 0)
        assert inv.stdout == "out"
        assert inv.stderr == "err"
        assert inv.exit_code == 0
        assert inv.failure_kind is None

    def test_review_invocation_with_failure_kind(self):
        inv = ReviewInvocation("", "", -1, "timeout")
        assert inv.failure_kind == "timeout"

    def test_backward_compat_iter(self):
        inv = ReviewInvocation("output", "err", 0)
        out, code = inv
        assert out == "output"
        assert code == 0


class TestHistoryFailureKind:

    def test_failure_kind_in_history(self, tmp_path):
        hfile = str(tmp_path / "h.jsonl")
        log_to_history("/tmp", "block", "opus", STATE_INFRA_FAILED,
                       reason="claude exit -1",
                       failure_kind="timeout", stderr_excerpt="timed out",
                       min_confidence="medium", scope="working")
        # Re-read from constants default; override for this test
        import cold_eyes.constants as c
        orig = c.HISTORY_FILE
        c.HISTORY_FILE = hfile
        try:
            log_to_history("/tmp", "block", "opus", STATE_INFRA_FAILED,
                           reason="claude exit -1",
                           failure_kind="timeout", stderr_excerpt="timed out")
        finally:
            c.HISTORY_FILE = orig
        with open(hfile) as f:
            entry = json.loads(f.readline())
        assert entry["failure_kind"] == "timeout"
        assert entry["stderr_excerpt"] == "timed out"

    def test_no_failure_kind_when_success(self, tmp_path):
        import cold_eyes.constants as c
        hfile = str(tmp_path / "h.jsonl")
        orig = c.HISTORY_FILE
        c.HISTORY_FILE = hfile
        try:
            log_to_history("/tmp", "block", "opus", STATE_PASSED)
        finally:
            c.HISTORY_FILE = orig
        with open(hfile) as f:
            entry = json.loads(f.readline())
        assert "failure_kind" not in entry
        assert "stderr_excerpt" not in entry


# ===========================================================================
# PATCH 5 — Rich diff metadata
# ===========================================================================

class TestDiffMetadata:

    def test_partial_file_sets_truncated_true(self, tmp_path):
        """A single file cut mid-content should set truncated=True."""
        f = tmp_path / "big.py"
        f.write_text("x = 1\n" * 2000)  # large file
        old_cwd = os.getcwd()
        os.chdir(tmp_path)
        try:
            meta = engine.build_diff(["big.py"], {"big.py"}, max_tokens=50)
            assert meta["truncated"] is True
            assert "big.py" in meta["partial_files"]
            assert meta["skipped_budget"] == []
        finally:
            os.chdir(old_cwd)

    def test_binary_in_skipped_binary(self, tmp_path):
        f = tmp_path / "img.png"
        f.write_bytes(b"\x89PNG\r\n\x00\x00")
        old_cwd = os.getcwd()
        os.chdir(tmp_path)
        try:
            meta = engine.build_diff(["img.png"], {"img.png"}, max_tokens=12000)
            assert "img.png" in meta["skipped_binary"]
            assert meta["truncated"] is True
        finally:
            os.chdir(old_cwd)

    def test_unreadable_in_skipped_unreadable(self, tmp_path):
        """A file that can't be read lands in skipped_unreadable."""
        f = tmp_path / "secret.dat"
        f.write_text("data")
        old_cwd = os.getcwd()
        os.chdir(tmp_path)
        try:
            # Make unreadable by monkeypatching open
            import builtins
            real_open = builtins.open
            def bad_open(path, *a, **kw):
                if "secret.dat" in str(path) and "r" in str(a):
                    raise OSError("permission denied")
                return real_open(path, *a, **kw)
            builtins.open = bad_open
            try:
                meta = engine.build_diff(["secret.dat"], {"secret.dat"}, max_tokens=12000)
                assert "secret.dat" in meta["skipped_unreadable"]
            finally:
                builtins.open = real_open
        finally:
            os.chdir(old_cwd)

    def test_budget_exhausted_in_skipped_budget(self, tmp_path):
        f1 = tmp_path / "a.py"
        f1.write_text("a" * 377)  # 377 chars + 23 header = 400 → exactly 100 tokens
        f2 = tmp_path / "b.py"
        f2.write_text("b")
        old_cwd = os.getcwd()
        os.chdir(tmp_path)
        try:
            meta = engine.build_diff(
                ["a.py", "b.py"], {"a.py", "b.py"}, max_tokens=100
            )
            assert "b.py" in meta["skipped_budget"]
        finally:
            os.chdir(old_cwd)

    def test_no_truncation_when_all_fit(self, tmp_path):
        f = tmp_path / "small.py"
        f.write_text("x = 1\n")
        old_cwd = os.getcwd()
        os.chdir(tmp_path)
        try:
            meta = engine.build_diff(["small.py"], {"small.py"}, max_tokens=12000)
            assert meta["truncated"] is False
            assert meta["partial_files"] == []
            assert meta["skipped_budget"] == []
            assert meta["skipped_binary"] == []
            assert meta["skipped_unreadable"] == []
        finally:
            os.chdir(old_cwd)


# ===========================================================================
# PATCH 7 — Policy/state machine fixes
# ===========================================================================

class TestPolicyStateMachine:

    def _review_with_issues(self, severity="critical", confidence="high"):
        return {
            "pass": False, "review_status": "completed",
            "issues": [{"severity": severity, "confidence": confidence,
                        "check": "x", "verdict": "y", "fix": "z",
                        "file": "auth.py", "line_hint": "42"}],
            "summary": "test",
        }

    def test_all_filtered_out_state_is_passed(self):
        """If confidence filter removes all issues, report mode → passed, not reported."""
        review = self._review_with_issues(confidence="low")
        outcome = engine.apply_policy(review, "report", "critical", False, "high")
        assert outcome["state"] == STATE_PASSED

    def test_report_with_remaining_issues_is_reported(self):
        review = self._review_with_issues(confidence="high")
        outcome = engine.apply_policy(review, "report", "critical", False, "medium")
        assert outcome["state"] == STATE_REPORTED

    def test_block_reason_includes_file(self):
        review = self._review_with_issues()
        outcome = engine.apply_policy(review, "block", "critical", False, "medium")
        assert "auth.py" in outcome["reason"]

    def test_block_reason_includes_line_hint(self):
        review = self._review_with_issues()
        outcome = engine.apply_policy(review, "block", "critical", False, "medium")
        assert "(~42)" in outcome["reason"]

    def test_block_reason_english_labels(self):
        review = self._review_with_issues()
        outcome = engine.apply_policy(review, "block", "critical", False, "medium",
                                      language="English")
        assert "Check:" in outcome["reason"]
        assert "Verdict:" in outcome["reason"]
        assert "Fix:" in outcome["reason"]
        assert "\u6aa2\u67e5" not in outcome["reason"]

    def test_block_reason_chinese_default(self):
        review = self._review_with_issues()
        outcome = engine.apply_policy(review, "block", "critical", False, "medium")
        assert "\u6aa2\u67e5" in outcome["reason"]

    def test_infra_state_consistent_across_modes(self):
        infra = {"pass": True, "review_status": "failed", "issues": [], "summary": "err"}
        block_outcome = engine.apply_policy(infra, "block", "critical", False, "medium")
        report_outcome = engine.apply_policy(infra, "report", "critical", False, "medium")
        assert block_outcome["state"] == STATE_INFRA_FAILED
        assert report_outcome["state"] == STATE_INFRA_FAILED


# ===========================================================================
# History retention (prune / archive) and quality report
# ===========================================================================

class TestHistoryPrune:

    def _write_entry(self, path, state, timestamp=None):
        entry = {
            "version": 2, "state": state, "mode": "block", "model": "opus",
            "timestamp": timestamp or "2026-04-10T12:00:00Z",
            "cwd": "/tmp",
        }
        with open(path, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry) + "\n")

    def test_prune_by_entries(self, tmp_path):
        h = str(tmp_path / "h.jsonl")
        for _ in range(10):
            self._write_entry(h, STATE_PASSED)
        result = prune_history(h, keep_entries=3)
        assert result["original"] == 10
        assert result["kept"] == 3
        assert result["removed"] == 7

    def test_prune_by_days(self, tmp_path):
        h = str(tmp_path / "h.jsonl")
        self._write_entry(h, STATE_PASSED, "2020-01-01T00:00:00Z")  # old
        self._write_entry(h, STATE_BLOCKED, "2099-01-01T00:00:00Z")  # future
        result = prune_history(h, keep_days=1)
        assert result["kept"] == 1
        assert result["removed"] == 1

    def test_prune_requires_args(self):
        result = prune_history(keep_days=None, keep_entries=None)
        assert "error" in result


class TestHistoryArchive:

    def _write_entry(self, path, state, timestamp):
        entry = {
            "version": 2, "state": state, "mode": "block", "model": "opus",
            "timestamp": timestamp, "cwd": "/tmp",
        }
        with open(path, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry) + "\n")

    def test_archive_moves_old_entries(self, tmp_path):
        h = str(tmp_path / "h.jsonl")
        a = str(tmp_path / "h.jsonl.archive")
        self._write_entry(h, STATE_PASSED, "2025-01-01T00:00:00Z")
        self._write_entry(h, STATE_BLOCKED, "2026-06-01T00:00:00Z")
        result = archive_history(h, before="2026-01-01", dest=a)
        assert result["archived"] == 1
        assert result["kept"] == 1
        assert os.path.isfile(a)

    def test_archive_requires_before(self):
        result = archive_history(before=None)
        assert "error" in result


class TestQualityReport:

    def _write_entry(self, path, state, cwd="/tmp", review=None, timestamp=None):
        entry = {
            "version": 2, "state": state, "mode": "block", "model": "opus",
            "timestamp": timestamp or "2026-04-10T12:00:00Z",
            "cwd": cwd,
        }
        if review:
            entry["review"] = review
        with open(path, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry) + "\n")

    def test_empty_history(self, tmp_path):
        h = str(tmp_path / "h.jsonl")
        (tmp_path / "h.jsonl").write_text("")
        result = quality_report(h)
        assert result["total"] == 0

    def test_rates_computed(self, tmp_path):
        h = str(tmp_path / "h.jsonl")
        self._write_entry(h, STATE_PASSED)
        self._write_entry(h, STATE_PASSED)
        self._write_entry(h, STATE_BLOCKED)
        self._write_entry(h, STATE_OVERRIDDEN)
        result = quality_report(h)
        assert result["total"] == 4
        assert result["rates"]["block_rate"] == 0.25
        assert result["rates"]["override_rate"] == 0.25

    def test_noisy_paths(self, tmp_path):
        h = str(tmp_path / "h.jsonl")
        self._write_entry(h, STATE_BLOCKED, cwd="/noisy")
        self._write_entry(h, STATE_BLOCKED, cwd="/noisy")
        self._write_entry(h, STATE_PASSED, cwd="/quiet")
        result = quality_report(h)
        assert len(result["top_noisy_paths"]) == 1
        assert result["top_noisy_paths"][0]["path"] == "/noisy"

    def test_issue_categories(self, tmp_path):
        h = str(tmp_path / "h.jsonl")
        review = {"issues": [{"category": "security"}, {"category": "security"}, {"category": "logic"}]}
        self._write_entry(h, STATE_BLOCKED, review=review)
        result = quality_report(h)
        assert result["top_issue_categories"][0]["category"] == "security"
        assert result["top_issue_categories"][0]["count"] == 2

    def _write_entry_depth(self, path, state, review_depth, cwd="/tmp"):
        entry = {
            "version": 2, "state": state, "mode": "block", "model": "opus",
            "timestamp": "2026-04-10T12:00:00Z", "cwd": cwd,
            "review_depth": review_depth,
        }
        with open(path, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry) + "\n")

    def test_triage_distribution(self, tmp_path):
        h = str(tmp_path / "h.jsonl")
        self._write_entry_depth(h, STATE_SKIPPED, "skip")
        self._write_entry_depth(h, STATE_SKIPPED, "skip")
        self._write_entry_depth(h, STATE_PASSED, "shallow")
        self._write_entry_depth(h, STATE_PASSED, "deep")
        self._write_entry_depth(h, STATE_BLOCKED, "deep")
        result = quality_report(h)
        assert "by_review_depth" in result
        assert result["by_review_depth"]["skip"] == 2
        assert result["by_review_depth"]["shallow"] == 1
        assert result["by_review_depth"]["deep"] == 2

    def test_triage_distribution_missing_depth(self, tmp_path):
        """Entries without review_depth should count as 'unknown'."""
        h = str(tmp_path / "h.jsonl")
        self._write_entry(h, STATE_PASSED)
        result = quality_report(h)
        assert "by_review_depth" in result
        assert result["by_review_depth"].get("unknown", 0) == 1
