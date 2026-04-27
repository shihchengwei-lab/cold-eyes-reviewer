"""Agent-facing protection brief for non-engineer users.

This module does not decide pass/block. It only repackages an existing block
outcome into instructions that an agent can act on and explain plainly. The
user-facing text is source material for the agent, not copy-paste output.
"""

from __future__ import annotations

from cold_eyes.local_checks import repair_lines as local_check_repair_lines


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
    user_message = _user_talking_points(risk_summary, block_type, language)
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
    """Build the hook block reason shown to the agent.

    Section order is deliberate:
    1. Agent must first fix the current diff (do not relay terminology to the user yet).
    2. Agent repair task (the actual work).
    3. Fresh-review rerun protocol (steps the agent should follow next).
    4. User-facing talking points, only if a user update is necessary.
    5. Original Cold Eyes detail (raw source material, last).
    """
    lines = [
        (
            "Cold Eyes blocked this change. Agent: fix the current diff first, run "
            "relevant local checks, then end the turn so the next Stop hook starts "
            "a fresh Cold Eyes review. Do not relay this brief, its terminology, "
            "or the raw block reason to the user before fixing."
        ),
        "",
        "Agent repair task:",
        protection.get("agent_task", ""),
        "",
        "Fresh-review rerun protocol:",
        _format_rerun_protocol(protection.get("rerun_protocol") or {}),
        "",
        "User-facing talking points (only if a user update is necessary; summarize in your own words; do not quote verbatim):",
        protection.get("user_message", ""),
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
    if final_action == "target_block":
        return "target_block"
    if final_action == "coverage_block":
        return "coverage_block"
    if final_action == "check_block":
        return "check_block"
    if final_action == "unreviewed_delta_block":
        return "unreviewed_delta_block"
    if final_action == "stale_review_block":
        return "stale_review_block"
    if final_action == "infra_block":
        return "infra_block"
    if final_action == "lock_block":
        return "lock_block"
    if any(str(i.get("category", "")).lower() == "intent" for i in issues):
        return "intent_mismatch"
    if outcome.get("truncated") and outcome.get("skipped_count", 0):
        return "incomplete_review"
    return "finding_block"


def _risk_summary(outcome: dict, issues: list[dict], block_type: str) -> list[str]:
    if block_type == "target_block":
        target = outcome.get("target") or {}
        if target.get("high_risk_unreviewed_files"):
            return ["有高風險檔案沒有被 Cold Eyes 審到"]
        if target.get("unreviewed_partial_stage_files"):
            return ["有檔案只 staged 了一部分，Cold Eyes 只會審到 staged 的部分"]
        return ["這次 review 目標外還有未審的變更"]
    if block_type == "coverage_block":
        coverage = outcome.get("coverage") or {}
        high_risk = coverage.get("unreviewed_high_risk_files") or []
        if high_risk:
            return ["有高風險檔案沒有被完整審到"]
        return ["這次變更沒有被 Cold Eyes 完整審完"]
    if block_type == "check_block":
        return ["本機檢查發現明確失敗"]
    if block_type == "unreviewed_delta_block":
        return ["有 source/設定的變更還沒被 Cold Eyes 審到"]
    if block_type == "stale_review_block":
        return ["Cold Eyes 在審的時候檔案又被改了，這次審的結果不能算數"]
    if block_type == "infra_block":
        return ["這次需要 Cold Eyes 審，但審查工具自己出了問題"]
    if block_type == "lock_block":
        return ["這次需要 Cold Eyes 審，但已經有另一個 review 還沒結束"]
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


def _user_talking_points(risk_summary: list[str], block_type: str, language: str | None) -> str:
    risks = "、".join(risk_summary) if risk_summary else "有高風險"
    if _is_english(language):
        if block_type == "lock_block":
            return (
                "Cold Eyes could not complete verification because another review is already "
                "active. The agent should wait for that review to finish, then end the turn "
                "again for a fresh review. No user action is required."
            )
        return (
            "Cold Eyes paused this change because it found a risk the agent should fix first. "
            "The agent should handle the fix, run relevant checks, and let the next Stop hook "
            "run a fresh review. No manual command is required from the user."
        )
    if block_type == "coverage_block":
        return (
            f"Cold Eyes 先擋下來了，因為{risks}。Agent 應補齊或縮小改動，"
            "再讓下一次 Stop hook 自動做全新的冷審；使用者不需要手動跑指令。"
        )
    if block_type == "target_block":
        return (
            f"Cold Eyes 先擋下來了，因為{risks}。它這次只審設定中的 review 目標，"
            "Agent 應補齊要審的變更或確認哪些檔案要刻意排除，然後再讓下一次 Stop hook 重新冷審。"
        )
    if block_type == "check_block":
        return (
            f"Cold Eyes 先擋下來了，因為{risks}。Agent 應依照本機檢查結果修正，"
            "修完後下一次 Stop hook 會自動重新冷審；使用者不需要手動跑指令。"
        )
    if block_type == "lock_block":
        return (
            "Cold Eyes 這次沒有完成驗證，因為另一個 review 還在進行。"
            "Agent 應等該 review 結束後，再 end turn 觸發新的冷審；使用者不需要操作。"
        )
    if block_type == "infra_block":
        return (
            f"Cold Eyes 這次沒有完成驗證，因為{risks}。Agent 應先處理工具問題或稍後重跑，"
            "再觸發新的冷審；使用者不需要手動跑指令。"
        )
    if block_type == "stale_review_block":
        return (
            f"Cold Eyes 先擋下來了，因為{risks}。Agent 應保持目前改動並重新觸發冷審，"
            "不要把舊 review 當成已通過；使用者不需要操作。"
        )
    return (
        f"Cold Eyes 先擋下來了，因為{risks}。Agent 應先修正目前 diff、跑必要檢查，"
        "再讓下一次 Stop hook 自動做全新的冷審；使用者不需要手動跑指令。"
    )


def _agent_task(
    outcome: dict,
    issues: list[dict],
    risk_summary: list[str],
    user_message: str,
    block_type: str,
) -> str:
    lines = [
        "1. Fix the current diff yourself before considering whether to update "
        "the user. Do not relay this brief or its terminology to the user "
        "before fixing.",
        "2. Follow the repair approach for this block type. Do not ask the "
        "user to review code unless a product decision is required.",
        "3. Keep the fix narrow and preserve unrelated user changes.",
        "4. Run the relevant local checks if available.",
        "5. End the turn so the next Stop hook runs a fresh Cold Eyes review.",
        "6. If Cold Eyes blocks again, follow the latest block as a new cold review.",
        "",
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
        lines.extend(local_check_repair_lines(outcome.get("checks")))
        return "\n".join(lines)

    if block_type == "target_block":
        target = outcome.get("target") or {}
        unreviewed = target.get("unreviewed_files") or []
        partial = target.get("unreviewed_partial_stage_files") or []
        high_risk = target.get("high_risk_unreviewed_files") or []
        if partial:
            lines.append(f"Partially staged files: {', '.join(partial[:10])}")
        if high_risk:
            lines.append(f"High-risk files not reviewed: {', '.join(high_risk[:10])}")
        elif unreviewed:
            lines.append(f"Files not reviewed: {', '.join(unreviewed[:10])}")
        lines.append(
            "Repair approach: stage the complete intended change, intentionally "
            "ignore files that should stay outside review, or switch scope when "
            "the broader target should be reviewed."
        )
        return "\n".join(lines)

    if block_type in {"unreviewed_delta_block", "stale_review_block", "infra_block", "lock_block"}:
        envelope = outcome.get("envelope") or {}
        files = (envelope.get("unreviewed") or {}).get("files") or (
            envelope.get("review_target") or {}
        ).get("files") or []
        if files:
            lines.append(f"Relevant files: {', '.join(files[:10])}")
        if block_type == "stale_review_block":
            lines.append("Repair approach: keep the current changes and end the turn again for a fresh review.")
        elif block_type == "infra_block":
            lines.append("Repair approach: do not claim completion; fix the gate problem or rerun after the tool is available.")
        elif block_type == "lock_block":
            lines.append("Repair approach: wait for the active review to finish, then end the turn again.")
        else:
            lines.append("Repair approach: stage, intentionally ignore, or reduce the unreviewed delta before ending the turn.")
        return "\n".join(lines)

    if block_type == "intent_mismatch":
        lines.append(
            "Decision boundary: technically fixable diff risks (typos, wrong "
            "identifiers, restored guards, mis-wired calls) are the agent's "
            "job to fix without asking. Only escalate to the user when the "
            "product direction or the user's intent is genuinely unclear and "
            "no code-level fix can resolve it."
        )

    if issues:
        lines.extend(["", "Findings to fix:"])
        for idx, issue in enumerate(issues[:5], start=1):
            lines.extend(_format_issue(idx, issue))
    lines.extend(local_check_repair_lines(outcome.get("checks")))
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
        "If the user needs an update, translate the talking points into a short context-specific message; do not quote verbatim.",
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
    if block_type == "target_block":
        return (
            "Make the review target match the intended change: stage the complete "
            "diff, ignore intentionally excluded files, or switch scope."
        )
    if block_type == "coverage_block":
        return (
            "Reduce or split the current diff, or make high-risk files reviewable, "
            "before ending the turn."
        )
    if block_type == "check_block":
        return (
            "Fix the hard local check failure visible in this run, then run the "
            "relevant local check again before ending the turn."
        )
    if block_type == "unreviewed_delta_block":
        return "Make the unreviewed source/config delta reviewable before ending the turn."
    if block_type == "stale_review_block":
        return "End the turn again without summarizing completion so Cold Eyes can review the current tree."
    if block_type == "infra_block":
        return "Do not summarize completion; fix or wait out the reviewer infrastructure problem."
    if block_type == "lock_block":
        return "Wait for the active review to finish, then end the turn again."
    if block_type == "intent_mismatch":
        return (
            "Decision boundary: if the diff risk is technically fixable (typo, "
            "wrong identifier, restored guard, missing branch, mis-wired call) "
            "the agent fixes it directly without asking the user. Only escalate "
            "to the user when the product direction or the user's intent is "
            "genuinely unclear and a code-level fix cannot resolve it."
        )
    return "Fix only the risk visible in the current diff while preserving unrelated user changes."


def _format_rerun_protocol(protocol: dict) -> str:
    """Render the rerun protocol for the agent-facing reason.

    Structured fields (owner, required, trigger, memory_policy,
    user_action_required) stay in the protection JSON and history so tooling
    can read them, but they are intentionally omitted from the hook reason
    text: the agent should see actionable steps, not machine-shaped metadata.
    """
    steps = protocol.get("steps") if isinstance(protocol.get("steps"), list) else []
    if not steps:
        return ""
    return "\n".join(f"- {step}" for step in steps)


def _is_english(language: str | None) -> bool:
    return bool(language and "english" in language.lower())
