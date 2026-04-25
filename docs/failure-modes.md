# Failure Modes

## Review states

Every review exits through one legacy-compatible `state` plus a v2 `gate_state`, logged to `~/.claude/cold-review-history.jsonl`:

| State | Entry condition | Block mode | Report mode |
|-------|----------------|------------|-------------|
| `skipped` | No review needed, safe-only changes, cache hit, or explicit off | exit 0 | exit 0 |
| `infra_failed` | Infrastructure failure where review was not required | logs, passes | logs, passes |
| `passed` | Review completed, no issues at/above threshold | passes | passes |
| `reported` | Issues found but mode is report | n/a | logs, passes |
| `blocked` | Issues at/above threshold, incomplete coverage, hard local check failure, unreviewed delta, stale review, lock contention, or review-required infra failure | **blocks** | n/a |
| `overridden` | Would have blocked, but override token was armed | passes | n/a |

`gate_state` is the authoritative v2 protection signal: `protected`, `protected_cached`, `skipped_no_change`, `skipped_safe`, `blocked_issue`, `blocked_unreviewed_delta`, `blocked_stale_review`, `blocked_infra`, `blocked_lock_active`, and `off_explicit`.

## Infrastructure failures

History entries for `infra_failed` include `failure_kind` and `stderr_excerpt`:

| `failure_kind` | Cause | Diagnosis |
|----------------|-------|-----------|
| `timeout` | Claude CLI did not respond within timeout | Check network, Claude service status, model load |
| `cli_not_found` | `claude` command not on PATH | Install Claude Code CLI, verify with `claude --version` |
| `cli_error` | Claude CLI returned non-zero exit | Check `stderr_excerpt`, run `claude -d` for auth/rate issues |
| `empty_output` | Claude CLI returned empty stdout | Usually transient; check `stderr_excerpt` for clues |

If `infra_failed` occurs repeatedly, run `doctor` and check the last few history entries:
```bash
python ~/.claude/scripts/cold_eyes/cli.py doctor
tail -5 ~/.claude/cold-review-history.jsonl | python -m json.tool
```

Current engine policy blocks review-required infra failures as `gate_state: blocked_infra`. No-change, safe-only, or cached paths do not manufacture an infra block. Shell-level failures that prevent valid engine JSON from being produced still fail closed in `cold-review.sh`.

## Truncation

When a diff exceeds the token budget (default 12000), files are truncated by risk priority. The outcome includes:

- `truncated_files` — files partially included
- `budget_skipped_files` — files entirely skipped due to budget
- `coverage_pct` — percentage of changed files included in the review

The `truncation_policy` setting controls what happens:

| Policy | Truncated + no issues | Truncated + issues |
|--------|----------------------|-------------------|
| `warn` (default) | pass (with warning) | normal threshold logic |
| `soft-pass` | pass (no warning) | normal threshold logic |
| `fail-closed` | **block** | **block** |

To reduce truncation: increase `max_tokens`, add patterns to `.cold-review-ignore`, or use `scope: staged` to review smaller changesets.

## Lock contention

The shell shim uses `mkdir`-based atomic locking in `~/.claude/.cold-review-lock.d/`. If a lock is held:
- The PID file is checked with `kill -0` to detect stale locks
- Stale locks are automatically removed and retried once
- If the lock is genuinely held, the shell asks the engine for a lightweight envelope decision
- No-change or cache-hit envelopes can pass; source/config changes that need review block as `blocked_lock_active`

**Windows caveat:** `kill -0` in Git Bash is less reliable for Windows PIDs. Concurrent Claude Code sessions may occasionally bypass the lock.

## Parse failures

If the LLM returns malformed JSON:
1. `parse_review_output()` strips markdown code fences and retries
2. If parsing still fails, a synthetic review with `review_status: "failed"` is created
3. `validate_review()` checks field types and values; errors are logged in `validation_errors` but do not block
4. If review is required, current engine behavior blocks as `blocked_infra`. If no review is required, it records `infra_failed` and passes. Shell-level parser failures still fail closed when no valid engine JSON can be read.

## Coverage incomplete

Coverage is evaluated after the diff is filtered and risk-ranked. `partial_files`, `skipped_budget`, `skipped_binary`, and `skipped_unreadable` count as unreviewed.

| Condition | Result |
|-----------|--------|
| Coverage below `minimum_coverage_pct` and `coverage_policy: warn` | Passes, logs `coverage_warning` |
| Coverage below `minimum_coverage_pct` and `coverage_policy: block` | Blocks only in `mode: block` |
| Any unreviewed file with `coverage_policy: fail-closed` | Blocks only in `mode: block` |
| High-risk unreviewed file and `fail_on_unreviewed_high_risk: true` | Blocks only in `mode: block` |

Coverage block is distinct from review block: it does not add to `issues`, sets `cold_eyes_verdict: incomplete`, `final_action: coverage_block`, and `authority: coverage_gate`.

## Review target incomplete

The target sentinel runs before model review. It records what the configured scope will review and what remains outside it.

| Condition | Default result |
|-----------|----------------|
| Unstaged source/config outside `staged` scope | Reviewed as shadow delta or blocks as `blocked_unreviewed_delta` |
| Untracked source/config outside `staged` or `head` scope | Reviewed as shadow delta or blocks as `blocked_unreviewed_delta` |
| Docs/generated/image-only outside the primary target | Can pass as `skipped_safe` |
| High-risk partially staged file | Blocks only in `mode: block` |

Target and delta blocks are distinct from model review blocks: they do not add to `issues`. v1 target blocks use `final_action: target_block`; v2 unreviewed delta blocks use `final_action: unreviewed_delta_block`, `authority: delta_sentinel`, and `gate_state: blocked_unreviewed_delta`.

## False positives

To reduce false positive blocks:
1. **Confidence filter** — raise `confidence` to `high` (keeps only high-confidence issues)
2. **Override** — `arm-override --reason "..."` for one-time bypass
3. **Threshold** — raise `block_threshold` to `critical` (default; only critical issues block)
4. **Tuning** — see `docs/tuning.md` for diagnostic workflow
5. **Patterns** — check `aggregate-overrides` for recurring override reasons; consider adding to `.cold-review-ignore`
