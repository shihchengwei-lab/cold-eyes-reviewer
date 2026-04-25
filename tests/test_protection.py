import json

from cold_eyes.history import log_to_history
from cold_eyes.policy import apply_policy
from cold_eyes.protection import attach_protection, history_summary


def _critical_review(category="correctness", evidence=None):
    if evidence is None:
        evidence = ["diff line shows guard removed"]
    return {
        "review_status": "completed",
        "pass": False,
        "summary": "risk found",
        "issues": [{
            "severity": "critical",
            "confidence": "high",
            "category": category,
            "file": "src/app.py",
            "line_hint": "L42",
            "check": "changed guard behavior",
            "verdict": "this can skip validation",
            "fix": "restore the guard before returning",
            "evidence": evidence,
        }],
    }


def test_block_finding_gets_agent_task_and_user_message():
    review = _critical_review()
    outcome = apply_policy(review, "block", "critical", False, "medium")

    protected = attach_protection(outcome, review=review)

    assert protected["action"] == "block"
    assert protected["protection"]["agent_task"]
    assert protected["protection"]["user_message"]
    assert protected["protection"]["block_type"] == "finding_block"
    assert "Message to relay to the user" in protected["reason"]
    assert "Agent repair task" in protected["reason"]
    assert "src/app.py" in protected["reason"]


def test_coverage_block_gets_repair_task_for_unreviewed_high_risk_files():
    outcome = {
        "action": "block",
        "state": "blocked",
        "final_action": "coverage_block",
        "reason": "coverage below minimum",
        "coverage": {
            "action": "block",
            "unreviewed_high_risk_files": ["src/auth.py"],
            "unreviewed_files": ["src/auth.py"],
        },
    }

    protected = attach_protection(outcome)

    assert protected["protection"]["block_type"] == "coverage_block"
    assert "高風險檔案沒有被完整審到" in protected["protection"]["risk_summary"][0]
    assert "src/auth.py" in protected["protection"]["agent_task"]
    assert "coverage below minimum" in protected["reason"]


def test_intent_issue_without_diff_evidence_does_not_block():
    review = _critical_review(category="intent", evidence=[])

    outcome = apply_policy(review, "block", "critical", False, "medium")

    assert outcome["action"] == "pass"
    assert outcome["state"] == "passed"


def test_intent_issue_with_diff_evidence_can_block():
    review = _critical_review(category="intent", evidence=["diff line removes requested CLI flag"])

    outcome = apply_policy(review, "block", "critical", False, "medium")
    protected = attach_protection(outcome, review=review)

    assert protected["action"] == "block"
    assert protected["protection"]["block_type"] == "intent_mismatch"
    assert "偏離" in protected["protection"]["risk_summary"][0]


def test_history_summary_keeps_protection_compact(tmp_path, monkeypatch):
    from cold_eyes import constants

    history = tmp_path / "history.jsonl"
    monkeypatch.setattr(constants, "HISTORY_FILE", str(history))
    protected = attach_protection(
        apply_policy(_critical_review(), "block", "critical", False, "medium"),
        review=_critical_review(),
    )

    log_to_history(
        "/repo",
        "block",
        "sonnet",
        "blocked",
        protection=history_summary(protected["protection"]),
    )

    entry = json.loads(history.read_text(encoding="utf-8").strip())
    assert entry["protection"]["agent_task"] is True
    assert entry["protection"]["user_message"] is True
    assert "agent_task" in entry["protection"]
    assert "Fix:" not in json.dumps(entry["protection"], ensure_ascii=False)
