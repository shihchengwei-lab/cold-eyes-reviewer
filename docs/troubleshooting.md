# Troubleshooting

## Reviews are not running

1. Check history: `tail -5 ~/.claude/cold-review-history.jsonl | python -m json.tool`
2. Run diagnostics: `python ~/.claude/scripts/cold_eyes/cli.py doctor`
3. Look for `skipped` entries and check `gate_state`: `skipped_no_change`, `skipped_safe`, `protected_cached`, or `off_explicit`
4. Look for `infra_failed` or `blocked_infra` entries — check `failure_kind` and `stderr_excerpt`

## Every commit is blocked

Distinguish between **infrastructure blocks** and **review blocks**:

- `blocked_infra` → the reviewer itself could not verify a review-required change. Check `failure_kind` in history. Common: Claude CLI auth expired (`claude -d`), timeout, encoding error.
- `blocked_issue` / `blocked_unreviewed_delta` / `blocked_stale_review` → Cold Eyes blocked the current changeset. Read the block reason. If it's a false positive, use `arm-override --reason "..."` for one-time bypass.
- `truncation_policy: fail-closed` blocks all truncated diffs. Switch to `warn` (default) or increase `max_tokens`.

## False positive blocks

1. Read the block output — is the issue real?
2. One-time bypass: `python ~/.claude/scripts/cold_eyes/cli.py arm-override --reason "false positive: ..."`
3. Recurring pattern? Check: `python ~/.claude/scripts/cold_eyes/cli.py aggregate-overrides`
4. Tune thresholds: raise `confidence` to `high`, or raise `block_threshold` — see `docs/tuning.md`
5. File-level ignore: add the pattern to `.cold-review-ignore`

## Doctor reports failures

All `fail` messages now include `Fix:` instructions. Common failures:

| Check | Fix |
|-------|-----|
| `deploy_files` | Re-run `bash install.sh` from the repo root |
| `settings_hook` | Add Stop hook entry to `~/.claude/settings.json` (see README) |
| `claude_cli` | Install Claude Code CLI, verify with `claude --version` |
| `legacy_helper` | Run `doctor --fix` to auto-remove, or delete manually |
| `shell_version` | Re-run `bash install.sh` to update the shell script |
| `health_schedule` | Re-run `bash install.sh` or `python ~/.claude/scripts/cold_eyes/cli.py install-health-schedule` |

## Agent health notice schedule

The install script creates a weekly low-detail health notice schedule by default. It runs `agent-notice --write --only-problem`: healthy checks clear old notices; setup/tool problems write `~/.claude/cold-review-agent-notice.txt`, which the Stop hook surfaces to the Agent on the next run.

`doctor --fix` restores the schedule when supported and clears stale notices once health is clean.

Notice levels:

- `attention` — Cold Eyes needs Agent attention.
- `gate_unreliable` — do not rely on the gate until setup is fixed.
- `schedule_missing` — the background health notice schedule is missing.

Adjust the cadence:

```bash
python ~/.claude/scripts/cold_eyes/cli.py install-health-schedule --every-days 14 --time 08:30
```

Remove it:

```bash
python ~/.claude/scripts/cold_eyes/cli.py remove-health-schedule
```

## Windows-specific issues

- **Use Git Bash**, not PowerShell or CMD. The shell shim is Bash.
- **Encoding errors** were fixed in v1.2.0 (forced UTF-8 in subprocess). If you see `UnicodeDecodeError`, update to latest version.
- **Lock reliability** — `kill -0` stale PID detection is less reliable in Git Bash. If reviews stall, delete `~/.claude/.cold-review-lock.d/` manually. v2 records changed-source lock contention as `blocked_lock_active`.

## History file is too large

```bash
# Keep last 90 days
python ~/.claude/scripts/cold_eyes/cli.py history-prune --keep-days 90

# Or keep last 500 entries
python ~/.claude/scripts/cold_eyes/cli.py history-prune --keep-entries 500

# Archive old entries
python ~/.claude/scripts/cold_eyes/cli.py history-archive --before 2026-01-01
```

## Claude CLI not found

- Install Claude Code: https://docs.anthropic.com/en/docs/claude-code
- Verify: `claude --version`
- Check auth: `claude -d` (shows subscription status)
- Ensure `claude` is on PATH in Git Bash: `which claude`

## Truncation warnings

When diffs exceed the token budget, some files are skipped. Options:

1. **Increase budget:** set `COLD_REVIEW_MAX_TOKENS=20000` (or in policy file: `max_tokens: 20000`)
2. **Exclude noise:** add patterns to `.cold-review-ignore` (e.g., `dist/*`, generated fixtures). Avoid ignoring package locks, workflow files, hook scripts, or gate-engine files unless that is intentional policy.
3. **Use smaller primary scope:** `COLD_REVIEW_SCOPE=staged` keeps staged changes as the main target while v2 still scans source/config shadow delta
4. **Adjust delta budget:** raise `COLD_REVIEW_MAX_SHADOW_DELTA_FILES` or `COLD_REVIEW_MAX_SHADOW_DELTA_BYTES` if shadow delta is intentionally larger
