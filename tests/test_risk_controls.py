"""Tests for truncation policy, coverage visibility, and risk controls."""

import json
import os
import sys

import pytest

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from cold_eyes.policy import apply_policy
from cold_eyes.config import load_policy
from cold_eyes.doctor import run_doctor
from cold_eyes.engine import _resolve
from cold_eyes import __version__
from cold_eyes.constants import (
    STATE_PASSED, STATE_BLOCKED, STATE_OVERRIDDEN,
    STATE_INFRA_FAILED, STATE_REPORTED, STATE_SKIPPED,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _review_with_issues(severity="critical", confidence="high"):
    return {
        "review_status": "completed",
        "pass": False,
        "issues": [{
            "check": "test issue",
            "verdict": "test verdict",
            "fix": "test fix",
            "severity": severity,
            "confidence": confidence,
        }],
        "summary": "test summary",
    }


def _review_no_issues():
    return {
        "review_status": "completed",
        "pass": True,
        "issues": [],
        "summary": "all clear",
    }


def _review_infra_failed():
    return {
        "review_status": "failed",
        "pass": True,
        "issues": [],
        "summary": "timeout",
    }


# ---------------------------------------------------------------------------
# Truncation Policy: warn (default, current behavior)
# ---------------------------------------------------------------------------

class TestTruncationPolicyWarn:
    def test_warn_with_issues_blocks(self):
        review = _review_with_issues()
        outcome = apply_policy(review, "block", "critical", False,
                               truncated=True, skipped_files=["a.py"],
                               truncation_policy="warn")
        assert outcome["action"] == "block"

    def test_warn_no_issues_passes(self):
        review = _review_no_issues()
        outcome = apply_policy(review, "block", "critical", False,
                               truncated=True, skipped_files=["a.py"],
                               truncation_policy="warn")
        assert outcome["action"] == "pass"
        assert outcome["state"] == STATE_PASSED

    def test_warn_is_default(self):
        """No truncation_policy arg should behave like warn."""
        review = _review_no_issues()
        outcome = apply_policy(review, "block", "critical", False,
                               truncated=True, skipped_files=["a.py"])
        assert outcome["action"] == "pass"

    def test_warn_not_truncated_normal(self):
        review = _review_with_issues()
        outcome = apply_policy(review, "block", "critical", False,
                               truncated=False, truncation_policy="warn")
        assert outcome["action"] == "block"


# ---------------------------------------------------------------------------
# Truncation Policy: soft-pass
# ---------------------------------------------------------------------------

class TestTruncationPolicySoftPass:
    def test_soft_pass_no_issues_truncated_passes(self):
        review = _review_no_issues()
        outcome = apply_policy(review, "block", "critical", False,
                               truncated=True, skipped_files=["a.py", "b.py"],
                               truncation_policy="soft-pass")
        assert outcome["action"] == "pass"
        assert outcome["state"] == STATE_PASSED
        assert outcome["truncated"] is True
        assert outcome["skipped_count"] == 2

    def test_soft_pass_with_issues_still_blocks(self):
        review = _review_with_issues()
        outcome = apply_policy(review, "block", "critical", False,
                               truncated=True, skipped_files=["a.py"],
                               truncation_policy="soft-pass")
        assert outcome["action"] == "block"

    def test_soft_pass_not_truncated_normal(self):
        review = _review_no_issues()
        outcome = apply_policy(review, "block", "critical", False,
                               truncated=False, truncation_policy="soft-pass")
        assert outcome["action"] == "pass"

    def test_soft_pass_report_mode_unaffected(self):
        review = _review_no_issues()
        outcome = apply_policy(review, "report", "critical", False,
                               truncated=True, skipped_files=["a.py"],
                               truncation_policy="soft-pass")
        assert outcome["action"] == "pass"


# ---------------------------------------------------------------------------
# Truncation Policy: fail-closed
# ---------------------------------------------------------------------------

class TestTruncationPolicyFailClosed:
    def test_fail_closed_no_issues_truncated_blocks(self):
        review = _review_no_issues()
        outcome = apply_policy(review, "block", "critical", False,
                               truncated=True, skipped_files=["a.py"],
                               truncation_policy="fail-closed")
        assert outcome["action"] == "block"
        assert outcome["state"] == STATE_BLOCKED

    def test_fail_closed_with_issues_truncated_blocks(self):
        review = _review_with_issues()
        outcome = apply_policy(review, "block", "critical", False,
                               truncated=True, skipped_files=["a.py"],
                               truncation_policy="fail-closed")
        assert outcome["action"] == "block"

    def test_fail_closed_not_truncated_normal(self):
        review = _review_no_issues()
        outcome = apply_policy(review, "block", "critical", False,
                               truncated=False, truncation_policy="fail-closed")
        assert outcome["action"] == "pass"

    def test_fail_closed_override_does_not_bypass(self):
        review = _review_no_issues()
        outcome = apply_policy(review, "block", "critical", True,
                               truncated=True, skipped_files=["a.py"],
                               truncation_policy="fail-closed")
        # fail-closed is never bypassed by override (Bug #53 fix)
        assert outcome["action"] == "block"

    def test_fail_closed_report_mode_unaffected(self):
        review = _review_no_issues()
        outcome = apply_policy(review, "report", "critical", False,
                               truncated=True, skipped_files=["a.py"],
                               truncation_policy="fail-closed")
        assert outcome["action"] == "pass"

    def test_fail_closed_display_message(self):
        review = _review_no_issues()
        outcome = apply_policy(review, "block", "critical", False,
                               truncated=True, skipped_files=["a.py", "b.py"],
                               truncation_policy="fail-closed")
        assert "fail-closed" in outcome["display"]
        assert "2 files unreviewed" in outcome["display"]


# ---------------------------------------------------------------------------
# Truncation Policy: config resolution
# ---------------------------------------------------------------------------

class TestTruncationPolicyConfig:
    def test_policy_file_key(self, tmp_path):
        policy_file = tmp_path / ".cold-review-policy.yml"
        policy_file.write_text("truncation_policy: fail-closed\n")
        policy = load_policy(str(tmp_path))
        assert policy.get("truncation_policy") == "fail-closed"

    def test_unknown_key_ignored(self, tmp_path):
        policy_file = tmp_path / ".cold-review-policy.yml"
        policy_file.write_text("unknown_key: value\n")
        policy = load_policy(str(tmp_path))
        assert "unknown_key" not in policy

    def test_valid_truncation_values(self, tmp_path):
        for val in ("warn", "soft-pass", "fail-closed"):
            policy_file = tmp_path / ".cold-review-policy.yml"
            policy_file.write_text(f"truncation_policy: {val}\n")
            policy = load_policy(str(tmp_path))
            assert policy["truncation_policy"] == val


class TestCoveragePolicyConfig:
    def test_policy_keys_parse_correctly(self, tmp_path):
        policy_file = tmp_path / ".cold-review-policy.yml"
        policy_file.write_text(
            "minimum_coverage_pct: 80\n"
            "coverage_policy: fail-closed\n"
            "fail_on_unreviewed_high_risk: true\n"
        )
        policy = load_policy(str(tmp_path))
        assert policy["minimum_coverage_pct"] == 80
        assert policy["coverage_policy"] == "fail-closed"
        assert policy["fail_on_unreviewed_high_risk"] is True

    def test_invalid_values_ignored(self, tmp_path):
        policy_file = tmp_path / ".cold-review-policy.yml"
        policy_file.write_text(
            "minimum_coverage_pct: 101\n"
            "coverage_policy: noisy\n"
            "fail_on_unreviewed_high_risk: maybe\n"
        )
        policy = load_policy(str(tmp_path))
        assert "minimum_coverage_pct" not in policy
        assert "coverage_policy" not in policy
        assert "fail_on_unreviewed_high_risk" not in policy

    def test_env_vars_resolve_correctly(self, monkeypatch):
        monkeypatch.setenv("COLD_REVIEW_MINIMUM_COVERAGE_PCT", "75")
        monkeypatch.setenv("COLD_REVIEW_COVERAGE_POLICY", "block")
        assert _resolve(
            None, "COLD_REVIEW_MINIMUM_COVERAGE_PCT",
            {}, "minimum_coverage_pct", None, cast=int,
        ) == 75
        assert _resolve(
            None, "COLD_REVIEW_COVERAGE_POLICY",
            {}, "coverage_policy", "warn",
        ) == "block"

    def test_init_gate_profile_writes_gate_policy(self, tmp_path):
        from cold_eyes.doctor import run_init

        result = run_init(repo_root=str(tmp_path), profile="gate")
        policy_text = (tmp_path / ".cold-review-policy.yml").read_text()
        assert result["profile"] == "gate"
        assert ".cold-review-policy.yml" in result["created"]
        assert "scope: staged" in policy_text
        assert "minimum_coverage_pct: 80" in policy_text

    def test_init_defaults_to_gate_profile(self, tmp_path):
        from cold_eyes.doctor import run_init

        result = run_init(repo_root=str(tmp_path))
        policy_text = (tmp_path / ".cold-review-policy.yml").read_text()
        assert result["profile"] == "gate"
        assert "scope: staged" in policy_text
        assert "model: sonnet" in policy_text

    def test_init_gate_profile_skips_existing_policy(self, tmp_path):
        from cold_eyes.doctor import run_init

        policy_file = tmp_path / ".cold-review-policy.yml"
        policy_file.write_text("mode: report\n")
        result = run_init(repo_root=str(tmp_path), profile="gate")
        assert ".cold-review-policy.yml" in result["skipped"]
        assert policy_file.read_text() == "mode: report\n"

    def test_init_gate_profile_force_overwrites_policy(self, tmp_path):
        from cold_eyes.doctor import run_init

        policy_file = tmp_path / ".cold-review-policy.yml"
        policy_file.write_text("mode: report\n")
        result = run_init(repo_root=str(tmp_path), profile="gate", force=True)
        assert ".cold-review-policy.yml" in result["created"]
        assert "scope: staged" in policy_file.read_text()


# ---------------------------------------------------------------------------
# Coverage visibility
# ---------------------------------------------------------------------------

class TestCoverageVisibility:
    """Coverage fields are added by engine.run(), not by apply_policy().
    Test apply_policy includes truncated/skipped_count in outcomes."""

    def test_pass_outcome_has_truncated(self):
        review = _review_no_issues()
        outcome = apply_policy(review, "block", "critical", False,
                               truncated=False)
        assert "truncated" in outcome
        assert outcome["truncated"] is False

    def test_block_outcome_has_skipped_count(self):
        review = _review_with_issues()
        outcome = apply_policy(review, "block", "critical", False,
                               truncated=True, skipped_files=["a.py", "b.py"])
        assert "skipped_count" in outcome
        assert outcome["skipped_count"] == 2


# ---------------------------------------------------------------------------
# State reachability
# ---------------------------------------------------------------------------

class TestStateReachability:
    def test_passed(self):
        review = _review_no_issues()
        outcome = apply_policy(review, "block", "critical", False)
        assert outcome["state"] == STATE_PASSED

    def test_blocked(self):
        review = _review_with_issues()
        outcome = apply_policy(review, "block", "critical", False)
        assert outcome["state"] == STATE_BLOCKED

    def test_overridden(self):
        review = _review_with_issues()
        outcome = apply_policy(review, "block", "critical", True,
                               override_reason="testing")
        assert outcome["state"] == STATE_OVERRIDDEN

    def test_infra_failed_block(self):
        review = _review_infra_failed()
        outcome = apply_policy(review, "block", "critical", False)
        assert outcome["state"] == STATE_INFRA_FAILED

    def test_infra_failed_report(self):
        review = _review_infra_failed()
        outcome = apply_policy(review, "report", "critical", False)
        assert outcome["state"] == STATE_INFRA_FAILED

    def test_reported(self):
        review = _review_with_issues()
        outcome = apply_policy(review, "report", "critical", False)
        assert outcome["state"] == STATE_REPORTED


# ---------------------------------------------------------------------------
# Engine skip on zero file_count
# ---------------------------------------------------------------------------

class TestZeroFileCountSkip:
    def test_skip_when_file_count_zero(self):
        """Engine skips when diff has file_count=0 even if diff_text is non-empty."""
        from cold_eyes.engine import run
        from cold_eyes.claude import MockAdapter
        # MockAdapter returns a valid review, but if engine reaches it with
        # zero files, it should have skipped before calling the adapter.
        adapter = MockAdapter('{"pass": true, "issues": [], "review_status": "completed"}')
        # Monkeypatch collect_files to return a file, and build_diff to return
        # file_count=0 (simulates empty diff chunks with truncation notice)
        import cold_eyes.engine as eng_mod

        orig_collect = eng_mod.collect_files
        orig_build = eng_mod.build_diff
        orig_filter = eng_mod.filter_file_list
        orig_rank = eng_mod.rank_file_list

        eng_mod.collect_files = lambda scope, base=None: (["phantom.py"], set())
        eng_mod.filter_file_list = lambda files, ignore_file="": files
        eng_mod.rank_file_list = lambda files, untracked: files
        eng_mod.build_diff = lambda ranked, untracked, max_tokens, scope=None, base=None: {
            "diff_text": "\n[Cold Eyes: diff truncated]\n",
            "file_count": 0,
            "token_count": 0,
            "truncated": True,
            "partial_files": [],
            "skipped_budget": ["phantom.py"],
            "skipped_binary": [],
            "skipped_unreadable": [],
        }
        try:
            result = run(adapter=adapter)
            assert result["state"] == STATE_SKIPPED
            assert "no diff content" in result["reason"]
        finally:
            eng_mod.collect_files = orig_collect
            eng_mod.build_diff = orig_build
            eng_mod.filter_file_list = orig_filter
            eng_mod.rank_file_list = orig_rank


# ---------------------------------------------------------------------------
# CLI --version
# ---------------------------------------------------------------------------

class TestCLIVersion:
    def test_version_flag(self):
        import subprocess
        cli_path = os.path.join(PROJECT_ROOT, "cold_eyes", "cli.py")
        r = subprocess.run(
            [sys.executable, cli_path, "--version"],
            capture_output=True, text=True, encoding="utf-8",
        )
        assert r.returncode == 0
        assert __version__ in r.stdout


# ---------------------------------------------------------------------------
# Doctor actionable messages
# ---------------------------------------------------------------------------

class TestDoctorActionableMessages:
    def test_deploy_files_fail_has_fix(self, tmp_path):
        """Deploy files failure detail must contain 'Fix:' guidance."""
        report = run_doctor(scripts_dir=str(tmp_path), repo_root=str(tmp_path))
        deploy_check = next(c for c in report["checks"] if c["name"] == "deploy_files")
        assert deploy_check["status"] == "fail"
        assert "Fix:" in deploy_check["detail"]

    def test_settings_hook_fail_has_fix(self, tmp_path):
        """Missing settings.json failure detail must contain 'Fix:' guidance."""
        fake_settings = str(tmp_path / "nonexistent_settings.json")
        report = run_doctor(scripts_dir=str(tmp_path), settings_path=fake_settings,
                            repo_root=str(tmp_path))
        hook_check = next(c for c in report["checks"] if c["name"] == "settings_hook")
        assert hook_check["status"] == "fail"
        assert "Fix:" in hook_check["detail"]

    def test_legacy_helper_fail_has_fix(self, tmp_path):
        """Legacy helper detection must contain 'Fix:' guidance."""
        helper = tmp_path / "cold-review-helper.py"
        helper.write_text("# legacy")
        report = run_doctor(scripts_dir=str(tmp_path), repo_root=str(tmp_path))
        legacy_check = next(c for c in report["checks"] if c["name"] == "legacy_helper")
        assert legacy_check["status"] == "fail"
        assert "Fix:" in legacy_check["detail"]
