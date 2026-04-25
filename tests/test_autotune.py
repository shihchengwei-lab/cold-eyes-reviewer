"""Tests for conservative auto-tuning."""

import json
from datetime import datetime, timezone

from cold_eyes import config as config_mod
from cold_eyes.autotune import auto_tune, maybe_auto_tune, write_auto_policy
from cold_eyes.config import AUTO_POLICY_FILENAME, POLICY_FILENAME, load_policy
from cold_eyes.constants import STATE_BLOCKED, STATE_PASSED
from cold_eyes.history import log_to_history


def _write_entry(
    path,
    state=STATE_PASSED,
    depth="deep",
    duration_ms=30_000,
    tokens=12_000,
    files=3,
    final_action=None,
    coverage=None,
    protection=None,
):
    entry = {
        "version": 2,
        "timestamp": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "cwd": "/repo",
        "mode": "block",
        "model": "opus",
        "state": state,
        "review_depth": depth,
        "duration_ms": duration_ms,
        "diff_stats": {"tokens": tokens, "files": files},
        "review": {"issues": []},
    }
    if final_action:
        entry["final_action"] = final_action
    if coverage:
        entry["coverage"] = coverage
    if protection:
        entry["protection"] = protection
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry) + "\n")


def test_auto_tune_waits_for_minimum_samples(tmp_path):
    history = tmp_path / "history.jsonl"
    _write_entry(history)

    result = auto_tune(str(history), min_samples=2)

    assert result["recommended_profile"] == "observe"
    assert result["changes"] == {}
    assert result["write_eligible"] is False


def test_auto_tune_reduces_context_only_for_clean_slow_deep_history(tmp_path):
    history = tmp_path / "history.jsonl"
    for _ in range(5):
        _write_entry(history, duration_ms=30_000, tokens=12_000)

    result = auto_tune(str(history), min_samples=5)

    assert result["recommended_profile"] == "fast-safe"
    assert result["changes"]["context_tokens"] == 1200
    assert result["changes"]["block_threshold"] == "critical"
    assert result["changes"]["confidence"] == "medium"
    assert result["changes"]["fail_on_unreviewed_high_risk"] is True
    assert "max_tokens" not in result["changes"]


def test_auto_tune_holds_quality_when_recent_blocks_exist(tmp_path):
    history = tmp_path / "history.jsonl"
    for _ in range(4):
        _write_entry(history)
    _write_entry(history, state=STATE_BLOCKED)

    result = auto_tune(str(history), min_samples=5)

    assert result["recommended_profile"] == "hold-quality"
    assert result["changes"]["context_tokens"] == 2000
    assert any("recent blocks" in reason for reason in result["reasons"])


def test_auto_tune_holds_quality_when_high_risk_files_were_unreviewed(tmp_path):
    history = tmp_path / "history.jsonl"
    for _ in range(4):
        _write_entry(history)
    _write_entry(
        history,
        coverage={"unreviewed_high_risk_files": ["src/auth.py"]},
    )

    result = auto_tune(str(history), min_samples=5)

    assert result["recommended_profile"] == "hold-quality"
    assert result["changes"]["context_tokens"] == 2000
    assert result["changes"]["coverage_policy"] == "block"
    assert any("high-risk files" in reason for reason in result["reasons"])


def test_auto_tune_holds_quality_when_intent_mismatch_blocks_occur(tmp_path):
    history = tmp_path / "history.jsonl"
    for _ in range(4):
        _write_entry(history)
    _write_entry(
        history,
        protection={"block_type": "intent_mismatch"},
    )

    result = auto_tune(str(history), min_samples=5)

    assert result["recommended_profile"] == "hold-quality"
    assert result["changes"]["context_tokens"] == 2000
    assert any("intent mismatch" in reason for reason in result["reasons"])


def test_write_auto_policy_is_low_priority_to_manual_policy(tmp_path):
    write_auto_policy(
        str(tmp_path),
        {
            "context_tokens": 1200,
            "block_threshold": "critical",
            "confidence": "medium",
            "fail_on_unreviewed_high_risk": True,
        },
    )
    auto_text = (tmp_path / AUTO_POLICY_FILENAME).read_text(encoding="utf-8")
    assert "context_tokens: 1200" in auto_text
    assert "fail_on_unreviewed_high_risk: true" in auto_text

    (tmp_path / POLICY_FILENAME).write_text(
        "context_tokens: 2000\nconfidence: high\n",
        encoding="utf-8",
    )
    policy = load_policy(str(tmp_path))

    assert policy["context_tokens"] == 2000
    assert policy["confidence"] == "high"
    assert policy["block_threshold"] == "critical"


def test_maybe_auto_tune_writes_policy_and_state_without_repo_file(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    history = tmp_path / "history.jsonl"
    state = tmp_path / "state.json"
    output = tmp_path / "auto.yml"
    for _ in range(5):
        _write_entry(history, duration_ms=30_000, tokens=12_000)

    result = maybe_auto_tune(
        str(repo),
        history_path=str(history),
        state_path=str(state),
        output_path=str(output),
        interval_hours=24,
    )

    assert result["action"] == "auto-tune-auto"
    assert result["written"] is True
    assert result["recommended_profile"] == "fast-safe"
    assert output.is_file()
    assert state.is_file()
    assert not (repo / AUTO_POLICY_FILENAME).exists()


def test_maybe_auto_tune_respects_interval(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    history = tmp_path / "history.jsonl"
    state = tmp_path / "state.json"
    output = tmp_path / "auto.yml"
    for _ in range(5):
        _write_entry(history, duration_ms=30_000, tokens=12_000)

    first = maybe_auto_tune(
        str(repo), history_path=str(history), state_path=str(state),
        output_path=str(output), interval_hours=24,
    )
    second = maybe_auto_tune(
        str(repo), history_path=str(history), state_path=str(state),
        output_path=str(output), interval_hours=24,
    )

    assert first["written"] is True
    assert second["action"] == "auto-tune-skip"
    assert second["reason"] == "interval"


def test_load_policy_reads_home_scoped_auto_policy(tmp_path, monkeypatch):
    auto_dir = tmp_path / "home-auto"
    monkeypatch.setattr(config_mod, "AUTO_POLICY_DIR", str(auto_dir))
    repo = tmp_path / "repo"
    repo.mkdir()
    path = config_mod.user_auto_policy_path(str(repo))
    write_auto_policy(str(repo), {"context_tokens": 1200}, output_path=path)

    policy = load_policy(str(repo))

    assert policy["context_tokens"] == 1200


def test_log_to_history_records_duration(tmp_path, monkeypatch):
    history = tmp_path / "history.jsonl"
    monkeypatch.setattr("cold_eyes.constants.HISTORY_FILE", str(history))

    log_to_history("/repo", "block", "opus", STATE_PASSED, duration_ms=123)

    entry = json.loads(history.read_text(encoding="utf-8").strip())
    assert entry["duration_ms"] == 123
