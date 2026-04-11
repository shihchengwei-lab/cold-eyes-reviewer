"""Pipeline orchestrator — coordinates the full review flow."""

import os
import tempfile

from cold_eyes.constants import SCHEMA_VERSION
from cold_eyes.git import git_cmd, collect_files, build_diff
from cold_eyes.filter import filter_file_list, rank_file_list
from cold_eyes.prompt import build_prompt_text
from cold_eyes.claude import call_claude
from cold_eyes.review import parse_review_output
from cold_eyes.policy import apply_policy
from cold_eyes.history import log_to_history
from cold_eyes.config import load_policy


def _resolve(cli_val, env_name, policy, policy_key, default, cast=None):
    """Resolve a setting.  CLI arg > env var > policy file > default."""
    if cli_val is not None:
        return cast(cli_val) if cast else cli_val
    env = os.environ.get(env_name)
    if env is not None:
        return cast(env) if cast else env
    pol = policy.get(policy_key)
    if pol is not None:
        return cast(pol) if cast else pol
    return default


def run(mode=None, model=None, max_tokens=None, threshold=None,
        confidence=None, language=None, scope=None, override_reason=None):
    """Execute full review pipeline. Return FinalOutcome dict."""
    cwd = os.getcwd()
    repo_root = git_cmd("rev-parse", "--show-toplevel")
    policy = load_policy(repo_root)

    # Resolve settings: CLI arg > env var > policy file > default
    mode = _resolve(mode, "COLD_REVIEW_MODE", policy, "mode", "block")
    model = _resolve(model, "COLD_REVIEW_MODEL", policy, "model", "opus")
    max_tokens = _resolve(max_tokens, "COLD_REVIEW_MAX_TOKENS", policy,
                          "max_tokens", 12000, cast=int)
    threshold = _resolve(threshold, "COLD_REVIEW_BLOCK_THRESHOLD", policy,
                         "block_threshold", "critical")
    min_confidence = _resolve(confidence, "COLD_REVIEW_CONFIDENCE", policy,
                              "confidence", "medium")
    if isinstance(min_confidence, str):
        min_confidence = min_confidence.lower()
    scope = _resolve(scope, "COLD_REVIEW_SCOPE", policy, "scope", "working")
    language = _resolve(language, "COLD_REVIEW_LANGUAGE", policy, "language", None)

    # mode=off: skip immediately (normally caught by shell, but policy file may set it)
    if mode == "off":
        return _skip("mode is off")

    allow_once = os.environ.get("COLD_REVIEW_ALLOW_ONCE") == "1"
    override_reason = override_reason or os.environ.get("COLD_REVIEW_OVERRIDE_REASON", "")
    ignore_file = os.path.join(repo_root, ".cold-review-ignore") if repo_root else ""

    # 1. Collect files
    all_files, untracked = collect_files(scope)
    if not all_files:
        log_to_history(cwd, mode, model, "skipped", "no changes",
                       min_confidence=min_confidence, scope=scope)
        return _skip("no changes")

    # 2. Filter
    filtered = filter_file_list(all_files, ignore_file)
    if not filtered:
        log_to_history(cwd, mode, model, "skipped", "all files ignored",
                       min_confidence=min_confidence, scope=scope)
        return _skip("all files ignored")

    # 3. Rank
    ranked = rank_file_list(filtered, untracked)

    # 4. Build diff
    diff_text, file_count, token_count, truncated, skipped = build_diff(
        ranked, untracked, max_tokens, scope
    )

    if not diff_text.strip():
        log_to_history(cwd, mode, model, "skipped", "no diff content",
                       min_confidence=min_confidence, scope=scope)
        return _skip("no diff content")

    # 5. Build prompt
    prompt_text = build_prompt_text(language)
    prompt_fd = tempfile.NamedTemporaryFile(
        mode="w", suffix=".txt", delete=False, encoding="utf-8"
    )
    prompt_fd.write(prompt_text)
    prompt_fd.close()

    try:
        # 6. Call claude
        raw_output, exit_code = call_claude(diff_text, model, prompt_fd.name)

        # 7. Handle CLI errors
        if exit_code != 0:
            review = _infra_review(f"claude exit {exit_code}")
            outcome = apply_policy(review, mode, threshold, allow_once, min_confidence,
                                   override_reason=override_reason)
            log_to_history(cwd, mode, model, outcome["state"],
                           reason=review["summary"], min_confidence=min_confidence,
                           scope=scope, override_reason=override_reason)
            return outcome

        if not raw_output:
            review = _infra_review("empty output")
            outcome = apply_policy(review, mode, threshold, allow_once, min_confidence,
                                   override_reason=override_reason)
            log_to_history(cwd, mode, model, outcome["state"],
                           reason=review["summary"], min_confidence=min_confidence,
                           scope=scope, override_reason=override_reason)
            return outcome

        # 8. Parse review
        review = parse_review_output(raw_output)

        # 9-10. Apply policy (with truncation context)
        outcome = apply_policy(review, mode, threshold, allow_once, min_confidence,
                               truncated=truncated, skipped_files=skipped,
                               override_reason=override_reason)

        # 11. Log
        diff_line_count = diff_text.count("\n") + 1
        log_to_history(
            cwd, mode, model, outcome["state"],
            review=review, file_count=file_count,
            line_count=diff_line_count, truncated=truncated,
            token_count=token_count, min_confidence=min_confidence,
            scope=scope, override_reason=override_reason,
        )

        return outcome
    finally:
        os.unlink(prompt_fd.name)


def _skip(reason):
    return {
        "action": "pass",
        "state": "skipped",
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
