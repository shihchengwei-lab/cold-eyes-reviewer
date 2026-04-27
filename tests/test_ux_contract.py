"""UX hardening contract tests for v2.1.0+.

Cold Eyes is a gate. When it blocks, the agent must fix the current diff
first; the user-facing talking points come last and only when a user update
is genuinely necessary. These tests pin down those invariants without
changing the v2.1.0 gate behavior itself.
"""

from __future__ import annotations

import re

from cold_eyes.policy import apply_policy
from cold_eyes.protection import attach_protection, build_protection, format_agent_reason


_RAW_ENGLISH_BLOCK_PHRASES = [
    "source/config delta was not reviewed",
    "files changed while Cold Eyes was reviewing",
    "review was required but reviewer infrastructure failed",
    "review was required but another review was already active",
]

_MACHINE_RERUN_FIELD_HEADERS = [
    "Owner:",
    "Required:",
    "Trigger:",
    "Memory policy:",
    "User action required:",
]


def _critical_review(category: str = "correctness", evidence=None):
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


def _block_outcomes() -> dict[str, dict]:
    return {
        "infra_block": {
            "action": "block",
            "state": "blocked",
            "final_action": "infra_block",
            "reason": "infra failed",
            "envelope": {"unreviewed": {"files": ["src/app.py"]}},
        },
        "stale_review_block": {
            "action": "block",
            "state": "blocked",
            "final_action": "stale_review_block",
            "reason": "tree changed during review",
            "envelope": {"review_target": {"files": ["src/app.py"]}},
        },
        "unreviewed_delta_block": {
            "action": "block",
            "state": "blocked",
            "final_action": "unreviewed_delta_block",
            "reason": "delta unreviewed",
            "envelope": {"unreviewed": {"files": ["src/app.py"]}},
        },
        "lock_block": {
            "action": "block",
            "state": "blocked",
            "final_action": "lock_block",
            "reason": "another review still active",
            "envelope": {"review_target": {"files": ["src/app.py"]}},
        },
    }


# --- 1. Chinese user_message must not leak raw English block reason -----------

def test_chinese_user_message_never_contains_raw_english_block_phrase():
    for outcome in _block_outcomes().values():
        protected = attach_protection(dict(outcome), language="zh")
        message = protected["protection"]["user_message"]
        for phrase in _RAW_ENGLISH_BLOCK_PHRASES:
            assert phrase not in message, (
                f"Chinese user_message leaked raw English phrase {phrase!r} "
                f"for block_type={protected['protection']['block_type']}: "
                f"{message!r}"
            )


def test_chinese_user_message_uses_chinese_for_finding_block():
    review = _critical_review()
    outcome = apply_policy(review, "block", "critical", False, "medium")
    protected = attach_protection(outcome, review=review, language="zh")
    message = protected["protection"]["user_message"]
    for phrase in _RAW_ENGLISH_BLOCK_PHRASES:
        assert phrase not in message
    assert re.search(r"[一-鿿]", message), (
        f"Expected Chinese characters in user_message, got: {message!r}"
    )


# --- 2. Agent repair task must come before user-facing talking points ---------

def _section_positions(reason: str) -> dict[str, int]:
    return {
        "agent_repair": reason.index("Agent repair task:"),
        "rerun_protocol": reason.index("Fresh-review rerun protocol:"),
        "user_talking": reason.index("User-facing talking points"),
    }


def test_agent_repair_task_is_ordered_before_user_talking_points():
    review = _critical_review()
    outcome = apply_policy(review, "block", "critical", False, "medium")
    protected = attach_protection(outcome, review=review, language="zh")
    positions = _section_positions(protected["reason"])
    assert positions["agent_repair"] < positions["rerun_protocol"], (
        f"Agent repair task must come before rerun protocol: {positions}"
    )
    assert positions["rerun_protocol"] < positions["user_talking"], (
        f"Rerun protocol must come before user-facing talking points: {positions}"
    )


def test_agent_repair_task_is_ordered_before_user_talking_points_for_every_block_type():
    for block_type, outcome in _block_outcomes().items():
        protected = attach_protection(dict(outcome), language="zh")
        positions = _section_positions(protected["reason"])
        assert positions["agent_repair"] < positions["user_talking"], (
            f"Agent repair task must precede user talking points for {block_type}: "
            f"{positions}"
        )


# --- 3. User-facing talking points must not ask the user to run commands -----

_USER_COMMAND_TRIGGERS = [
    "請你執行",
    "請執行",
    "請手動",
    "請跑",
    "請你跑",
    "請你輸入",
    "請輸入",
    "請複製",
    "請貼上",
    "請你貼",
    "請你複製",
    "麻煩你執行",
    "麻煩你跑",
    "你需要手動",
    "請按",
    "please run",
    "please execute",
    "please paste",
    "please copy",
    "you need to run",
    "you must run",
]


def test_user_talking_points_never_ask_user_to_run_a_command():
    review = _critical_review()
    outcome = apply_policy(review, "block", "critical", False, "medium")
    cases = [attach_protection(outcome, review=review, language="zh")]
    for outcome in _block_outcomes().values():
        cases.append(attach_protection(dict(outcome), language="zh"))
        cases.append(attach_protection(dict(outcome), language="english"))

    for protected in cases:
        message = protected["protection"]["user_message"]
        lower = message.lower()
        for trigger in _USER_COMMAND_TRIGGERS:
            assert trigger.lower() not in lower, (
                f"User-facing talking points should not ask the user to run commands; "
                f"found {trigger!r} in {message!r} for block_type="
                f"{protected['protection']['block_type']}"
            )


# --- 4. Infra / stale / unreviewed / lock all have plain Chinese -------------

def test_block_types_all_have_plain_chinese_risk_summary_and_user_message():
    chinese_char = re.compile(r"[一-鿿]")
    for block_type, outcome in _block_outcomes().items():
        protected = attach_protection(dict(outcome), language="zh")
        risks = protected["protection"]["risk_summary"]
        message = protected["protection"]["user_message"]
        assert risks, f"{block_type} should have a risk_summary"
        assert all(chinese_char.search(r) for r in risks), (
            f"{block_type} risk_summary must be plain Chinese, got {risks!r}"
        )
        for phrase in _RAW_ENGLISH_BLOCK_PHRASES:
            assert phrase not in " ".join(risks), (
                f"{block_type} risk_summary leaked raw English {phrase!r}"
            )
            assert phrase not in message, (
                f"{block_type} user_message leaked raw English {phrase!r}"
            )


# --- 5. Hook reason omits machine rerun fields, JSON keeps them --------------

def test_hook_reason_omits_machine_rerun_protocol_fields():
    review = _critical_review()
    outcome = apply_policy(review, "block", "critical", False, "medium")
    protected = attach_protection(outcome, review=review, language="zh")
    reason = protected["reason"]
    for header in _MACHINE_RERUN_FIELD_HEADERS:
        assert header not in reason, (
            f"Hook reason should not surface machine rerun field {header!r}; "
            f"reason was: {reason!r}"
        )


def test_protection_json_still_carries_structured_rerun_protocol_fields():
    review = _critical_review()
    outcome = apply_policy(review, "block", "critical", False, "medium")
    protected = attach_protection(outcome, review=review, language="zh")
    rerun = protected["protection"]["rerun_protocol"]
    # Structured fields stay available for tooling / history, even though the
    # hook reason no longer prints them as "Owner: ..." lines.
    assert rerun["owner"] == "main_agent"
    assert rerun["required"] is True
    assert rerun["trigger"] == "next_stop_hook"
    assert rerun["memory_policy"] == "fresh_review_only"
    assert rerun["user_action_required"] is False
    assert isinstance(rerun["steps"], list) and rerun["steps"]


# --- 6. intent_mismatch decision boundary is surfaced -------------------------

def test_intent_mismatch_repair_step_states_decision_boundary():
    review = _critical_review(category="intent", evidence=["diff line removes requested CLI flag"])
    outcome = apply_policy(review, "block", "critical", False, "medium")
    protected = attach_protection(outcome, review=review, language="zh")
    rerun_steps = " ".join(protected["protection"]["rerun_protocol"]["steps"])
    agent_task = protected["protection"]["agent_task"]

    assert protected["protection"]["block_type"] == "intent_mismatch"
    assert "technically fixable" in rerun_steps.lower(), (
        f"intent_mismatch rerun step should state the decision boundary, got: {rerun_steps!r}"
    )
    assert "decision boundary" in agent_task.lower(), (
        f"intent_mismatch agent_task should state the decision boundary, got: {agent_task!r}"
    )


# --- 7. v2.1.0 engine / no-silent-pass gate behavior is unchanged ------------

def test_v210_engine_stages_no_silent_pass_gate_behavior_unchanged():
    """Smoke check: the policy/gate still produces the same actions for the
    canonical cases. attach_protection is a presentation layer; it must not
    mutate the gate decision (action / state / final_action) or rerun_protocol
    structured fields."""
    review = _critical_review()
    raw = apply_policy(review, "block", "critical", False, "medium")
    protected = attach_protection(dict(raw), review=review, language="zh")

    assert protected["action"] == raw["action"] == "block"
    assert protected["state"] == raw["state"]
    assert protected.get("final_action") == raw.get("final_action")

    for block_type, outcome in _block_outcomes().items():
        protected = attach_protection(dict(outcome), language="zh")
        assert protected["action"] == "block"
        assert protected["state"] == "blocked"
        assert protected["final_action"] == block_type
        # Agent repair task and rerun protocol still present (v2.1.0 contract).
        assert protected["protection"]["agent_task"]
        assert protected["protection"]["rerun_protocol"]["steps"]


def test_attach_protection_disabled_does_not_change_gate_action():
    review = _critical_review()
    raw = apply_policy(review, "block", "critical", False, "medium")
    protected = attach_protection(dict(raw), review=review, enabled=False)

    assert protected["action"] == raw["action"]
    assert protected["state"] == raw["state"]
    assert "protection" not in protected


# --- 8. Hook reason tells the agent to fix first -----------------------------

def test_hook_reason_first_paragraph_tells_agent_to_fix_first():
    protection = build_protection({
        "action": "block",
        "state": "blocked",
        "final_action": "finding_block",
        "reason": "risk",
    }, language="zh")
    reason = format_agent_reason(protection, "risk")
    first_paragraph = reason.split("\n\n", 1)[0].lower()
    assert "fix the current diff" in first_paragraph
    assert "do not relay" in first_paragraph or "do not quote" in first_paragraph
