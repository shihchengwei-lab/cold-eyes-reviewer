import subprocess
from unittest.mock import MagicMock

from cold_eyes.local_checks import (
    compact_history,
    normalize_check_mode,
    normalize_timeout,
    repair_lines,
    run_local_checks,
    select_checks,
)


def test_normalize_check_mode_defaults_to_auto():
    assert normalize_check_mode(None) == "auto"
    assert normalize_check_mode("auto") == "auto"
    assert normalize_check_mode("off") == "off"
    assert normalize_check_mode("bad-value") == "auto"


def test_normalize_timeout_is_bounded():
    assert normalize_timeout("30") == 30
    assert normalize_timeout("0") == 120
    assert normalize_timeout("9999") == 600
    assert normalize_timeout("oops") == 120


def test_select_checks_for_python_source(tmp_path):
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "app.py").write_text("print('ok')\n", encoding="utf-8")

    selected = select_checks(["src/app.py"], repo_root=str(tmp_path))
    ids = [entry["check_id"] for entry in selected]

    assert ids == ["lint_checker", "type_checker"]
    assert selected[0]["targets"] == ["src/app.py"]
    assert selected[1]["targets"] == ["src/app.py"]


def test_select_checks_for_high_risk_python_source_with_tests(tmp_path):
    (tmp_path / "src").mkdir()
    (tmp_path / "tests").mkdir()
    (tmp_path / "src" / "auth.py").write_text("AUTH = True\n", encoding="utf-8")

    selected = select_checks(["src/auth.py"], repo_root=str(tmp_path))
    ids = [entry["check_id"] for entry in selected]

    assert "lint_checker" in ids
    assert "type_checker" in ids
    assert "test_runner" in ids


def test_high_risk_python_source_uses_mapped_pytest_target(tmp_path):
    (tmp_path / "src").mkdir()
    (tmp_path / "tests").mkdir()
    (tmp_path / "src" / "auth.py").write_text("AUTH = True\n", encoding="utf-8")
    (tmp_path / "tests" / "test_auth.py").write_text("def test_auth(): pass\n", encoding="utf-8")

    selected = select_checks(["src/auth.py"], repo_root=str(tmp_path))
    test_runner = next(entry for entry in selected if entry["check_id"] == "test_runner")

    assert test_runner["targets"] == ["tests/test_auth.py"]


def test_high_risk_python_source_falls_back_to_full_pytest_when_unmapped(tmp_path):
    (tmp_path / "src").mkdir()
    (tmp_path / "tests").mkdir()
    (tmp_path / "src" / "auth.py").write_text("AUTH = True\n", encoding="utf-8")

    selected = select_checks(["src/auth.py"], repo_root=str(tmp_path))
    test_runner = next(entry for entry in selected if entry["check_id"] == "test_runner")

    assert "targets" not in test_runner


def test_select_checks_for_dependency_file():
    selected = select_checks(["pyproject.toml"])

    assert selected == [{
        "check_id": "build_checker",
        "blocking": "hard",
        "reason": "python dependency/build config changed",
    }]


def test_off_mode_runs_nothing(tmp_path):
    result = run_local_checks(["src/app.py"], mode="off", repo_root=str(tmp_path))

    assert result == {
        "mode": "off",
        "results": [],
        "hard_failed": False,
        "warnings": [],
    }


def test_missing_tool_skips_without_hard_failure(tmp_path, monkeypatch):
    monkeypatch.setattr("cold_eyes.local_checks.shutil.which", lambda _cmd: None)

    result = run_local_checks(["src/app.py"], mode="auto", repo_root=str(tmp_path))

    assert result["hard_failed"] is False
    assert result["results"][0]["status"] == "skip"
    assert result["results"][0]["infrastructure"] is True
    assert "tool not available" in result["warnings"][0]


def test_pytest_failure_is_hard_failure(tmp_path, monkeypatch):
    (tmp_path / "tests").mkdir()
    monkeypatch.setattr("cold_eyes.local_checks.shutil.which", lambda _cmd: "tool")
    proc = MagicMock()
    proc.stdout = "FAILED tests/test_app.py::test_guard - AssertionError\n"
    proc.stderr = ""
    proc.returncode = 1
    monkeypatch.setattr("cold_eyes.local_checks.subprocess.run", lambda *a, **k: proc)

    result = run_local_checks(["tests/test_app.py"], mode="auto", repo_root=str(tmp_path))

    assert result["hard_failed"] is True
    assert result["results"][0]["check_id"] == "test_runner"
    assert result["results"][0]["status"] == "fail"


def test_ruff_failure_is_soft_only(tmp_path, monkeypatch):
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "app.py").write_text("import os\n", encoding="utf-8")
    monkeypatch.setattr("cold_eyes.local_checks.shutil.which", lambda _cmd: "tool")
    proc = MagicMock()
    proc.stdout = "src/app.py:1:1: F401 unused import\n"
    proc.stderr = ""
    proc.returncode = 1
    monkeypatch.setattr("cold_eyes.local_checks.subprocess.run", lambda *a, **k: proc)

    result = run_local_checks(["src/app.py"], mode="auto", repo_root=str(tmp_path))

    assert result["hard_failed"] is False
    assert result["results"][0]["check_id"] == "lint_checker"
    assert result["results"][0]["blocking"] == "soft"
    assert result["results"][0]["status"] == "fail"


def test_soft_checks_target_changed_python_files(tmp_path, monkeypatch):
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "app.py").write_text("print('ok')\n", encoding="utf-8")
    monkeypatch.setattr("cold_eyes.local_checks.shutil.which", lambda _cmd: "tool")
    commands = []
    proc = MagicMock()
    proc.stdout = ""
    proc.stderr = ""
    proc.returncode = 0

    def _capture(command, **_kwargs):
        commands.append(command)
        return proc

    monkeypatch.setattr("cold_eyes.local_checks.subprocess.run", _capture)

    run_local_checks(["src/app.py"], mode="auto", repo_root=str(tmp_path))

    assert commands[0] == ["ruff", "check", "src/app.py"]
    assert commands[1] == ["mypy", "src/app.py"]


def test_timeout_warns_without_hard_failure(tmp_path, monkeypatch):
    monkeypatch.setattr("cold_eyes.local_checks.shutil.which", lambda _cmd: "tool")

    def _timeout(*_args, **_kwargs):
        raise subprocess.TimeoutExpired(cmd="pytest", timeout=1)

    monkeypatch.setattr("cold_eyes.local_checks.subprocess.run", _timeout)

    result = run_local_checks(["tests/test_app.py"], mode="auto", repo_root=str(tmp_path))

    assert result["hard_failed"] is False
    assert result["results"][0]["status"] == "error"
    assert result["results"][0]["infrastructure"] is True
    assert "timed out" in result["warnings"][0]


def test_repair_lines_include_failed_checks():
    checks = {
        "results": [{
            "check_id": "test_runner",
            "status": "fail",
            "blocking": "hard",
            "findings": [{
                "location": "tests/test_app.py::test_guard",
                "message": "AssertionError",
            }],
            "infrastructure": False,
        }]
    }

    lines = repair_lines(checks)

    assert "Local checks to fix:" in lines
    assert any("tests/test_app.py::test_guard" in line for line in lines)


def test_compact_history_limits_check_details():
    checks = {
        "mode": "auto",
        "hard_failed": True,
        "warnings": ["w"] * 10,
        "results": [{
            "check_id": "test_runner",
            "status": "fail",
            "blocking": "hard",
            "duration_ms": 5,
            "findings": [{"message": "x"}],
            "infrastructure": False,
        }],
    }

    result = compact_history(checks)

    assert result["hard_failed"] is True
    assert result["results"][0]["finding_count"] == 1
    assert len(result["warnings"]) == 5
