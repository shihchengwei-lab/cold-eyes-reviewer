"""Tests for cold_eyes/helper.py — shell-facing commands (parse-hook, log-state)."""

import json
import os
import subprocess
import sys

import pytest

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HELPER_SCRIPT = os.path.join(PROJECT_ROOT, "cold_eyes", "helper.py")


def run_helper(command, stdin_data=None, extra_args=None):
    """Run helper.py as subprocess, return (stdout, stderr, returncode)."""
    args = [sys.executable, HELPER_SCRIPT, command] + (extra_args or [])
    r = subprocess.run(
        args,
        input=stdin_data,
        capture_output=True,
        text=True,
        cwd=PROJECT_ROOT,
        env={**os.environ, "PYTHONIOENCODING": "utf-8"},
    )
    return r.stdout.strip(), r.stderr.strip(), r.returncode


class TestParseHook:
    def test_active_true(self):
        data = json.dumps({"stop_hook_active": True})
        stdout, _, rc = run_helper("parse-hook", stdin_data=data)
        assert rc == 0
        assert stdout == "true"

    def test_active_false(self):
        data = json.dumps({"stop_hook_active": False})
        stdout, _, rc = run_helper("parse-hook", stdin_data=data)
        assert rc == 0
        assert stdout == "false"

    def test_missing_field(self):
        data = json.dumps({"other": 123})
        stdout, _, rc = run_helper("parse-hook", stdin_data=data)
        assert rc == 0
        assert stdout == "false"


class TestLogState:
    def test_runs_without_error(self):
        _, _, rc = run_helper("log-state", extra_args=[".", "block", "opus", "skipped", "no changes"])
        assert rc == 0

    def test_override_reason_arg(self):
        _, _, rc = run_helper("log-state", extra_args=[".", "block", "opus", "overridden", "bypass", "false_positive"])
        assert rc == 0
