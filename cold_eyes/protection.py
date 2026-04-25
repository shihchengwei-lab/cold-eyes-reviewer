"""Agent-facing protection brief for non-engineer users.

This module does not decide pass/block. It only repackages an existing block
outcome into instructions that an agent can act on and explain plainly.
"""

from __future__ import annotations


_OFF_VALUES = {"0", "false", "no", "off"}


def is_enabled(value: str | None, default: bool = True) -> bool:
    if value is None or value == "":
        return default
    return value.strip().lower() not in _OFF_VALUES


def attach_protection(
    outcome: dict,
    *,
    review: dict | None = None,
    language: str | None = None,
    intent: dict | None = None,
    enabled: bool = True,
) -> dict:
    """Attach protection metadata and rewrite block reason when enabled."""
    outcome = dict(outcome)
    if not enabled or outcome.get("action") != "block":
        if intent and intent.get("status") not in (None, "missing_hook_input"):
            outcome["protection"] = {"intent": _intent_summary(intent)}
        return outcome

    protection = build_protection(outcome, review=review, language=language, intent=intent)
    outcome["protection"] = protection
    outcome["reason"] = format_agent_reason(protection, outcome.get("reason", ""))
    return outcome


def build_protection(
    outcome: dict,
    *,
    review: dict | None = None,
    language: str | None = None,
    intent: dict | None = None,
) -> dict:
    issues = _issues(outcome, review)
    block_type = _block_type(outcome, issues)
    risk_summary = _risk_summary(outcome, issues, block_type)
    user_message = _user_message(risk_summary, block_type, language)
    agent_task = _agent_task(outcome, issues, risk_summary, user_message, block_type)
    rerun_protocol = _rerun_protocol(block_type)
    return {
        "block_type": block_type,
        "risk_summary": risk_summary,
        "user_message": user_message,
        "agent_task": agent_task,
        "rerun_protocol": rerun_protocol,
        "intent": _intent_summary(intent),
    }


def format_agent_reason(protection: dict, original_reason: str = "") -> str:
    """Build the hook block reason shown to the agent."""
    lines = [
        (
            "Cold Eyes blocked this change. Agent: fix the current diff, run "
            "relevant checks, then end the turn so the next Stop hook starts a "
            "fresh Cold Eyes review."
        ),
        "",
        "Message to relay to the user:",
        protection.get("user_message", ""),
        "",
        "Automatic rerun protocol:",
        _format_rerun_protocol(protection.get("rerun_protocol") or {}),
        "",
        "Agent repair task:",
        protection.get("agent_task", ""),
    ]
    if original_reason:
        lines.extend(["", "Original Cold Eyes detail:", original_reason])
    if "arm-override" not in "\n".join(lines):
        lines.extend([
            "",
            "Override is last resort only: python cli.py arm-override --reason '<reason>'",
        ])
    return "\n".join(lines).strip()


def history_summary(protection: dict | None) -> dict | None:
    """Return a compact history-safe protection summary."""
    if not protection:
        return None
    intent = protection.get("intent") or {}
    return {
        "agent_task": bool(protection.get("agent_task")),
        "user_message": bool(protection.get("user_message")),
        "block_type": protection.get("block_type", ""),
        "risk_summary": list(protection.get("risk_summary", []))[:5],
        "intent": {
            "status": intent.get("status", ""),
            "has_summary": bool(intent.get("summary")),
        },
    }


def _issues(outcome: dict, review: dict | None) -> list[dict]:
    issues = outcome.get("issues")
    if isinstance(issues, list):
        return [i for i in issues if isinstance(i, dict)]
    if isinstance(review, dict) and isinstance(review.get("issues"), list):
        return [i for i in review["issues"] if isinstance(i, dict)]
    return []


def _block_type(outcome: dict, issues: list[dict]) -> str:
    final_action = outcome.get("final_action")
    if final_action == "coverage_block":
        return "coverage_block"
    if any(str(i.get("category", "")).lower() == "intent" for i in issues):
        return "intent_mismatch"
    if outcome.get("truncated") and outcome.get("skipped_count", 0):
        return "incomplete_review"
    return "finding_block"


def _risk_summary(outcome: dict, issues: list[dict], block_type: str) -> list[str]:
    if block_type == "coverage_block":
        coverage = outcome.get("coverage") or {}
        high_risk = coverage.get("unreviewed_high_risk_files") or []
        if high_risk:
            return ["有高風險檔案沒有被完整審到"]
        return ["這次變更沒有被 Cold Eyes 完整審完"]
    if block_type == "intent_mismatch":
        return ["這次改動可能偏離使用者原本要做的事"]
    if block_type == "incomplete_review":
        return ["diff 太大，部分檔案沒有被審到"]
    summaries = []
    for issue in issues[:3]:
        category = str(issue.get("category", "correctness")).lower()
        summaries.append(_category_label(category))
    return summaries or ["Cold Eyes 發現高風險問題"]


def _category_label(category: str) -> str:
    labels = {
        "security": "可能有安全風險",
        "correctness": "可能讓功能行為出錯",
        "consistency": "可能造成資料或流程不一致",
        "complexity": "可能讓改動變得難以安全維護",
        "reference": "可能有刪掉後仍被引用的項目",
        "intent": "可能偏離使用者原本目標",
    }
    return labels.get(category, "Cold Eyes 發現高風險問題")


def _user_message(risk_summary: list[str], block_type: str, language: str | None) -> str:
    risks = "、".join(risk_summary) if risk_summary else "有高風險"
    if _is_english(language):
        return (
            "Cold Eyes paused this change because it found a risk the agent should fix first. "
            "I will repair it and let the next Stop hook run a fresh review. "
            "You do not need to run a command manually."
        )
    if block_type == "coverage_block":
        return (
            f"Cold Eyes 先擋下來了，因為{risks}。我會先讓 Agent 補齊或縮小改動，"
            "再讓下一次 Stop hook 自動做全新的冷審；你不用手動跑指令。"
        )
    return (
        f"Cold Eyes 先擋下來了，因為{risks}。你不用自己看程式碼，也不用手動跑指令；"
        "我會先讓 Agent 修正後，再讓下一次 Stop hook 自動做全新的冷審。"
    )


def _agent_task(
    outcome: dict,
    issues: list[dict],
    risk_summary: list[str],
    user_message: str,
    block_type: str,
) -> str:
    lines = [
        "1. Relay the user message in plain language before editing.",
        "2. Fix the blocked risk in the current diff. Do not ask the user to review code.",
        "3. Keep the fix narrow and preserve unrelated user changes.",
        "4. Run the relevant local checks if available.",
        "5. End the turn so the next Stop hook runs a fresh Cold Eyes review.",
        "6. If Cold Eyes blocks again, follow the latest block as a new cold review.",
        "",
        f"User message: {user_message}",
        f"Risk summary: {', '.join(risk_summary)}",
    ]
    if block_type == "coverage_block":
        coverage = outcome.get("coverage") or {}
        unreviewed = coverage.get("unreviewed_files") or []
        high_risk = coverage.get("unreviewed_high_risk_files") or []
        if high_risk:
            lines.append(f"High-risk files not fully reviewed: {', '.join(high_risk[:10])}")
        elif unreviewed:
            lines.append(f"Files not fully reviewed: {', '.join(unreviewed[:10])}")
        lines.append(
            "Repair approach: reduce the diff, split the change, or make sure "
            "high-risk files are reviewable in the next fresh review."
        )
        return "\n".join(lines)

    if issues:
        lines.extend(["", "Findings to fix:"])
        for idx, issue in enumerate(issues[:5], start=1):
            lines.extend(_format_issue(idx, issue))
    return "\n".join(lines)


def _format_issue(idx: int, issue: dict) -> list[str]:
    sev = str(issue.get("severity", "major")).upper()
    conf = str(issue.get("confidence", "medium"))
    file_name = issue.get("file") or "unknown"
    line_hint = issue.get("line_hint") or ""
    where = f"{file_name} {line_hint}".strip()
    lines = [
        f"{idx}. [{sev}/{conf}] {where}",
        f"   Check: {issue.get('check', '')}",
        f"   Verdict: {issue.get('verdict', '')}",
        f"   Fix: {issue.get('fix', '')}",
    ]
    evidence = issue.get("evidence")
    if isinstance(evidence, list) and evidence:
        lines.append(f"   Evidence: {'; '.join(str(e) for e in evidence[:3])}")
    return lines


def _intent_summary(intent: dict | None) -> dict:
    if not isinstance(intent, dict):
        return {"status": "missing", "summary": ""}
    return {
        "status": intent.get("status", ""),
        "summary": intent.get("summary", ""),
        "source": intent.get("source", ""),
        "truncated": bool(intent.get("truncated")),
    }


def _rerun_protocol(block_type: str) -> dict:
    steps = [
        "Relay the plain-language user message before editing.",
        _repair_step(block_type),
        "Run relevant local checks when available.",
        "End the turn so Claude Code's next Stop hook runs Cold Eyes again.",
        "Treat any next block as a fresh review of the current diff, not as validation against prior block history.",
    ]
    return {
        "owner": "main_agent",
        "required": True,
        "trigger": "next_stop_hook",
        "memory_policy": "fresh_review_only",
        "user_action_required": False,
        "steps": steps,
    }


def _repair_step(block_type: str) -> str:
    if block_type == "coverage_block":
        return (
            "Reduce or split the current diff, or make high-risk files reviewable, "
            "before ending the turn."
        )
    if block_type == "intent_mismatch":
        return (
            "If the fix needs a product or intent decision, ask the user in plain "
            "language; otherwise fix only the visible diff risk."
        )
    return "Fix only the risk visible in the current diff while preserving unrelated user changes."


def _format_rerun_protocol(protocol: dict) -> str:
    steps = protocol.get("steps") if isinstance(protocol.get("steps"), list) else []
    lines = [
        f"Owner: {protocol.get('owner', 'main_agent')}",
        f"Required: {str(bool(protocol.get('required', True))).lower()}",
        f"Trigger: {protocol.get('trigger', 'next_stop_hook')}",
        f"Memory policy: {protocol.get('memory_policy', 'fresh_review_only')}",
        "User action required: false",
        "Steps:",
    ]
    lines.extend(f"- {step}" for step in steps)
    return "\n".join(lines)


def _is_english(language: str | None) -> bool:
    return bool(language and "english" in language.lower())
