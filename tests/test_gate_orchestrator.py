"""Tests for cold_eyes.gates.orchestrator."""

import json
from unittest.mock import MagicMock, patch

from cold_eyes.gates.orchestrator import run_gates
from cold_eyes.session.schema import create_session


def _mock_engine_outcome(action="pass", state="passed", issues=None):
    return {
        "action": action,
        "state": state,
        "review": {"issues": issues or []},
    }


class TestRunGates:
    def test_empty_gates(self):
        s = create_session("test")
        results = run_gates(s, [])
        assert results == []

    def test_llm_review_gate_wraps_engine(self):
        s = create_session("test")
        outcome = _mock_engine_outcome()
        with patch("cold_eyes.gates.orchestrator.engine_run", return_value=outcome, create=True):
            # Use direct mock of the import
            from cold_eyes.gates import orchestrator
            original = None
            try:
                original = getattr(orchestrator, '_run_llm_review')
            except AttributeError:
                pass

            # Simpler: mock engine.run at module level
            with patch("cold_eyes.engine.run", return_value=outcome):
                results = run_gates(s, [{"gate_id": "llm_review", "blocking": "hard"}])

        assert len(results) == 1
        assert results[0]["gate_name"] == "llm_review"
        assert results[0]["status"] == "pass"
        assert results[0]["blocking_mode"] == "hard"

    def test_llm_review_blocked(self):
        s = create_session("test")
        outcome = _mock_engine_outcome(
            action="block", state="blocked",
            issues=[{"check": "bug", "severity": "critical", "confidence": "high",
                     "file": "x.py", "verdict": "bad"}],
        )
        with patch("cold_eyes.engine.run", return_value=outcome):
            results = run_gates(s, [{"gate_id": "llm_review", "blocking": "hard"}])
        assert results[0]["status"] == "fail"
        assert len(results[0]["findings"]) == 1

    def test_external_gate_pass(self):
        s = create_session("test")
        mock_proc = MagicMock()
        mock_proc.stdout = "5 passed in 0.3s\n"
        mock_proc.stderr = ""
        mock_proc.returncode = 0

        with patch("cold_eyes.gates.orchestrator.subprocess.run", return_value=mock_proc):
            results = run_gates(s, [{"gate_id": "test_runner", "blocking": "hard"}])
        assert len(results) == 1
        assert results[0]["status"] == "pass"

    def test_external_gate_failure(self):
        s = create_session("test")
        mock_proc = MagicMock()
        mock_proc.stdout = "FAILED tests/test_x.py::test_a - assert False\n1 failed\n"
        mock_proc.stderr = ""
        mock_proc.returncode = 1

        with patch("cold_eyes.gates.orchestrator.subprocess.run", return_value=mock_proc):
            results = run_gates(s, [{"gate_id": "test_runner", "blocking": "hard"}])
        assert results[0]["status"] == "fail"
        assert any(f["type"] == "test_failure" for f in results[0]["findings"])

    def test_external_gate_timeout(self):
        s = create_session("test")
        import subprocess
        with patch("cold_eyes.gates.orchestrator.subprocess.run",
                   side_effect=subprocess.TimeoutExpired(cmd="pytest", timeout=5)):
            results = run_gates(s, [{"gate_id": "test_runner", "blocking": "soft"}], timeout=5)
        assert results[0]["status"] == "fail"
        assert "timed out" in results[0]["raw_output"]

    def test_external_gate_tool_not_found(self):
        s = create_session("test")
        with patch("cold_eyes.gates.orchestrator.subprocess.run",
                   side_effect=FileNotFoundError("not found")):
            results = run_gates(s, [{"gate_id": "lint_checker", "blocking": "soft"}])
        assert results[0]["status"] == "fail"
        assert "not found" in results[0]["raw_output"]

    def test_multiple_gates_sequential(self):
        s = create_session("test")
        mock_proc = MagicMock()
        mock_proc.stdout = "ok"
        mock_proc.stderr = ""
        mock_proc.returncode = 0

        outcome = _mock_engine_outcome()
        with patch("cold_eyes.engine.run", return_value=outcome), \
             patch("cold_eyes.gates.orchestrator.subprocess.run", return_value=mock_proc):
            gates = [
                {"gate_id": "llm_review", "blocking": "hard"},
                {"gate_id": "test_runner", "blocking": "hard"},
            ]
            results = run_gates(s, gates)
        assert len(results) == 2
        assert results[0]["gate_name"] == "llm_review"
        assert results[1]["gate_name"] == "test_runner"

    def test_duration_is_recorded(self):
        s = create_session("test")
        outcome = _mock_engine_outcome()
        with patch("cold_eyes.engine.run", return_value=outcome):
            results = run_gates(s, [{"gate_id": "llm_review", "blocking": "soft"}])
        assert results[0]["duration_ms"] >= 0
