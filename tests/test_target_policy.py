import subprocess
import json

import cold_eyes.constants as constants
from cold_eyes.engine import run
from cold_eyes.target import evaluate_target_policy


def _target(**overrides):
    base = {
        "scope": "staged",
        "review_files": [],
        "review_file_count": 0,
        "unreviewed_unstaged_files": [],
        "unreviewed_untracked_files": [],
        "unreviewed_partial_stage_files": [],
        "unreviewed_files": [],
        "high_risk_unreviewed_files": [],
        "high_risk_partial_stage_files": [],
    }
    base.update(overrides)
    return base


def _git(cwd, *args):
    return subprocess.run(
        ["git", *args],
        cwd=cwd,
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )


def _init_repo(tmp_path, filename="app.py"):
    _git(tmp_path, "init")
    _git(tmp_path, "config", "user.email", "cold@example.test")
    _git(tmp_path, "config", "user.name", "Cold Eyes")
    (tmp_path / filename).write_text("value = 1\n", encoding="utf-8")
    _git(tmp_path, "add", filename)
    _git(tmp_path, "commit", "-m", "initial")


def test_dirty_worktree_warns_by_default():
    decision = evaluate_target_policy(
        _target(
            unreviewed_unstaged_files=["src/app.py"],
            unreviewed_files=["src/app.py"],
        )
    )

    assert decision["action"] == "warn"
    assert decision["warnings"][0]["kind"] == "dirty_worktree"


def test_untracked_warns_by_default():
    decision = evaluate_target_policy(
        _target(
            unreviewed_untracked_files=["src/new.py"],
            unreviewed_files=["src/new.py"],
        )
    )

    assert decision["action"] == "warn"
    assert decision["warnings"][0]["kind"] == "untracked"


def test_partial_stage_blocks_high_risk_by_default():
    decision = evaluate_target_policy(
        _target(
            unreviewed_unstaged_files=["src/auth.py"],
            unreviewed_partial_stage_files=["src/auth.py"],
            unreviewed_files=["src/auth.py"],
            high_risk_unreviewed_files=["src/auth.py"],
            high_risk_partial_stage_files=["src/auth.py"],
        )
    )

    assert decision["action"] == "block"
    assert decision["reason"] == "partial_stage"


def test_high_risk_untracked_blocks_when_policy_is_block_high_risk():
    decision = evaluate_target_policy(
        _target(
            unreviewed_untracked_files=["src/auth.py"],
            unreviewed_files=["src/auth.py"],
            high_risk_unreviewed_files=["src/auth.py"],
        ),
        untracked_policy="block-high-risk",
    )

    assert decision["action"] == "block"
    assert decision["blocks"][0]["kind"] == "untracked"


class _NoModelAdapter:
    def review(self, *_args, **_kwargs):
        raise AssertionError("model should not be called")


class _CleanAdapter:
    def __init__(self):
        self.call_count = 0

    def review(self, *_args, **_kwargs):
        self.call_count += 1
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


def test_engine_reviews_partial_high_risk_delta(tmp_path, monkeypatch):
    _init_repo(tmp_path, filename="auth.py")
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(constants, "HISTORY_FILE", str(tmp_path / "history.jsonl"))
    (tmp_path / "auth.py").write_text("value = 2\n", encoding="utf-8")
    _git(tmp_path, "add", "auth.py")
    (tmp_path / "auth.py").write_text("value = 3\n", encoding="utf-8")

    adapter = _CleanAdapter()
    result = run(adapter=adapter, checks="off")

    assert result["action"] == "pass"
    assert result["gate_state"] == "protected"
    assert adapter.call_count == 1
    assert result["target"]["policy_action"] == "block"


def test_engine_reviews_dirty_unstaged_delta(tmp_path, monkeypatch):
    _init_repo(tmp_path)
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(constants, "HISTORY_FILE", str(tmp_path / "history.jsonl"))
    (tmp_path / "app.py").write_text("value = 2\n", encoding="utf-8")

    adapter = _CleanAdapter()
    result = run(adapter=adapter, checks="off")

    assert result["gate_state"] == "protected"
    assert adapter.call_count == 1
    assert result["target"]["policy_action"] == "warn"
    assert result["target_warning"] == "dirty_worktree_unreviewed"


def test_target_module_is_deployed():
    assert "cold_eyes/target.py" in constants.DEPLOY_FILES
    assert "cold_eyes/envelope.py" in constants.DEPLOY_FILES
