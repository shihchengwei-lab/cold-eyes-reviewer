"""Pipeline orchestrator — coordinates the full review flow."""

import os
import sys

from cold_eyes.constants import SCHEMA_VERSION, STATE_SKIPPED
from cold_eyes.git import git_cmd, collect_files, build_diff, estimate_tokens, GitCommandError, ConfigError
from cold_eyes.filter import filter_file_list, rank_file_list
from cold_eyes.triage import classify_depth
from cold_eyes.context import build_context
from cold_eyes.detector import build_detector_hints
from cold_eyes.prompt import build_prompt_text

try:
    from cold_eyes.memory import extract_fp_patterns as _extract_fp
except ImportError:
    _extract_fp = None
from cold_eyes.claude import ClaudeCliAdapter
from cold_eyes.review import parse_review_output
from cold_eyes.policy import apply_policy, calibrate_evidence, filter_by_confidence
from cold_eyes.history import log_to_history
from cold_eyes.config import load_policy
from cold_eyes.override import consume_override


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
        context_tokens=None, max_input_tokens=None):
    """Execute full review pipeline. Return FinalOutcome dict.

    adapter: ModelAdapter instance.  Defaults to ClaudeCliAdapter().
    base: base branch for pr-diff scope (e.g. 'main').
    truncation_policy: 'warn' (default), 'soft-pass', or 'fail-closed'.
    shallow_model: model override for shallow reviews (default: sonnet).
    context_tokens: token budget for context retrieval in deep reviews (default: 2000).
    max_input_tokens: total token cap for all content sent to model
                      (diff + context + hints). Default: max_tokens + context_tokens + 1000.
    """
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
    model = _resolve(model, "COLD_REVIEW_MODEL", policy, "model", "opus")
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

    # mode=off: skip immediately (normally caught by shell, but policy file may set it)
    if mode == "off":
        return _skip("mode is off")

    if adapter is None:
        adapter = ClaudeCliAdapter()

    # Override token (one-time, file-based)
    token_ok, token_reason = consume_override(repo_root)

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
    ignore_file = os.path.join(repo_root, ".cold-review-ignore") if repo_root else ""

    # 1. Collect files
    try:
        all_files, untracked = collect_files(scope, base=base)
    except (GitCommandError, ConfigError) as exc:
        review = _infra_review(str(exc))
        outcome = apply_policy(review, mode, threshold, allow_once, min_confidence,
                               override_reason=override_reason, language=language)
        log_to_history(cwd, mode, model, outcome["state"],
                       reason=review["summary"], min_confidence=min_confidence,
                       scope=scope, override_reason=override_reason)
        return outcome
    if not all_files:
        log_to_history(cwd, mode, model, STATE_SKIPPED, "no changes",
                       min_confidence=min_confidence, scope=scope)
        return _skip("no changes")

    # 2. Filter
    filtered = filter_file_list(all_files, ignore_file)
    if not filtered:
        log_to_history(cwd, mode, model, STATE_SKIPPED, "all files ignored",
                       min_confidence=min_confidence, scope=scope)
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
                       review_depth=review_depth)
        result = _skip(reason)
        result["review_depth"] = review_depth
        result["why_depth_selected"] = triage["why_depth_selected"]
        return result

    # Shallow: use lighter model + shallow prompt
    effective_model = shallow_model if review_depth == "shallow" else model
    prompt_depth = "shallow" if review_depth == "shallow" else "deep"

    # 5. Build diff
    try:
        diff_meta = build_diff(ranked, untracked, max_tokens, scope, base=base)
    except GitCommandError as exc:
        review = _infra_review(str(exc))
        outcome = apply_policy(review, mode, threshold, allow_once, min_confidence,
                               override_reason=override_reason, language=language)
        log_to_history(cwd, mode, effective_model, outcome["state"],
                       reason=review["summary"], min_confidence=min_confidence,
                       scope=scope, override_reason=override_reason)
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
            diff_text = context_meta["context_text"] + "\n" + diff_text
            token_count += context_meta["token_count"]
            input_remaining -= context_meta["token_count"]

    # Detector hints for deep path (dropped if no budget remains)
    detector_meta = None
    if review_depth == "deep":
        detector_meta = build_detector_hints(diff_text, ranked)
        if detector_meta["hint_text"]:
            hint_tokens = estimate_tokens(detector_meta["hint_text"])
            if hint_tokens <= input_remaining:
                diff_text = detector_meta["hint_text"] + "\n" + diff_text
                input_remaining -= hint_tokens
                token_count += hint_tokens
            else:
                detector_meta["hint_text"] = ""
                hints_dropped = True

    # Coverage visibility
    total_candidates = len(ranked)
    reviewed_count = file_count
    coverage_pct = (round(reviewed_count / total_candidates * 100, 1)
                    if total_candidates > 0 else 100.0)

    if not diff_text.strip() or file_count == 0:
        log_to_history(cwd, mode, effective_model, STATE_SKIPPED, "no diff content",
                       min_confidence=min_confidence, scope=scope)
        return _skip("no diff content")

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
                               override_reason=override_reason, language=language)
        log_to_history(cwd, mode, effective_model, outcome["state"],
                       reason=review["summary"], min_confidence=min_confidence,
                       scope=scope, override_reason=override_reason,
                       failure_kind=failure_kind, stderr_excerpt=stderr_excerpt)
        return outcome

    if not invocation.stdout:
        failure_kind = "empty_output"
        review = _infra_review("empty output")
        outcome = apply_policy(review, mode, threshold, allow_once, min_confidence,
                               override_reason=override_reason, language=language)
        log_to_history(cwd, mode, effective_model, outcome["state"],
                       reason=review["summary"], min_confidence=min_confidence,
                       scope=scope, override_reason=override_reason,
                       failure_kind=failure_kind, stderr_excerpt=stderr_excerpt)
        return outcome

    # 8. Parse review
    review = parse_review_output(invocation.stdout)

    # 8.5 FP memory — extract patterns from override history
    fp_patterns = _extract_fp() if _extract_fp else None

    # 9-10. Apply policy (with truncation context + FP memory)
    outcome = apply_policy(review, mode, threshold, allow_once, min_confidence,
                           truncated=truncated, skipped_files=skipped_files,
                           override_reason=override_reason, language=language,
                           truncation_policy=truncation_policy,
                           fp_patterns=fp_patterns)

    # Expose filtered issues for downstream consumers (e.g. gates/result.py)
    _calibrated = calibrate_evidence(review.get("issues", []), fp_patterns=fp_patterns)
    outcome["issues"] = filter_by_confidence(_calibrated, min_confidence)

    # Add coverage visibility
    outcome["reviewed_files"] = reviewed_count
    outcome["total_files"] = total_candidates
    outcome["coverage_pct"] = coverage_pct
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
    )

    return outcome


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
