"""Pipeline orchestrator — coordinates the full review flow."""

import os
import sys
import time

from cold_eyes.constants import SCHEMA_VERSION, STATE_SKIPPED, STATE_BLOCKED, STATE_OVERRIDDEN
from cold_eyes.git import git_cmd, collect_files, build_diff, estimate_tokens, GitCommandError, ConfigError
from cold_eyes.filter import filter_file_list, rank_file_list
from cold_eyes.triage import classify_depth
from cold_eyes.context import build_context
from cold_eyes.detector import build_detector_hints
from cold_eyes.prompt import build_prompt_text
from cold_eyes.intent import (
    DEFAULT_INTENT_MAX_CHARS,
    intent_prompt_block,
    is_enabled as intent_setting_enabled,
    load_intent_capsule,
)
from cold_eyes.protection import (
    attach_protection,
    history_summary as protection_history_summary,
    is_enabled as protection_setting_enabled,
)

try:
    from cold_eyes.memory import extract_fp_patterns as _extract_fp
except ImportError:
    _extract_fp = None
from cold_eyes.claude import ClaudeCliAdapter
from cold_eyes.review import parse_review_output
from cold_eyes.policy import apply_policy, calibrate_evidence, filter_by_confidence
from cold_eyes.history import log_to_history
from cold_eyes.config import load_policy
from cold_eyes import override as _override
from cold_eyes.override import consume_override_metadata
from cold_eyes.coverage_gate import (
    build_coverage_report,
    format_coverage_block_reason,
    is_truthy,
)
from cold_eyes.local_checks import (
    compact_history as checks_history_summary,
    format_block_reason as format_check_block_reason,
    normalize_check_mode,
    normalize_timeout,
    run_local_checks,
)

# Backward-compatible test seam for older tests that patch
# cold_eyes.engine.consume_override directly.
consume_override = _override.consume_override


def _resolve(cli_val, env_name, policy, policy_key, default, cast=None):
    """Resolve a setting.  CLI arg > env var > policy file > default."""
    if cli_val is not None:
        return cast(cli_val) if cast else cli_val
    env = os.environ.get(env_name)
    if env is not None:
        if cast:
            try:
                return cast(env)
            except (ValueError, TypeError):
                pass  # fall through to policy / default
        else:
            return env
    pol = policy.get(policy_key)
    if pol is not None:
        if cast:
            try:
                return cast(pol)
            except (ValueError, TypeError):
                pass  # fall through to default
        else:
            return pol
    return default


def run(mode=None, model=None, max_tokens=None, threshold=None,
        confidence=None, language=None, scope=None, override_reason=None,
        adapter=None, base=None, truncation_policy=None, shallow_model=None,
        context_tokens=None, max_input_tokens=None, history_path=None,
        minimum_coverage_pct=None, coverage_policy=None,
        fail_on_unreviewed_high_risk=None, override_note=None,
        hook_input_path=None, checks=None, check_timeout_sec=None):
    """Execute full review pipeline. Return FinalOutcome dict.

    adapter: ModelAdapter instance.  Defaults to ClaudeCliAdapter().
    base: base branch for pr-diff scope (e.g. 'main').
    truncation_policy: 'warn' (default), 'soft-pass', or 'fail-closed'.
    shallow_model: model override for shallow reviews (default: sonnet).
    context_tokens: token budget for context retrieval in deep reviews (default: 2000).
    max_input_tokens: total token cap for all content sent to model
                      (diff + context + hints). Default: max_tokens + context_tokens + 1000.
    """
    started = time.monotonic()
    cwd = os.getcwd()
    try:
        repo_root = git_cmd("rev-parse", "--show-toplevel")
    except GitCommandError:
        repo_root = ""
    policy = load_policy(repo_root)

    # Resolve settings: CLI arg > env var > policy file > default
    mode = _resolve(mode, "COLD_REVIEW_MODE", policy, "mode", "block")
    if isinstance(mode, str):
        mode = mode.lower()
    model = _resolve(model, "COLD_REVIEW_MODEL", policy, "model", "sonnet")
    max_tokens = _resolve(max_tokens, "COLD_REVIEW_MAX_TOKENS", policy,
                          "max_tokens", 12000, cast=int)
    threshold = _resolve(threshold, "COLD_REVIEW_BLOCK_THRESHOLD", policy,
                         "block_threshold", "critical")
    if isinstance(threshold, str):
        threshold = threshold.lower()
    min_confidence = _resolve(confidence, "COLD_REVIEW_CONFIDENCE", policy,
                              "confidence", "medium")
    if isinstance(min_confidence, str):
        min_confidence = min_confidence.lower()
    scope = _resolve(scope, "COLD_REVIEW_SCOPE", policy, "scope", "working")
    if isinstance(scope, str):
        scope = scope.lower()
    base = _resolve(base, "COLD_REVIEW_BASE", policy, "base", None)
    language = _resolve(language, "COLD_REVIEW_LANGUAGE", policy, "language", None)
    truncation_policy = _resolve(truncation_policy, "COLD_REVIEW_TRUNCATION_POLICY",
                                 policy, "truncation_policy", "warn")
    if isinstance(truncation_policy, str):
        truncation_policy = truncation_policy.lower()
    shallow_model = _resolve(shallow_model, "COLD_REVIEW_SHALLOW_MODEL",
                             policy, "shallow_model", "sonnet")
    context_tokens = _resolve(context_tokens, "COLD_REVIEW_CONTEXT_TOKENS",
                              policy, "context_tokens", 2000, cast=int)
    max_input_tokens = _resolve(max_input_tokens, "COLD_REVIEW_MAX_INPUT_TOKENS",
                                policy, "max_input_tokens", None,
                                cast=lambda v: int(v) if v is not None else None)
    if not max_input_tokens or max_input_tokens <= 0:
        max_input_tokens = max_tokens + context_tokens + 1000
    minimum_coverage_pct = _resolve(
        minimum_coverage_pct, "COLD_REVIEW_MINIMUM_COVERAGE_PCT",
        policy, "minimum_coverage_pct", 80,
        cast=lambda v: int(v) if v not in (None, "") else None,
    )
    if minimum_coverage_pct is not None and not (0 <= minimum_coverage_pct <= 100):
        minimum_coverage_pct = None
    coverage_policy = _resolve(
        coverage_policy, "COLD_REVIEW_COVERAGE_POLICY",
        policy, "coverage_policy", "warn",
    )
    if isinstance(coverage_policy, str):
        coverage_policy = coverage_policy.lower()
    fail_on_unreviewed_high_risk = _resolve(
        fail_on_unreviewed_high_risk,
        "COLD_REVIEW_FAIL_ON_UNREVIEWED_HIGH_RISK",
        policy,
        "fail_on_unreviewed_high_risk",
        True,
        cast=is_truthy,
    )
    check_mode = normalize_check_mode(_resolve(
        checks,
        "COLD_REVIEW_CHECKS",
        policy,
        "checks",
        "auto",
    ))
    check_timeout_sec = normalize_timeout(_resolve(
        check_timeout_sec,
        "COLD_REVIEW_CHECK_TIMEOUT_SEC",
        policy,
        "check_timeout_sec",
        120,
        cast=int,
    ))
    agent_brief_enabled = protection_setting_enabled(os.environ.get("COLD_REVIEW_AGENT_BRIEF"), True)
    intent_enabled = intent_setting_enabled(os.environ.get("COLD_REVIEW_INTENT_CONTEXT"), True)
    intent_max_chars = _resolve(
        None,
        "COLD_REVIEW_INTENT_MAX_CHARS",
        {},
        "intent_max_chars",
        DEFAULT_INTENT_MAX_CHARS,
        cast=int,
    )
    intent_capsule = load_intent_capsule(
        hook_input_path,
        enabled=intent_enabled,
        max_chars=intent_max_chars,
    )

    # mode=off: skip immediately (normally caught by shell, but policy file may set it)
    if mode == "off":
        return _skip("mode is off")

    if adapter is None:
        adapter = ClaudeCliAdapter()

    # Override token (one-time, file-based)
    token = consume_override_metadata(repo_root)
    token_ok = token["ok"]
    token_reason = token["reason"]
    token_note = token["note"]

    # Legacy env var override (deprecated — cannot truly be consumed)
    legacy_allow = os.environ.get("COLD_REVIEW_ALLOW_ONCE") == "1"
    if legacy_allow:
        import sys as _sys
        print("WARNING: COLD_REVIEW_ALLOW_ONCE is deprecated; "
              "use: python cli.py arm-override --reason '<reason>'",
              file=_sys.stderr)

    allow_once = token_ok or legacy_allow
    if token_ok and token_reason:
        override_reason = override_reason or token_reason
    override_reason = override_reason or os.environ.get("COLD_REVIEW_OVERRIDE_REASON", "")
    override_note = override_note or token_note or os.environ.get("COLD_REVIEW_OVERRIDE_NOTE", "")
    ignore_file = os.path.join(repo_root, ".cold-review-ignore") if repo_root else ""

    # 1. Collect files
    try:
        all_files, untracked = collect_files(scope, base=base)
    except (GitCommandError, ConfigError) as exc:
        review = _infra_review(str(exc))
        outcome = apply_policy(review, mode, threshold, allow_once, min_confidence,
                               override_reason=override_reason, language=language,
                               override_note=override_note)
        log_to_history(cwd, mode, model, outcome["state"],
                       reason=review["summary"], min_confidence=min_confidence,
                       scope=scope, override_reason=override_reason,
                       cold_eyes_verdict=outcome.get("cold_eyes_verdict"),
                       final_action=outcome.get("final_action"),
                       authority=outcome.get("authority"),
                       override_note=outcome.get("override_note", ""),
                       duration_ms=_elapsed_ms(started))
        return outcome
    if not all_files:
        log_to_history(cwd, mode, model, STATE_SKIPPED, "no changes",
                       min_confidence=min_confidence, scope=scope,
                       duration_ms=_elapsed_ms(started))
        return _skip("no changes")

    # 2. Filter
    filtered = filter_file_list(all_files, ignore_file)
    if not filtered:
        log_to_history(cwd, mode, model, STATE_SKIPPED, "all files ignored",
                       min_confidence=min_confidence, scope=scope,
                       duration_ms=_elapsed_ms(started))
        return _skip("all files ignored")

    # 3. Rank
    ranked = rank_file_list(filtered, untracked)

    # 4. Triage — skip / shallow / deep
    triage = classify_depth(ranked)
    review_depth = triage["review_depth"]

    if review_depth == "skip":
        reason = f"triage skip: {triage['why_depth_selected']}"
        log_to_history(cwd, mode, model, STATE_SKIPPED, reason,
                       min_confidence=min_confidence, scope=scope,
                       review_depth=review_depth,
                       duration_ms=_elapsed_ms(started))
        result = _skip(reason)
        result["review_depth"] = review_depth
        result["why_depth_selected"] = triage["why_depth_selected"]
        return result

    # Shallow: use lighter model + shallow prompt
    effective_model = shallow_model if review_depth == "shallow" else model
    prompt_depth = "shallow" if review_depth == "shallow" else "deep"

    # 5. Build diff
    try:
        diff_token_limit = min(max_tokens, max_input_tokens)
        diff_meta = build_diff(ranked, untracked, diff_token_limit, scope, base=base)
    except GitCommandError as exc:
        review = _infra_review(str(exc))
        outcome = apply_policy(review, mode, threshold, allow_once, min_confidence,
                               override_reason=override_reason, language=language,
                               override_note=override_note)
        log_to_history(cwd, mode, effective_model, outcome["state"],
                       reason=review["summary"], min_confidence=min_confidence,
                       scope=scope, override_reason=override_reason,
                       cold_eyes_verdict=outcome.get("cold_eyes_verdict"),
                       final_action=outcome.get("final_action"),
                       authority=outcome.get("authority"),
                       override_note=outcome.get("override_note", ""),
                       duration_ms=_elapsed_ms(started))
        return outcome

    diff_text = diff_meta["diff_text"]
    file_count = diff_meta["file_count"]
    token_count = diff_meta["token_count"]
    truncated = diff_meta["truncated"]
    skipped_files = (diff_meta["partial_files"] + diff_meta["skipped_budget"]
                     + diff_meta["skipped_binary"] + diff_meta["skipped_unreadable"])
    diff_line_count = diff_text.count("\n") + 1

    # --- Total input budget enforcement ---
    input_remaining = max_input_tokens - token_count
    if input_remaining < 0:
        sys.stderr.write(
            f"cold-review: warning: diff tokens ({token_count}) exceed "
            f"max_input_tokens ({max_input_tokens}); context and hints will be skipped\n"
        )
    hints_dropped = False

    # Context retrieval for deep path (capped by remaining budget)
    context_meta = None
    if review_depth == "deep" and context_tokens > 0 and input_remaining > 0:
        effective_ctx_budget = min(context_tokens, input_remaining)
        context_meta = build_context(ranked, max_tokens=effective_ctx_budget)
        if context_meta["context_text"]:
            diff_text = diff_text + "\n" + context_meta["context_text"]
            token_count += context_meta["token_count"]
            input_remaining -= context_meta["token_count"]

    # Detector hints for deep path (dropped if no budget remains)
    detector_meta = None
    if review_depth == "deep":
        detector_meta = build_detector_hints(diff_text, ranked)
        if detector_meta["hint_text"]:
            hint_tokens = estimate_tokens(detector_meta["hint_text"])
            if hint_tokens <= input_remaining:
                diff_text = diff_text + "\n" + detector_meta["hint_text"]
                input_remaining -= hint_tokens
                token_count += hint_tokens
            else:
                detector_meta["hint_text"] = ""
                hints_dropped = True

    # Low-weight intent capsule: only deep reviews get this extra hint, and it
    # must fit the remaining budget. Policy later prevents intent-only blocks
    # without concrete diff evidence.
    intent_text = intent_prompt_block(intent_capsule) if review_depth == "deep" else ""
    if intent_text:
        intent_tokens = estimate_tokens(intent_text)
        if intent_tokens <= input_remaining:
            diff_text = diff_text + "\n" + intent_text
            input_remaining -= intent_tokens
            token_count += intent_tokens
        else:
            intent_capsule = dict(intent_capsule)
            intent_capsule["status"] = "skipped_budget"

    # Coverage visibility and gate decision
    coverage = build_coverage_report(
        ranked,
        diff_meta,
        minimum_coverage_pct=minimum_coverage_pct,
        coverage_policy=coverage_policy,
        fail_on_unreviewed_high_risk=fail_on_unreviewed_high_risk,
    )

    if not diff_text.strip() or file_count == 0:
        result = _apply_coverage_gate(
            _skip("no diff content"), coverage, mode, allow_once,
            override_reason=override_reason, override_note=override_note,
        )
        result = _attach_protection_brief(
            result, language=language, intent=intent_capsule,
            enabled=agent_brief_enabled,
        )
        log_to_history(
            cwd, mode, effective_model, result["state"], "no diff content",
            min_confidence=min_confidence, scope=scope,
            coverage=result.get("coverage"),
            cold_eyes_verdict=result.get("cold_eyes_verdict"),
            final_action=result.get("final_action"),
            authority=result.get("authority"),
            override_reason=override_reason,
            override_note=result.get("override_note", ""),
            protection=protection_history_summary(result.get("protection")),
            duration_ms=_elapsed_ms(started),
        )
        return result

    # 5. Build prompt
    prompt_text = build_prompt_text(language, depth=prompt_depth)

    # 6. Call model via adapter
    invocation = adapter.review(diff_text, prompt_text, effective_model)

    # 7. Handle errors
    failure_kind = invocation.failure_kind
    stderr_excerpt = getattr(invocation, "stderr", "")[:500] if hasattr(invocation, "stderr") else ""

    if invocation.exit_code != 0:
        failure_kind = failure_kind or "cli_error"
        review = _infra_review(f"claude exit {invocation.exit_code}")
        outcome = apply_policy(review, mode, threshold, allow_once, min_confidence,
                               override_reason=override_reason, language=language,
                               override_note=override_note)
        log_to_history(cwd, mode, effective_model, outcome["state"],
                       reason=review["summary"], min_confidence=min_confidence,
                       scope=scope, override_reason=override_reason,
                       failure_kind=failure_kind, stderr_excerpt=stderr_excerpt,
                       cold_eyes_verdict=outcome.get("cold_eyes_verdict"),
                       final_action=outcome.get("final_action"),
                       authority=outcome.get("authority"),
                       override_note=outcome.get("override_note", ""),
                       duration_ms=_elapsed_ms(started))
        return outcome

    if not invocation.stdout:
        failure_kind = "empty_output"
        review = _infra_review("empty output")
        outcome = apply_policy(review, mode, threshold, allow_once, min_confidence,
                               override_reason=override_reason, language=language,
                               override_note=override_note)
        log_to_history(cwd, mode, effective_model, outcome["state"],
                       reason=review["summary"], min_confidence=min_confidence,
                       scope=scope, override_reason=override_reason,
                       failure_kind=failure_kind, stderr_excerpt=stderr_excerpt,
                       cold_eyes_verdict=outcome.get("cold_eyes_verdict"),
                       final_action=outcome.get("final_action"),
                       authority=outcome.get("authority"),
                       override_note=outcome.get("override_note", ""),
                       duration_ms=_elapsed_ms(started))
        return outcome

    # 8. Parse review
    review = parse_review_output(invocation.stdout)

    # 8.5 FP memory — extract patterns from override history
    fp_patterns = _extract_fp(history_path=history_path) if _extract_fp else None

    # 9-10. Apply policy (with truncation context + FP memory)
    outcome = apply_policy(review, mode, threshold, allow_once, min_confidence,
                           truncated=truncated, skipped_files=skipped_files,
                           override_reason=override_reason, language=language,
                           truncation_policy=truncation_policy,
                           fp_patterns=fp_patterns,
                           override_note=override_note)

    # Expose filtered issues for downstream consumers (e.g. gates/result.py)
    _calibrated = calibrate_evidence(review.get("issues", []), fp_patterns=fp_patterns)
    outcome["issues"] = filter_by_confidence(_calibrated, min_confidence)

    outcome = _apply_coverage_gate(
        outcome, coverage, mode, allow_once,
        override_reason=override_reason, override_note=override_note,
    )
    local_checks = run_local_checks(
        ranked,
        mode=check_mode,
        timeout=check_timeout_sec,
        repo_root=repo_root or cwd,
    )
    outcome = _apply_local_check_gate(
        outcome, local_checks, mode, allow_once,
        override_reason=override_reason, override_note=override_note,
    )
    outcome = _attach_protection_brief(
        outcome, review=review, language=language, intent=intent_capsule,
        enabled=agent_brief_enabled,
    )

    # Add review path visibility
    outcome["review_depth"] = review_depth
    outcome["why_depth_selected"] = triage["why_depth_selected"]
    if context_meta and context_meta["context_text"]:
        outcome["context_summary"] = context_meta["context_summary"]
    if detector_meta:
        if detector_meta["hint_text"]:
            outcome["detector_repo_type"] = detector_meta["repo_type"]
            outcome["detector_focus"] = detector_meta["detector_focus"]
            outcome["state_signal_count"] = len(detector_meta["state_signals"])
        if hints_dropped:
            outcome["hints_dropped"] = True
    if fp_patterns and fp_patterns["total_overrides"] > 0:
        outcome["fp_memory_overrides"] = fp_patterns["total_overrides"]
        outcome["fp_memory_patterns"] = (
            len(fp_patterns["category_patterns"])
            + len(fp_patterns["path_patterns"])
            + len(fp_patterns["check_patterns"])
        )

    # 11. Log
    log_to_history(
        cwd, mode, effective_model, outcome["state"],
        review=review, file_count=file_count,
        line_count=diff_line_count, truncated=truncated,
        token_count=token_count, min_confidence=min_confidence,
        scope=scope, override_reason=override_reason,
        review_depth=review_depth,
        coverage=outcome.get("coverage"),
        checks=checks_history_summary(outcome.get("checks")),
        cold_eyes_verdict=outcome.get("cold_eyes_verdict"),
        final_action=outcome.get("final_action"),
        authority=outcome.get("authority"),
        override_note=outcome.get("override_note", ""),
        protection=protection_history_summary(outcome.get("protection")),
        duration_ms=_elapsed_ms(started),
    )

    return outcome


def _attach_protection_brief(outcome, review=None, language=None, intent=None, enabled=True):
    return attach_protection(
        outcome,
        review=review,
        language=language,
        intent=intent,
        enabled=enabled,
    )


def _elapsed_ms(started):
    return int((time.monotonic() - started) * 1000)


def _skip(reason):
    return {
        "action": "pass",
        "state": STATE_SKIPPED,
        "reason": reason,
        "display": f"cold-review: skipped ({reason})",
    }


def _infra_review(summary):
    """Build a synthetic review dict representing an infrastructure failure."""
    return {
        "schema_version": SCHEMA_VERSION,
        "pass": True,
        "review_status": "failed",
        "issues": [],
        "summary": summary,
    }


def _apply_coverage_gate(outcome, coverage, mode, allow_once,
                         override_reason="", override_note=""):
    """Attach coverage metadata and enforce coverage gate decisions."""
    outcome = dict(outcome)
    outcome["coverage"] = coverage
    outcome["reviewed_files"] = coverage.get("reviewed_files", 0)
    outcome["total_files"] = coverage.get("total_files", 0)
    outcome["coverage_pct"] = coverage.get("coverage_pct", 100.0)

    coverage_action = coverage.get("action", "pass")
    if coverage_action == "warn" or (coverage_action == "block" and mode != "block"):
        outcome["coverage_warning"] = coverage.get("reason", "")

    if coverage_action != "block" or mode != "block":
        if coverage_action == "block" and outcome.get("cold_eyes_verdict") == "pass":
            outcome["cold_eyes_verdict"] = "incomplete"
        return outcome

    if outcome.get("action") == "block" or outcome.get("state") == STATE_OVERRIDDEN:
        if outcome.get("cold_eyes_verdict") == "pass":
            outcome["cold_eyes_verdict"] = "incomplete"
        return outcome

    if allow_once:
        reason_suffix = f" [{override_reason}]" if override_reason else ""
        outcome.update({
            "action": "pass",
            "state": STATE_OVERRIDDEN,
            "reason": override_reason,
            "display": f"cold-review: override - coverage block skipped{reason_suffix}",
            "cold_eyes_verdict": "incomplete",
            "final_action": "override_pass",
            "authority": "human_override",
        })
        if override_note:
            outcome["override_note"] = override_note
        return outcome

    outcome.update({
        "action": "block",
        "state": STATE_BLOCKED,
        "reason": format_coverage_block_reason(coverage),
        "display": (
            "cold-review: blocking "
            f"(coverage policy: {coverage.get('policy')}, "
            f"{coverage.get('coverage_pct')}% reviewed)"
        ),
        "truncated": bool(coverage.get("unreviewed_files")),
        "skipped_count": len(coverage.get("unreviewed_files", [])),
        "cold_eyes_verdict": "incomplete",
        "final_action": "coverage_block",
        "authority": "coverage_gate",
    })
    return outcome


def _apply_local_check_gate(outcome, checks, mode, allow_once,
                            override_reason="", override_note=""):
    """Attach local check metadata and enforce hard-check failures."""
    outcome = dict(outcome)
    outcome["checks"] = checks
    if not checks or not checks.get("hard_failed"):
        return outcome

    reason = format_check_block_reason(checks)
    if mode != "block":
        outcome["check_warning"] = reason
        return outcome

    if outcome.get("action") == "block" or outcome.get("state") == STATE_OVERRIDDEN:
        outcome["check_warning"] = reason
        return outcome

    if allow_once:
        reason_suffix = f" [{override_reason}]" if override_reason else ""
        outcome.update({
            "action": "pass",
            "state": STATE_OVERRIDDEN,
            "reason": override_reason,
            "display": f"cold-review: override - local check block skipped{reason_suffix}",
            "cold_eyes_verdict": "local_check_failed",
            "final_action": "override_pass",
            "authority": "human_override",
        })
        if override_note:
            outcome["override_note"] = override_note
        return outcome

    outcome.update({
        "action": "block",
        "state": STATE_BLOCKED,
        "reason": reason,
        "display": "cold-review: blocking (local hard check failed)",
        "cold_eyes_verdict": "local_check_failed",
        "final_action": "check_block",
        "authority": "local_checks",
    })
    return outcome
