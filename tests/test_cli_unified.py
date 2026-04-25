import json
import sys

from cold_eyes import cli


def test_v2_flag_is_compat_warning_and_uses_unified_run(monkeypatch, capsys):
    called = {}

    def fake_run(**kwargs):
        called.update(kwargs)
        return {"action": "pass", "state": "passed", "display": "ok", "reason": ""}

    monkeypatch.setattr(cli, "run", fake_run)
    monkeypatch.setattr(cli, "_attach_auto_tune", lambda result: result)
    monkeypatch.setattr(sys, "argv", ["cold-eyes", "run", "--v2"])

    cli.main()

    captured = capsys.readouterr()
    assert "--v2 is retired; using unified v1" in captured.err
    assert "hook_input_path" in called
    assert json.loads(captured.out)["state"] == "passed"
