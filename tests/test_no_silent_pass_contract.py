import json
import subprocess

import cold_eyes.constants as constants
from cold_eyes.engine import run
from cold_eyes.history import runtime_status


def _git(cwd, *args):
    return subprocess.run(
        ["git", *args],
        cwd=cwd,
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )


def _init_repo(tmp_path):
    _git(tmp_path, "init")
    _git(tmp_path, "config", "user.email", "cold@example.test")
    _git(tmp_path, "config", "user.name", "Cold Eyes")
    (tmp_path / "app.py").write_text("value = 1\n", encoding="utf-8")
    _git(tmp_path, "add", "app.py")
    _git(tmp_path, "commit", "-m", "initial")


class _NoModelAdapter:
    def review(self, *_args, **_kwargs):
        raise AssertionError("model should not be called")


class _CleanAdapter:
    def __init__(self):
        self.call_count = 0
        self.last_diff = ""

    def review(self, diff, *_args, **_kwargs):
        self.call_count += 1
        self.last_diff = diff
        return type(
            "Invocation",
            (),
            {
                "stdout": json.dumps({
                    "type": "result",
                    "result": json.dumps({
                        "pass": True,
                        "issues": [],
                        "summary": "clean",
                    }),
                }),
                "stderr": "",
                "exit_code": 0,
                "failure_kind": None,
            },
        )()


class _BadJsonAdapter:
    def review(self, *_args, **_kwargs):
        return type(
            "Invocation",
            (),
            {"stdout": "not json", "stderr": "", "exit_code": 0, "failure_kind": None},
        )()


class _MutatingCleanAdapter(_CleanAdapter):
    def __init__(self, path):
        super().__init__()
        self.path = path

    def review(self, *args, **kwargs):
        result = super().review(*args, **kwargs)
        self.path.write_text("value = 3\n", encoding="utf-8")
        return result


def test_no_file_changes_skips_without_model(tmp_path, monkeypatch):
    _init_repo(tmp_path)
    monkeypatch.chdir(tmp_path)
    history_path = tmp_path / "history.jsonl"
    monkeypatch.setattr(constants, "HISTORY_FILE", str(history_path))

    result = run(adapter=_NoModelAdapter(), checks="off")

    assert result["gate_state"] == "skipped_no_change"
    assert result["state"] == "skipped"
    entry = json.loads(history_path.read_text(encoding="utf-8").splitlines()[-1])
    assert entry["gate_state"] == "skipped_no_change"
    assert entry["envelope"]["schema_version"] == 2
    assert entry["envelope"]["review_required"] is False


def test_same_protected_envelope_uses_cache_without_model(tmp_path, monkeypatch):
    _init_repo(tmp_path)
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(constants, "HISTORY_FILE", str(tmp_path / "history.jsonl"))
    (tmp_path / "app.py").write_text("value = 2\n", encoding="utf-8")
    _git(tmp_path, "add", "app.py")

    first_adapter = _CleanAdapter()
    first = run(adapter=first_adapter, checks="off")
    second = run(adapter=_NoModelAdapter(), checks="off")

    assert first["gate_state"] == "protected"
    assert first_adapter.call_count == 1
    assert second["gate_state"] == "protected_cached"


def test_unstaged_source_delta_is_reviewed_not_silent_pass(tmp_path, monkeypatch):
    _init_repo(tmp_path)
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(constants, "HISTORY_FILE", str(tmp_path / "history.jsonl"))
    (tmp_path / "app.py").write_text("value = 2\n", encoding="utf-8")

    adapter = _CleanAdapter()
    result = run(adapter=adapter, checks="off")

    assert result["gate_state"] == "protected"
    assert adapter.call_count == 1
    assert "value = 2" in adapter.last_diff


def test_untracked_source_delta_is_reviewed_not_silent_pass(tmp_path, monkeypatch):
    _init_repo(tmp_path)
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(constants, "HISTORY_FILE", str(tmp_path / "history.jsonl"))
    (tmp_path / "new_module.py").write_text("value = 2\n", encoding="utf-8")

    adapter = _CleanAdapter()
    result = run(adapter=adapter, checks="off")

    assert result["gate_state"] == "protected"
    assert adapter.call_count == 1
    assert "NEW FILE: new_module.py" in adapter.last_diff


def test_staged_docs_plus_unstaged_source_does_not_skip_safe(tmp_path, monkeypatch):
    _init_repo(tmp_path)
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(constants, "HISTORY_FILE", str(tmp_path / "history.jsonl"))
    (tmp_path / "README.md").write_text("docs\n", encoding="utf-8")
    _git(tmp_path, "add", "README.md")
    (tmp_path / "app.py").write_text("value = 2\n", encoding="utf-8")

    adapter = _CleanAdapter()
    result = run(adapter=adapter, checks="off")

    assert result["gate_state"] == "protected"
    assert adapter.call_count == 1
    assert "app.py" in adapter.last_diff


def test_docs_only_is_skipped_safe_without_model(tmp_path, monkeypatch):
    _init_repo(tmp_path)
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(constants, "HISTORY_FILE", str(tmp_path / "history.jsonl"))
    (tmp_path / "README.md").write_text("docs\n", encoding="utf-8")
    _git(tmp_path, "add", "README.md")

    result = run(adapter=_NoModelAdapter(), checks="off")

    assert result["gate_state"] == "skipped_safe"


def test_high_risk_untracked_over_budget_blocks_without_model(tmp_path, monkeypatch):
    _init_repo(tmp_path)
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(constants, "HISTORY_FILE", str(tmp_path / "history.jsonl"))
    (tmp_path / "auth_config.py").write_text("TOKEN = 'secret'\n", encoding="utf-8")

    result = run(
        adapter=_NoModelAdapter(),
        checks="off",
        max_shadow_delta_bytes=1,
    )

    assert result["action"] == "block"
    assert result["gate_state"] == "blocked_unreviewed_delta"


def test_malformed_json_blocks_when_review_required(tmp_path, monkeypatch):
    _init_repo(tmp_path)
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(constants, "HISTORY_FILE", str(tmp_path / "history.jsonl"))
    (tmp_path / "app.py").write_text("value = 2\n", encoding="utf-8")
    _git(tmp_path, "add", "app.py")

    result = run(adapter=_BadJsonAdapter(), checks="off")

    assert result["action"] == "block"
    assert result["gate_state"] == "blocked_infra"


def test_lock_active_with_changed_source_blocks(tmp_path, monkeypatch):
    _init_repo(tmp_path)
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(constants, "HISTORY_FILE", str(tmp_path / "history.jsonl"))
    (tmp_path / "app.py").write_text("value = 2\n", encoding="utf-8")

    result = run(adapter=_NoModelAdapter(), checks="off", lock_active=True)

    assert result["action"] == "block"
    assert result["gate_state"] == "blocked_lock_active"


def test_file_change_during_review_blocks_stale_review(tmp_path, monkeypatch):
    _init_repo(tmp_path)
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(constants, "HISTORY_FILE", str(tmp_path / "history.jsonl"))
    (tmp_path / "app.py").write_text("value = 2\n", encoding="utf-8")
    _git(tmp_path, "add", "app.py")

    result = run(adapter=_MutatingCleanAdapter(tmp_path / "app.py"), checks="off")

    assert result["action"] == "block"
    assert result["gate_state"] == "blocked_stale_review"


def test_mode_off_records_off_explicit_without_model(tmp_path, monkeypatch):
    _init_repo(tmp_path)
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(constants, "HISTORY_FILE", str(tmp_path / "history.jsonl"))

    result = run(mode="off", adapter=_NoModelAdapter(), checks="off")

    assert result["gate_state"] == "off_explicit"
    assert result["state"] == "skipped"


def test_schema_v1_history_remains_readable(tmp_path, monkeypatch):
    _init_repo(tmp_path)
    monkeypatch.chdir(tmp_path)
    history_path = tmp_path / "history.jsonl"
    monkeypatch.setattr(constants, "HISTORY_FILE", str(history_path))
    history_path.write_text(
        json.dumps({
            "version": 1,
            "timestamp": "2026-04-25T00:00:00Z",
            "cwd": str(tmp_path),
            "mode": "block",
            "model": "sonnet",
            "state": "passed",
            "schema_version": 1,
            "review": None,
        }) + "\n",
        encoding="utf-8",
    )

    status = runtime_status()

    assert status["action"] == "status"
    assert status["ok"] is True
    assert status["last_state"] == "passed"
