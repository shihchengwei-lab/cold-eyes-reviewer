import json
from datetime import datetime, timedelta, timezone

from cold_eyes.constants import (
    STATE_BLOCKED,
    STATE_INFRA_FAILED,
    STATE_PASSED,
    STATE_SKIPPED,
)
from cold_eyes.history import format_human_status, runtime_status


def _iso(dt):
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")


def _write_entry(path, *, cwd, state, timestamp=None, **extra):
    entry = {
        "version": 2,
        "timestamp": timestamp or _iso(datetime.now(timezone.utc)),
        "cwd": str(cwd),
        "mode": "block",
        "model": "sonnet",
        "state": state,
        "min_confidence": "medium",
        "scope": "staged",
        "schema_version": 1,
        "review": None,
    }
    entry.update(extra)
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry) + "\n")


def test_status_unknown_when_no_history_for_repo(tmp_path):
    history = tmp_path / "history.jsonl"

    result = runtime_status(str(history), cwd=str(tmp_path))

    assert result["ok"] is False
    assert result["health"] == "unknown"
    assert result["last_seen"] is None


def test_status_treats_block_as_healthy_runtime(tmp_path):
    history = tmp_path / "history.jsonl"
    _write_entry(
        history,
        cwd=tmp_path,
        state=STATE_BLOCKED,
        final_action="block",
        reason="secret detail should stay out of status",
    )

    result = runtime_status(str(history), cwd=str(tmp_path))

    assert result["ok"] is True
    assert result["health"] == "ok"
    assert result["message"] == "Cold Eyes is running normally."
    assert "reason" not in result


def test_status_reports_infra_failure_as_problem(tmp_path):
    history = tmp_path / "history.jsonl"
    _write_entry(history, cwd=tmp_path, state=STATE_INFRA_FAILED, failure_kind="timeout")

    result = runtime_status(str(history), cwd=str(tmp_path))

    assert result["ok"] is False
    assert result["health"] == "problem"


def test_status_reports_stale_history_as_unknown(tmp_path):
    history = tmp_path / "history.jsonl"
    old = _iso(datetime.now(timezone.utc) - timedelta(hours=48))
    _write_entry(history, cwd=tmp_path, state=STATE_PASSED, timestamp=old)

    result = runtime_status(str(history), cwd=str(tmp_path), stale_after_hours=24)

    assert result["ok"] is False
    assert result["health"] == "unknown"


def test_status_summarizes_local_check_health_without_findings(tmp_path):
    history = tmp_path / "history.jsonl"
    _write_entry(
        history,
        cwd=tmp_path,
        state=STATE_PASSED,
        checks={
            "mode": "auto",
            "hard_failed": False,
            "results": [{
                "check_id": "type_checker",
                "status": "skip",
                "blocking": "soft",
                "duration_ms": 0,
                "finding_count": 0,
                "infrastructure": True,
            }],
            "warnings": ["type_checker skipped: tool not available"],
        },
    )

    result = runtime_status(str(history), cwd=str(tmp_path))

    assert result["ok"] is True
    assert result["checks"]["status"] == "warning"
    assert "tool not available" not in result["checks"]["message"]


def _doctor(*checks):
    return {"checks": list(checks), "all_ok": all(c.get("status") != "fail" for c in checks)}


def _check(name, status="ok", detail=""):
    return {"name": name, "status": status, "detail": detail}


def _human_status(health="ok", target=None, **extra):
    status = {
        "health": health,
        "last_seen": "2026-04-26T00:00:00Z",
        "last_state": STATE_PASSED,
        "mode": "block",
        "scope": "staged",
        "target": target or {
            "scope": "staged",
            "review_file_count": 2,
            "unreviewed_unstaged_files": [],
            "unreviewed_untracked_files": [],
            "unreviewed_partial_stage_files": [],
            "policy_action": "pass",
        },
    }
    status.update(extra)
    return status


def test_human_status_ready():
    text = format_human_status(
        _human_status(),
        _doctor(
            _check("settings_hook"),
            _check("claude_cli"),
            _check("git_repo"),
            _check("health_schedule"),
        ),
    )

    assert "Cold Eyes: READY" in text
    assert "Review target: 2 staged files" in text


def test_human_status_attention_for_target_warning():
    target = {
        "scope": "staged",
        "review_file_count": 0,
        "unreviewed_unstaged_files": ["app.py"],
        "unreviewed_untracked_files": [],
        "unreviewed_partial_stage_files": [],
        "policy_action": "warn",
    }
    text = format_human_status(
        _human_status(health="attention", target=target, last_state=STATE_SKIPPED),
        _doctor(_check("settings_hook"), _check("claude_cli"), _check("git_repo")),
    )

    assert "Cold Eyes: ATTENTION" in text
    assert "Not reviewed: 1 unstaged files, 0 untracked files" in text
    assert "Next action: stage intended changes" in text


def test_human_status_not_protecting_for_gate_failure_without_low_level_detail():
    text = format_human_status(
        _human_status(health="ok"),
        _doctor(
            _check("settings_hook"),
            _check("claude_cli", "fail", "secret low-level stack trace"),
            _check("git_repo"),
        ),
    )

    assert "Cold Eyes: NOT_PROTECTING" in text
    assert "secret low-level stack trace" not in text


def test_human_status_unknown_without_history():
    text = format_human_status(
        _human_status(health="unknown", last_seen=None, last_state=None),
        _doctor(_check("settings_hook"), _check("claude_cli"), _check("git_repo")),
    )

    assert "Cold Eyes: UNKNOWN" in text
