import json
from datetime import datetime, timedelta, timezone

from cold_eyes.constants import STATE_BLOCKED, STATE_INFRA_FAILED, STATE_PASSED
from cold_eyes.history import runtime_status


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
        "scope": "working",
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
