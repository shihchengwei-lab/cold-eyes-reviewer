# Failure Modes

## Review states

Every review exits through one of six states, logged to `~/.claude/cold-review-history.jsonl`:

| State | Entry condition | Block mode | Report mode |
|-------|----------------|------------|-------------|
| `skipped` | No changes, all files ignored, not a git repo, lock held | exit 0 | exit 0 |
| `infra_failed` | Git error, Claude CLI error/timeout, empty output, parse failure | logs, passes | logs, passes |
| `passed` | Review completed, no issues at/above threshold | passes | passes |
| `reported` | Issues found but mode is report | n/a | logs, passes |
| `blocked` | Issues at/above threshold, incomplete coverage, hard local check failure, or review-target mismatch in block mode | **blocks** | n/a |
| `overridden` | Would have blocked, but override token was armed | passes | n/a |

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

Current engine policy treats `infra_failed` as pass-and-log, even in block mode. Shell-level failures that prevent valid engine JSON from being produced still fail closed in `cold-review.sh`.

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
- If the lock is genuinely held, the review is skipped (not blocked)

**Windows caveat:** `kill -0` in Git Bash is less reliable for Windows PIDs. Concurrent Claude Code sessions may occasionally bypass the lock.

## Parse failures

If the LLM returns malformed JSON:
1. `parse_review_output()` strips markdown code fences and retries
2. If parsing still fails, a synthetic review with `review_status: "failed"` is created
3. `validate_review()` checks field types and values; errors are logged in `validation_errors` but do not block
4. Current engine behavior records `infra_failed` and passes. Shell-level parser failures still fail closed when no valid engine JSON can be read.

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
| Unstaged files outside `staged` scope | Passes with target warning |
| Untracked files outside `staged` or `head` scope | Passes with target warning |
| High-risk partially staged file | Blocks only in `mode: block` |

Target blocks are distinct from model review blocks: they do not add to `issues`, set `cold_eyes_verdict: target_incomplete`, `final_action: target_block`, and `authority: target_sentinel`.

## False positives

To reduce false positive blocks:
1. **Confidence filter** — raise `confidence` to `high` (keeps only high-confidence issues)
2. **Override** — `arm-override --reason "..."` for one-time bypass
3. **Threshold** — raise `block_threshold` to `critical` (default; only critical issues block)
4. **Tuning** — see `docs/tuning.md` for diagnostic workflow
5. **Patterns** — check `aggregate-overrides` for recurring override reasons; consider adding to `.cold-review-ignore`
