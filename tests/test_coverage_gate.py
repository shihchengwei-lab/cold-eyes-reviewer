"""Tests for coverage gate decisions."""

import json
from unittest.mock import MagicMock, patch

from cold_eyes.coverage_gate import build_coverage_report, format_coverage_block_reason


def _diff_meta(**overrides):
    data = {
        "diff_text": "diff content",
        "file_count": 2,
        "token_count": 50,
        "truncated": False,
        "partial_files": [],
        "skipped_budget": [],
        "skipped_binary": [],
        "skipped_unreadable": [],
    }
    data.update(overrides)
    return data


class TestCoverageGateDecision:
    def test_warn_below_minimum_does_not_block(self):
        coverage = build_coverage_report(
            ["a.py", "b.py"],
            _diff_meta(file_count=1, skipped_budget=["b.py"]),
            minimum_coverage_pct=80,
            coverage_policy="warn",
            fail_on_unreviewed_high_risk=False,
        )
        assert coverage["coverage_pct"] == 50.0
        assert coverage["action"] == "warn"
        assert coverage["reason"] == "coverage_below_minimum"

    def test_block_below_minimum_blocks(self):
        coverage = build_coverage_report(
            ["a.py", "b.py"],
            _diff_meta(file_count=1, skipped_budget=["b.py"]),
            minimum_coverage_pct=80,
            coverage_policy="block",
            fail_on_unreviewed_high_risk=False,
        )
        assert coverage["action"] == "block"

    def test_fail_closed_with_unreviewed_files_blocks(self):
        coverage = build_coverage_report(
            ["a.py", "b.py"],
            _diff_meta(file_count=1, skipped_binary=["b.py"]),
            minimum_coverage_pct=None,
            coverage_policy="fail-closed",
            fail_on_unreviewed_high_risk=False,
        )
        assert coverage["action"] == "block"
        assert coverage["reason"] == "unreviewed_files_present"

    def test_high_risk_unreviewed_blocks(self):
        coverage = build_coverage_report(
            ["src/auth.py", "src/view.py"],
            _diff_meta(file_count=1, skipped_budget=["src/auth.py"]),
            minimum_coverage_pct=None,
            coverage_policy="warn",
            fail_on_unreviewed_high_risk=True,
        )
        assert coverage["action"] == "block"
        assert coverage["reason"] == "high_risk_files_unreviewed"
        assert coverage["unreviewed_high_risk_files"] == ["src/auth.py"]

    def test_complete_coverage_passes(self):
        coverage = build_coverage_report(
            ["a.py", "b.py"],
            _diff_meta(file_count=2),
            minimum_coverage_pct=80,
            coverage_policy="block",
            fail_on_unreviewed_high_risk=True,
        )
        assert coverage["status"] == "complete"
        assert coverage["coverage_pct"] == 100.0
        assert coverage["action"] == "pass"

    def test_partial_file_counts_as_incomplete(self):
        coverage = build_coverage_report(
            ["a.py", "b.py"],
            _diff_meta(file_count=2, partial_files=["b.py"]),
            minimum_coverage_pct=80,
            coverage_policy="warn",
            fail_on_unreviewed_high_risk=False,
        )
        assert coverage["reviewed_files"] == 1
        assert coverage["coverage_pct"] == 50.0
        assert coverage["unreviewed_files"] == ["b.py"]
        assert coverage["action"] == "warn"

    def test_block_reason_is_claude_actionable(self):
        coverage = build_coverage_report(
            ["src/auth.py", "src/view.py"],
            _diff_meta(file_count=1, skipped_budget=["src/auth.py"]),
            minimum_coverage_pct=80,
            coverage_policy="block",
            fail_on_unreviewed_high_risk=True,
        )
        reason = format_coverage_block_reason(coverage)
        assert "Coverage: 50.0%" in reason
        assert "Minimum required: 80%" in reason
        assert "src/auth.py" in reason
        assert "Suggested action:" in reason


def _pass_invocation():
    invocation = MagicMock()
    invocation.exit_code = 0
    invocation.stdout = json.dumps({"result": json.dumps({
        "pass": True,
        "review_status": "completed",
        "issues": [],
        "summary": "ok",
    })})
    invocation.failure_kind = None
    invocation.stderr = ""
    return invocation


def _engine_common_patches(diff_meta, files=None, token=None):
    from cold_eyes import engine

    files = files or ["src/auth.py", "src/view.py"]
    token = token or {"ok": False, "reason": "", "note": ""}
    adapter = MagicMock()
    adapter.review.return_value = _pass_invocation()
    patches = [
        patch.object(engine, "git_cmd", return_value="/repo"),
        patch.object(engine, "collect_files", return_value=(files, set())),
        patch("cold_eyes.engine.filter_file_list", side_effect=lambda f, _=None: f),
        patch("cold_eyes.engine.rank_file_list", side_effect=lambda f, _=None: f),
        patch("cold_eyes.engine.classify_depth", return_value={
            "review_depth": "shallow",
            "why_depth_selected": "test",
        }),
        patch("cold_eyes.engine.build_diff", return_value=diff_meta),
        patch("cold_eyes.engine.load_policy", return_value={}),
        patch("cold_eyes.engine.consume_override_metadata", return_value=token),
        patch("cold_eyes.engine.log_to_history"),
    ]
    return engine, adapter, patches


class TestEngineCoverageGate:
    def test_coverage_block_not_counted_as_model_issue(self):
        diff_meta = _diff_meta(file_count=1, skipped_budget=["src/auth.py"])
        engine, adapter, patches = _engine_common_patches(diff_meta)

        with patches[0], patches[1], patches[2], patches[3], patches[4], \
             patches[5], patches[6], patches[7], patches[8]:
            result = engine.run(
                adapter=adapter,
                minimum_coverage_pct=80,
                coverage_policy="block",
                fail_on_unreviewed_high_risk=True,
            )

        assert result["action"] == "block"
        assert result["state"] == "blocked"
        assert result["final_action"] == "coverage_block"
        assert result["authority"] == "coverage_gate"
        assert result["cold_eyes_verdict"] == "incomplete"
        assert result["issues"] == []
        assert result["coverage"]["action"] == "block"
        assert result["reviewed_files"] == 1
        assert result["total_files"] == 2
        assert result["coverage_pct"] == 50.0

    def test_warn_coverage_records_warning_without_blocking(self):
        diff_meta = _diff_meta(file_count=1, skipped_budget=["src/view.py"])
        engine, adapter, patches = _engine_common_patches(diff_meta)

        with patches[0], patches[1], patches[2], patches[3], patches[4], \
             patches[5], patches[6], patches[7], patches[8]:
            result = engine.run(
                adapter=adapter,
                minimum_coverage_pct=80,
                coverage_policy="warn",
            )

        assert result["action"] == "pass"
        assert result["coverage"]["action"] == "warn"
        assert result["coverage_warning"] == "coverage_below_minimum"

    def test_override_coverage_block_becomes_override_pass(self):
        diff_meta = _diff_meta(file_count=1, skipped_budget=["src/auth.py"])
        token = {"ok": True, "reason": "acceptable_risk", "note": "manual review"}
        engine, adapter, patches = _engine_common_patches(diff_meta, token=token)

        with patches[0], patches[1], patches[2], patches[3], patches[4], \
             patches[5], patches[6], patches[7], patches[8]:
            result = engine.run(
                adapter=adapter,
                coverage_policy="fail-closed",
                fail_on_unreviewed_high_risk=True,
            )

        assert result["action"] == "pass"
        assert result["state"] == "overridden"
        assert result["final_action"] == "override_pass"
        assert result["authority"] == "human_override"
        assert result["cold_eyes_verdict"] == "incomplete"
        assert result["override_note"] == "manual review"
