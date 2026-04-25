# Agent Setup Guide

Instructions for an AI agent to install and configure Cold Eyes Reviewer.

## What Cold Eyes does

Cold Eyes is a Claude Code Stop hook that reviews every code change before it's committed. When it finds critical issues (SQL injection, hardcoded secrets, etc.), it blocks the commit and explains why.

## Installation (5 steps)

### Step 1: Install files

```bash
cd /path/to/cold-eyes-reviewer
bash install.sh
```

This copies `cold-review.sh`, `cold-review-prompt.txt`, and `cold_eyes/` to `~/.claude/scripts/`.
It also creates a low-noise health notice schedule by default. The schedule runs every 7 days at 09:00 and writes an Agent notice only when the gate setup needs attention.

To adjust the interval during install:

```bash
COLD_REVIEW_HEALTH_INTERVAL_DAYS=14 COLD_REVIEW_HEALTH_TIME=08:30 bash install.sh
```

### Step 2: Configure the Stop hook

Add to `~/.claude/settings.json`:

```json
{
  "hooks": {
    "Stop": [
      {
        "type": "command",
        "command": "bash ~/.claude/scripts/cold-review.sh"
      }
    ]
  }
}
```

If `hooks.Stop` already has entries, append to the array.

### Step 3: Verify installation

```bash
python ~/.claude/scripts/cold_eyes/cli.py verify-install
```

Expected output:
```json
{"action": "verify-install", "ok": true, "failures": []}
```

If `ok` is false, check the `failures` array for which check failed.

### Step 4: Run full diagnostics

```bash
python ~/.claude/scripts/cold_eyes/cli.py doctor
```

All checks should be `ok` or `info`. Any `fail` status needs attention.

### Step 5: Initialize repo (optional)

```bash
cd /path/to/your-repo
python ~/.claude/scripts/cold_eyes/cli.py init
```

Creates `.cold-review-policy.yml` and `.cold-review-ignore` with defaults.

## Recommended initial settings

For the first week, use report mode to observe without blocking:

```yaml
# .cold-review-policy.yml
mode: report
block_threshold: critical
confidence: medium
```

After one week, check results and switch to block mode:

```yaml
mode: block
```

## Handling common situations

### Cold Eyes blocks a commit

The block message explains the issue. Options:
1. Fix the issue (preferred)
2. Override once: `python ~/.claude/scripts/cold_eyes/cli.py arm-override --reason "reason"`
3. Add to ignore: edit `.cold-review-ignore`

### Doctor check fails

| Check | Fix |
|-------|-----|
| `deploy_files` | Re-run `bash install.sh` |
| `settings_hook` | Add hook entry to `~/.claude/settings.json` |
| `git_repo` | Run from inside a git repository |
| `legacy_helper` | Run `doctor --fix` or delete `~/.claude/scripts/cold-review-helper.py` |
| `shell_version` | Re-run `bash install.sh` to update shell script |
| `health_schedule` | Re-run `bash install.sh` or run `install-health-schedule` |

`doctor --fix` can auto-remove the legacy helper, restore the Agent health notice schedule when supported, and clear stale health notices after the setup is clean.

### settings.json doesn't exist

Create it:
```json
{
  "hooks": {
    "Stop": [
      {
        "type": "command",
        "command": "bash ~/.claude/scripts/cold-review.sh"
      }
    ]
  }
}
```

### settings.json already has hooks

Merge the Cold Eyes hook into the existing `hooks.Stop` array. Do not replace existing hooks.

## Verifying it works

After setup, make a small change in any git repo and run:

```bash
python ~/.claude/scripts/cold_eyes/cli.py run --mode report
```

Expected: JSON output with `"action": "pass"` or `"action": "block"` and a review summary.
