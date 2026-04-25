"""Tests for gate governance fields in history and reports."""

import json

from cold_eyes import constants
from cold_eyes.constants import STATE_BLOCKED, STATE_OVERRIDDEN, STATE_PASSED
from cold_eyes.history import log_to_history, quality_report


def test_log_to_history_writes_gate_fields(tmp_path, monkeypatch):
    history_path = tmp_path / "history.jsonl"
    monkeypatch.setattr(constants, "HISTORY_FILE", str(history_path))
    coverage = {
        "action": "block",
        "coverage_pct": 50.0,
        "unreviewed_files": ["src/auth.py"],
    }

    log_to_history(
        "/repo",
        "block",
        "sonnet",
        STATE_BLOCKED,
        reason="coverage",
        coverage=coverage,
        cold_eyes_verdict="incomplete",
        final_action="coverage_block",
        authority="coverage_gate",
        override_note="manual note",
        checks={"mode": "auto", "hard_failed": False, "results": []},
    )

    entry = json.loads(history_path.read_text().strip())
    assert entry["coverage"] == coverage
    assert entry["cold_eyes_verdict"] == "incomplete"
    assert entry["final_action"] == "coverage_block"
    assert entry["authority"] == "coverage_gate"
    assert entry["override_note"] == "manual note"
    assert entry["checks"]["mode"] == "auto"


def test_quality_report_gate_quality_counts_new_actions(tmp_path):
    history_path = tmp_path / "history.jsonl"
    entries = [
        {"state": STATE_PASSED, "final_action": "pass"},
        {"state": STATE_OVERRIDDEN, "final_action": "override_pass",
         "override_reason": "false_positive"},
        {"state": STATE_OVERRIDDEN, "final_action": "override_pass",
         "override_reason": "acceptable_risk"},
        {"state": STATE_BLOCKED, "final_action": "coverage_block"},
        {"state": "infra_failed", "cold_eyes_verdict": "infra_failed"},
    ]
    history_path.write_text("\n".join(json.dumps(e) for e in entries) + "\n")

    report = quality_report(str(history_path))
    gate_quality = report["gate_quality"]
    assert gate_quality["pass_count"] == 1
    assert gate_quality["block_count"] == 0
    assert gate_quality["override_count"] == 2
    assert gate_quality["false_positive_override_count"] == 1
    assert gate_quality["accepted_risk_count"] == 1
    assert gate_quality["coverage_block_count"] == 1
    assert gate_quality["coverage_block_rate"] == 0.2
    assert gate_quality["infra_failure_count"] == 1


def test_quality_report_reads_old_entries(tmp_path):
    history_path = tmp_path / "history.jsonl"
    entries = [
        {"state": STATE_PASSED},
        {"state": STATE_OVERRIDDEN, "override_reason": "acceptable_risk"},
        {"state": STATE_BLOCKED},
    ]
    history_path.write_text("\n".join(json.dumps(e) for e in entries) + "\n")

    report = quality_report(str(history_path))
    gate_quality = report["gate_quality"]
    assert gate_quality["pass_count"] == 1
    assert gate_quality["override_count"] == 1
    assert gate_quality["block_count"] == 1
