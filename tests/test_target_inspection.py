import subprocess

from cold_eyes.target import inspect_review_target


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


def test_staged_only_is_clean_target(tmp_path, monkeypatch):
    _init_repo(tmp_path)
    monkeypatch.chdir(tmp_path)
    (tmp_path / "app.py").write_text("value = 2\n", encoding="utf-8")
    _git(tmp_path, "add", "app.py")

    target = inspect_review_target("staged")

    assert target["review_files"] == ["app.py"]
    assert target["staged_count"] == 1
    assert target["unreviewed_count"] == 0
    assert target["target_integrity"] == "clean"


def test_unstaged_only_is_unreviewed_in_staged_scope(tmp_path, monkeypatch):
    _init_repo(tmp_path)
    monkeypatch.chdir(tmp_path)
    (tmp_path / "app.py").write_text("value = 2\n", encoding="utf-8")

    target = inspect_review_target("staged")

    assert target["review_file_count"] == 0
    assert target["unreviewed_unstaged_files"] == ["app.py"]
    assert target["target_integrity"] == "dirty"


def test_partial_stage_detects_same_file_in_staged_and_unstaged(tmp_path, monkeypatch):
    _init_repo(tmp_path)
    monkeypatch.chdir(tmp_path)
    (tmp_path / "app.py").write_text("value = 2\n", encoding="utf-8")
    _git(tmp_path, "add", "app.py")
    (tmp_path / "app.py").write_text("value = 3\n", encoding="utf-8")

    target = inspect_review_target("staged")

    assert target["partial_stage_files"] == ["app.py"]
    assert target["unreviewed_partial_stage_files"] == ["app.py"]
    assert target["target_integrity"] == "partial"


def test_untracked_high_risk_file_is_not_reviewed_in_staged_scope(tmp_path, monkeypatch):
    _init_repo(tmp_path)
    monkeypatch.chdir(tmp_path)
    (tmp_path / "auth_config.py").write_text("TOKEN = 'x'\n", encoding="utf-8")

    target = inspect_review_target("staged")

    assert target["unreviewed_untracked_files"] == ["auth_config.py"]
    assert target["high_risk_unreviewed_files"] == ["auth_config.py"]


def test_ignored_files_are_not_counted_as_unreviewed(tmp_path, monkeypatch):
    _init_repo(tmp_path)
    monkeypatch.chdir(tmp_path)
    ignore = tmp_path / ".cold-review-ignore"
    ignore.write_text("secret.py\n", encoding="utf-8")
    _git(tmp_path, "add", ".cold-review-ignore")
    _git(tmp_path, "commit", "-m", "ignore")
    (tmp_path / "secret.py").write_text("TOKEN = 'x'\n", encoding="utf-8")

    target = inspect_review_target("staged", ignore_file=str(ignore))

    assert target["untracked_files"] == []
    assert target["unreviewed_files"] == []
