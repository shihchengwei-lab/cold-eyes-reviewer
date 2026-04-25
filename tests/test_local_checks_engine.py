import json

from cold_eyes import constants
from cold_eyes import engine
from cold_eyes.claude import MockAdapter


def _diff_meta():
    return {
        "diff_text": "diff --git a/tests/test_app.py b/tests/test_app.py\n+assert True\n",
        "file_count": 1,
        "token_count": 20,
        "truncated": False,
        "partial_files": [],
        "skipped_budget": [],
        "skipped_binary": [],
        "skipped_unreadable": [],
    }


def _clean_response():
    return json.dumps({
        "schema_version": 1,
        "review_status": "completed",
        "pass": True,
        "summary": "clean",
        "issues": [],
    })


def _blocking_response():
    return json.dumps({
        "schema_version": 1,
        "review_status": "completed",
        "pass": False,
        "summary": "risk found",
        "issues": [{
            "severity": "critical",
            "confidence": "high",
            "category": "correctness",
            "file": "src/app.py",
            "check": "missing guard",
            "verdict": "unsafe",
            "fix": "restore guard",
            "evidence": ["diff removes guard"],
        }],
    })


def _patch_engine(monkeypatch, tmp_path, checks_summary, files=None):
    monkeypatch.setattr(engine, "git_cmd", lambda *args: str(tmp_path))
    monkeypatch.setattr(engine, "collect_files", lambda scope, base=None: (files or ["tests/test_app.py"], set()))
    monkeypatch.setattr(engine, "build_diff", lambda *args, **kwargs: _diff_meta())
    monkeypatch.setattr(engine, "run_local_checks", lambda *args, **kwargs: checks_summary)
    monkeypatch.setattr(constants, "HISTORY_FILE", str(tmp_path / "history.jsonl"))


def test_hard_local_check_failure_blocks_in_block_mode(monkeypatch, tmp_path):
    checks = {
        "mode": "auto",
        "hard_failed": True,
        "warnings": [],
        "results": [{
            "check_id": "test_runner",
            "status": "fail",
            "blocking": "hard",
            "findings": [{"location": "tests/test_app.py::test_guard", "message": "AssertionError"}],
            "raw_output": "",
            "infrastructure": False,
        }],
    }
    _patch_engine(monkeypatch, tmp_path, checks)

    result = engine.run(mode="block", adapter=MockAdapter(_clean_response()), checks="auto")

    assert result["action"] == "block"
    assert result["final_action"] == "check_block"
    assert result["authority"] == "local_checks"
    assert result["checks"]["hard_failed"] is True
    assert result["protection"]["block_type"] == "check_block"


def test_soft_local_check_failure_does_not_block(monkeypatch, tmp_path):
    checks = {
        "mode": "auto",
        "hard_failed": False,
        "warnings": [],
        "results": [{
            "check_id": "lint_checker",
            "status": "fail",
            "blocking": "soft",
            "findings": [{"file": "src/app.py", "line": "1", "message": "F401 unused import"}],
            "raw_output": "",
            "infrastructure": False,
        }],
    }
    _patch_engine(monkeypatch, tmp_path, checks, files=["src/app.py"])

    result = engine.run(mode="block", adapter=MockAdapter(_clean_response()), checks="auto")

    assert result["action"] == "pass"
    assert result["checks"]["results"][0]["blocking"] == "soft"
    assert "protection" not in result


def test_existing_llm_block_keeps_authority_and_adds_check_task(monkeypatch, tmp_path):
    checks = {
        "mode": "auto",
        "hard_failed": False,
        "warnings": [],
        "results": [{
            "check_id": "lint_checker",
            "status": "fail",
            "blocking": "soft",
            "findings": [{"file": "src/app.py", "line": "1", "message": "F401 unused import"}],
            "raw_output": "",
            "infrastructure": False,
        }],
    }
    _patch_engine(monkeypatch, tmp_path, checks, files=["src/app.py"])

    result = engine.run(mode="block", adapter=MockAdapter(_blocking_response()), checks="auto")

    assert result["action"] == "block"
    assert result["authority"] != "local_checks"
    assert result["protection"]["block_type"] == "finding_block"
    assert "Local checks to fix" in result["protection"]["agent_task"]
    assert "lint_checker" in result["protection"]["agent_task"]
