import subprocess

from cold_eyes.doctor import run_doctor_fix
from cold_eyes.health import (
    agent_notice,
    install_health_schedule,
    remove_health_schedule,
)


def test_agent_notice_only_problem_stays_quiet_when_healthy(tmp_path, monkeypatch):
    monkeypatch.setattr("cold_eyes.health.runtime_status", lambda **_kwargs: {"health": "ok"})
    monkeypatch.setattr("cold_eyes.health.run_doctor", lambda **_kwargs: {"all_ok": True, "checks": []})

    result = agent_notice(
        repo_root=str(tmp_path),
        notice_dir=str(tmp_path),
        write=True,
        only_problem=True,
    )

    assert result["ok"] is True
    assert result["emitted"] is False
    assert result["level"] == "ok"
    assert not (tmp_path / "cold-review-agent-notice.txt").exists()
    assert not (tmp_path / "cold-review-agent-notice.json").exists()


def test_agent_notice_writes_low_detail_problem_notice(tmp_path, monkeypatch):
    monkeypatch.setattr("cold_eyes.health.runtime_status", lambda **_kwargs: {"health": "ok"})
    monkeypatch.setattr(
        "cold_eyes.health.run_doctor",
        lambda **_kwargs: {
            "all_ok": False,
            "checks": [
                {"name": "claude_cli", "status": "fail", "detail": "secret low-level detail"},
                {"name": "python", "status": "ok", "detail": "3.12"},
            ],
        },
    )

    result = agent_notice(
        repo_root=str(tmp_path),
        notice_dir=str(tmp_path),
        write=True,
        only_problem=True,
    )

    text = (tmp_path / "cold-review-agent-notice.txt").read_text(encoding="utf-8")
    assert result["ok"] is False
    assert result["emitted"] is True
    assert result["level"] == "gate_unreliable"
    assert "claude_cli" in text
    assert "secret low-level detail" not in text


def test_agent_notice_marks_missing_schedule_separately(tmp_path, monkeypatch):
    monkeypatch.setattr("cold_eyes.health.runtime_status", lambda **_kwargs: {"health": "ok"})
    monkeypatch.setattr(
        "cold_eyes.health.run_doctor",
        lambda **_kwargs: {
            "all_ok": True,
            "checks": [{
                "name": "health_schedule",
                "status": "info",
                "detail": "health notice schedule not found: Cold Eyes Reviewer Health Notice",
            }],
        },
    )

    result = agent_notice(repo_root=str(tmp_path), notice_dir=str(tmp_path), only_problem=True)

    assert result["ok"] is False
    assert result["emitted"] is True
    assert result["level"] == "schedule_missing"
    assert "background health schedule is missing" in result["message"]


def test_agent_notice_clears_old_notice_when_healthy(tmp_path, monkeypatch):
    (tmp_path / "cold-review-agent-notice.txt").write_text("old\n", encoding="utf-8")
    (tmp_path / "cold-review-agent-notice.json").write_text("{}\n", encoding="utf-8")
    monkeypatch.setattr("cold_eyes.health.runtime_status", lambda **_kwargs: {"health": "ok"})
    monkeypatch.setattr("cold_eyes.health.run_doctor", lambda **_kwargs: {"all_ok": True, "checks": []})

    agent_notice(repo_root=str(tmp_path), notice_dir=str(tmp_path), write=True, only_problem=True)

    assert not (tmp_path / "cold-review-agent-notice.txt").exists()
    assert not (tmp_path / "cold-review-agent-notice.json").exists()


def test_doctor_fix_installs_missing_health_schedule(tmp_path, monkeypatch):
    monkeypatch.setattr(
        "cold_eyes.health.health_schedule_status",
        lambda: {"status": "info", "detail": "health notice schedule not found"},
    )
    monkeypatch.setattr(
        "cold_eyes.health.install_health_schedule",
        lambda **_kwargs: {"ok": True, "supported": True},
    )
    monkeypatch.setattr(
        "cold_eyes.health.agent_notice",
        lambda **_kwargs: {"emitted": False},
    )

    result = run_doctor_fix(scripts_dir=str(tmp_path), repo_root=str(tmp_path))

    assert "health_schedule: installed Agent health notice schedule" in result["fixed"]
    assert "agent_notice: cleared stale notice" in result["fixed"]


def test_install_health_schedule_writes_runner_and_uses_interval(tmp_path, monkeypatch):
    calls = []

    def fake_run(args):
        calls.append(args)
        return subprocess.CompletedProcess(args, 0, "ok", "")

    monkeypatch.setattr("cold_eyes.health._scheduler_command", lambda: ["schtasks"])
    monkeypatch.setattr("cold_eyes.health._run_scheduler", fake_run)
    monkeypatch.setattr("cold_eyes.health._to_windows_path", lambda path: str(path).replace("/", "\\"))

    result = install_health_schedule(
        repo_root=str(tmp_path / "repo"),
        scripts_dir=str(tmp_path / "scripts"),
        every_days=14,
        time_of_day="08:30",
    )

    runner = tmp_path / "scripts" / "cold-review-health-notice.cmd"
    runner_text = runner.read_text(encoding="utf-8")
    assert result["ok"] is True
    assert result["every_days"] == 14
    assert "/MO" in calls[0]
    assert "14" in calls[0]
    assert "--only-problem" in runner_text
    assert "agent-notice" in runner_text


def test_remove_health_schedule_deletes_runner(tmp_path, monkeypatch):
    calls = []
    scripts = tmp_path / "scripts"
    scripts.mkdir()
    runner = scripts / "cold-review-health-notice.cmd"
    runner.write_text("@echo off\n", encoding="utf-8")

    def fake_run(args):
        calls.append(args)
        return subprocess.CompletedProcess(args, 0, "deleted", "")

    monkeypatch.setattr("cold_eyes.health._scheduler_command", lambda: ["schtasks"])
    monkeypatch.setattr("cold_eyes.health._run_scheduler", fake_run)

    result = remove_health_schedule(scripts_dir=str(scripts))

    assert result["ok"] is True
    assert "/Delete" in calls[0]
    assert not runner.exists()
