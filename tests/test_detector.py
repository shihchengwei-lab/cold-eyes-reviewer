"""Tests for the detector module (state/invariant + repo-specific)."""

import os
import sys
import pytest

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from cold_eyes.detector import (
    detect_state_signals,
    classify_repo_type,
    get_detector_focus,
    build_detector_hints,
)


# ---------------------------------------------------------------------------
# detect_state_signals
# ---------------------------------------------------------------------------

class TestDetectStateSignals:
    def test_state_assignment(self):
        diff = "+    self.state = 'active'\n"
        signals = detect_state_signals(diff)
        assert len(signals) == 1
        assert signals[0]["signal_type"] == "state_assignment"

    def test_status_assignment(self):
        diff = "+    order.status = COMPLETED\n"
        signals = detect_state_signals(diff)
        assert len(signals) == 1
        assert signals[0]["signal_type"] == "state_assignment"

    def test_removed_line_detected(self):
        diff = "-    self.state = 'pending'\n"
        signals = detect_state_signals(diff)
        assert len(signals) == 1

    def test_transition_call(self):
        diff = "+    self.set_state('approved')\n"
        signals = detect_state_signals(diff)
        assert len(signals) == 1
        assert signals[0]["signal_type"] == "transition_call"

    def test_set_status(self):
        diff = "+    update_status(order_id, 'shipped')\n"
        signals = detect_state_signals(diff)
        assert len(signals) == 1
        assert signals[0]["signal_type"] == "transition_call"

    def test_setState_camelCase(self):
        diff = "+    setState({ loading: true })\n"
        signals = detect_state_signals(diff)
        assert len(signals) == 1
        assert signals[0]["signal_type"] == "transition_call"

    def test_move_to(self):
        diff = "+    order.move_to('cancelled')\n"
        signals = detect_state_signals(diff)
        assert len(signals) == 1
        assert signals[0]["signal_type"] == "transition_call"

    def test_state_check_if(self):
        diff = "+    if order.state == 'active':\n"
        signals = detect_state_signals(diff)
        assert len(signals) == 1
        assert signals[0]["signal_type"] == "state_check"

    def test_state_check_elif(self):
        diff = "+    elif status == PENDING:\n"
        signals = detect_state_signals(diff)
        assert len(signals) == 1
        assert signals[0]["signal_type"] == "state_check"

    def test_state_check_switch(self):
        diff = "+    switch (state) {\n"
        signals = detect_state_signals(diff)
        assert len(signals) == 1
        assert signals[0]["signal_type"] == "state_check"

    def test_fsm_pattern(self):
        diff = "+    fsm = FiniteStateMachine()\n"
        signals = detect_state_signals(diff)
        assert len(signals) == 1
        assert signals[0]["signal_type"] == "fsm_pattern"

    def test_state_machine_pattern(self):
        diff = "+    machine = state_machine.create()\n"
        signals = detect_state_signals(diff)
        assert len(signals) == 1
        assert signals[0]["signal_type"] == "fsm_pattern"

    def test_workflow_step(self):
        diff = "+    next_step = workflow_step(current)\n"
        signals = detect_state_signals(diff)
        assert len(signals) == 1
        assert signals[0]["signal_type"] == "fsm_pattern"

    def test_rollback(self):
        diff = "+    rollback(transaction_id)\n"
        signals = detect_state_signals(diff)
        assert len(signals) == 1
        assert signals[0]["signal_type"] == "rollback_pattern"

    def test_compensate(self):
        diff = "+    compensate_failed_step(step)\n"
        signals = detect_state_signals(diff)
        assert len(signals) == 1
        assert signals[0]["signal_type"] == "rollback_pattern"

    def test_context_lines_ignored(self):
        diff = " context line with state = foo\n"
        signals = detect_state_signals(diff)
        assert len(signals) == 0

    def test_header_lines_ignored(self):
        diff = "+++ a/state.py\n--- b/state.py\n@@ -1,3 +1,3 @@\n"
        signals = detect_state_signals(diff)
        assert len(signals) == 0

    def test_empty_diff(self):
        assert detect_state_signals("") == []

    def test_no_state_patterns(self):
        diff = "+    x = 42\n+    print(hello)\n"
        signals = detect_state_signals(diff)
        assert len(signals) == 0

    def test_multiple_signals(self):
        diff = (
            "+    self.state = 'active'\n"
            "+    if status == PENDING:\n"
            "+    rollback(tx)\n"
        )
        signals = detect_state_signals(diff)
        assert len(signals) == 3
        types = {s["signal_type"] for s in signals}
        assert "state_assignment" in types
        assert "state_check" in types
        assert "rollback_pattern" in types

    def test_line_truncated_at_120(self):
        long_line = "+    self.state = " + "x" * 200
        signals = detect_state_signals(long_line)
        assert len(signals) == 1
        assert len(signals[0]["line"]) == 120

    def test_one_signal_per_line(self):
        # Line matches both state_assignment and transition_call keywords
        diff = "+    set_state(self.state = 'new')\n"
        signals = detect_state_signals(diff)
        # Only one signal should be emitted (first match wins)
        assert len(signals) == 1


# ---------------------------------------------------------------------------
# classify_repo_type
# ---------------------------------------------------------------------------

class TestClassifyRepoType:
    def test_web_backend(self):
        files = ["src/routes/user.py", "src/controllers/auth.py"]
        rtype, scores = classify_repo_type(files)
        assert rtype == "web_backend"
        assert scores["web_backend"] >= 2

    def test_sdk_library(self):
        files = ["sdk/client.py", "lib/utils.py", "setup.py"]
        rtype, scores = classify_repo_type(files)
        assert rtype == "sdk_library"

    def test_db_data(self):
        files = ["models/user.py", "migrations/001_add_users.py"]
        rtype, scores = classify_repo_type(files)
        assert rtype == "db_data"

    def test_infra_async(self):
        files = ["worker/processor.py", "queue/handler.py", "docker/Dockerfile"]
        rtype, scores = classify_repo_type(files)
        assert rtype == "infra_async"

    def test_general_no_indicators(self):
        files = ["utils.py", "main.py", "README.md"]
        rtype, scores = classify_repo_type(files)
        assert rtype == "general"

    def test_empty_files(self):
        rtype, scores = classify_repo_type([])
        assert rtype == "general"

    def test_backslash_normalized(self):
        files = ["src\\routes\\user.py"]
        rtype, _ = classify_repo_type(files)
        assert rtype == "web_backend"

    def test_highest_score_wins(self):
        files = [
            "src/routes/api.py",
            "src/controller/main.py",
            "src/handler/ws.py",
            "models/user.py",
        ]
        rtype, scores = classify_repo_type(files)
        assert rtype == "web_backend"
        assert scores["web_backend"] > scores["db_data"]

    def test_tie_picks_one(self):
        # One file each — max picks the first one in dict iteration
        files = ["routes/index.py", "models/user.py"]
        rtype, scores = classify_repo_type(files)
        assert rtype in ("web_backend", "db_data")

    def test_celery_detected(self):
        files = ["celery_app.py", "tasks/send_email.py"]
        rtype, _ = classify_repo_type(files)
        assert rtype == "infra_async"

    def test_pyproject_toml(self):
        files = ["pyproject.toml"]
        rtype, _ = classify_repo_type(files)
        assert rtype == "sdk_library"


# ---------------------------------------------------------------------------
# get_detector_focus
# ---------------------------------------------------------------------------

class TestGetDetectorFocus:
    def test_web_backend(self):
        focus = get_detector_focus("web_backend")
        assert focus["name"] == "auth / permission"
        assert len(focus["checks"]) > 0

    def test_sdk_library(self):
        focus = get_detector_focus("sdk_library")
        assert focus["name"] == "contract break"

    def test_db_data(self):
        focus = get_detector_focus("db_data")
        assert focus["name"] == "migration / persistence"

    def test_infra_async(self):
        focus = get_detector_focus("infra_async")
        assert focus["name"] == "concurrency / staleness"

    def test_general(self):
        focus = get_detector_focus("general")
        assert focus["name"] == "general"
        assert focus["checks"] == []

    def test_unknown_falls_to_general(self):
        focus = get_detector_focus("nonexistent")
        assert focus["name"] == "general"


# ---------------------------------------------------------------------------
# build_detector_hints (integration)
# ---------------------------------------------------------------------------

class TestBuildDetectorHints:
    def test_state_signals_produce_hints(self):
        diff = "+    self.state = 'active'\n+    if status == PENDING:\n"
        files = ["src/main.py"]
        result = build_detector_hints(diff, files)
        assert "[Cold Eyes: State/Invariant Detector]" in result["hint_text"]
        assert len(result["state_signals"]) == 2
        assert result["repo_type"] == "general"

    def test_repo_specific_hints(self):
        diff = "+    x = 42\n"
        files = ["src/routes/user.py", "src/controller/auth.py"]
        result = build_detector_hints(diff, files)
        assert "[Cold Eyes: Repo-Specific Detector" in result["hint_text"]
        assert "auth / permission" in result["hint_text"]
        assert result["repo_type"] == "web_backend"
        assert result["detector_focus"] == "auth / permission"

    def test_both_hints(self):
        diff = "+    self.state = 'active'\n"
        files = ["models/order.py", "migrations/002.py"]
        result = build_detector_hints(diff, files)
        assert "State/Invariant Detector" in result["hint_text"]
        assert "Repo-Specific Detector" in result["hint_text"]
        assert result["repo_type"] == "db_data"

    def test_no_signals_no_hints(self):
        diff = "+    x = 42\n"
        files = ["utils.py"]
        result = build_detector_hints(diff, files)
        assert result["hint_text"] == ""
        assert result["state_signals"] == []
        assert result["repo_type"] == "general"
        assert result["detector_focus"] == "general"

    def test_many_signals_capped_at_5(self):
        lines = [f"+    self.state = '{i}'\n" for i in range(10)]
        diff = "".join(lines)
        result = build_detector_hints(diff, ["main.py"])
        assert "... and 5 more" in result["hint_text"]
        assert len(result["state_signals"]) == 10

    def test_hint_text_ends_with_newline(self):
        diff = "+    self.state = 'x'\n"
        result = build_detector_hints(diff, ["main.py"])
        assert result["hint_text"].endswith("\n")

    def test_empty_diff_empty_files(self):
        result = build_detector_hints("", [])
        assert result["hint_text"] == ""
        assert result["repo_type"] == "general"

    def test_sdk_focus_checks(self):
        diff = "+    x = 1\n"
        files = ["sdk/client.py", "lib/core.py"]
        result = build_detector_hints(diff, files)
        assert "contract break" in result["hint_text"]

    def test_infra_focus_checks(self):
        diff = "+    x = 1\n"
        files = ["worker/main.py", "queue/handler.py"]
        result = build_detector_hints(diff, files)
        assert "concurrency / staleness" in result["hint_text"]
