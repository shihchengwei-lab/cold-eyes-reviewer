# Tuning Guide

How to diagnose and adjust Cold Eyes settings based on real usage data.

## Start here

The defaults work well for most repos:

```yaml
mode: block
model: sonnet
block_threshold: critical
confidence: medium
scope: working
truncation_policy: warn
minimum_coverage_pct: 80
coverage_policy: warn
fail_on_unreviewed_high_risk: true
```

This is the default gate posture. Auto-tune adjusts around it from history.

## Week 1: observe

```bash
# Check stats
python cold_eyes/cli.py stats --last 7d

# Check quality report
python cold_eyes/cli.py quality-report --last 7d

# Inspect the automatic tuning decision
python cold_eyes/cli.py auto-tune --last 7d
```

Look at these numbers:

| Metric | Healthy range | Action if out of range |
|--------|--------------|----------------------|
| Block rate | 5-30% | Below 5%: normal. Above 30%: inspect causes before changing threshold |
| Override rate | 0-15% | Above 15%: check override reasons, add to ignore file |
| Infra failure rate | 0-5% | Above 5%: run `doctor`, check Claude CLI |

## When to adjust threshold

| Situation | Current | Change to | Why |
|-----------|---------|-----------|-----|
| Too many blocks on style issues | `critical` | Already correct | Critical should not block style |
| Missing real bugs | `critical` | `major` | Catches more issues, more friction |
| Blocking on every commit | `major` | `critical` | Reduce friction to critical-only |

## When to adjust confidence

| Situation | Current | Change to | Why |
|-----------|---------|-----------|-----|
| False positives from uncertain calls | `medium` | `high` | Filters out medium-confidence issues |
| Missing issues the model flags at medium | `high` | `medium` | Includes more findings |
| Want maximum recall | `medium` | `low` | Rarely useful, may add noise |

Sweep data (from `python cold_eyes/cli.py eval --eval-mode sweep`):
- `critical/high`: F1=0.93 (filters some legitimate medium-confidence issues)
- `critical/medium`: F1=1.00 (recommended default)
- `critical/low`: F1=1.00 (no benefit over medium in eval set)

## When to change scope

| Workflow | Recommended scope | Why |
|----------|------------------|-----|
| Solo dev, exploring | `working` | See everything |
| About to commit | `staged` | Review exactly what will be committed |
| PR review | `pr-diff` (+ base) | Full branch diff |
| CI gate | `pr-diff` (+ base) | Deterministic, no local state |

If you switch to `staged` or `pr-diff`, truncation risk usually drops (smaller diffs).

## When to add to .cold-review-ignore

Check noisy paths:

```bash
python cold_eyes/cli.py quality-report --last 7d
```

Look at the `top_noisy_paths` section. Add patterns for:
- Generated files (`*.generated.*`, `*.min.js`)
- Vendor code (`vendor/`, `node_modules/`)
- Binary assets (`*.png`, `*.jpg`)
- Lock files (`package-lock.json`, `poetry.lock`)

## Auto-tune

`auto-tune` turns recent history into conservative policy inputs instead of a
human-facing report. It prioritizes review quality first and speed second.
Normal `run` executes the same check automatically at low frequency, so Stop
hook usage does not depend on a remembered command.

```bash
# Inspect the current automatic decision
python cold_eyes/cli.py auto-tune --last 7d

# Optional manual repo-local write
python cold_eyes/cli.py auto-tune --last 7d --write-auto-policy
```

Automatic tuning writes a repo-specific policy under
`~/.claude/cold-review-auto-policies/`, keeping the working tree clean. Manual
`--write-auto-policy` writes `.cold-review-policy.auto.yml` in the repo. Manual
`.cold-review-policy.yml` values override all auto files, so explicit repo
policy stays in control.

Auto-tune may reduce `context_tokens` when recent reviews are clean but slow or
token-heavy. It does not reduce the primary diff budget. It will hold or
increase strictness instead of reducing time when recent history contains
blocks, overrides, infra failures, coverage blocks, or unreviewed high-risk
files. Intent-mismatch blocks also hold quality, because they indicate the
agent may be drifting away from the user's recent goal.

Automatic tuning defaults:

```bash
COLD_REVIEW_AUTO_TUNE=on
COLD_REVIEW_AUTO_TUNE_INTERVAL_HOURS=24
COLD_REVIEW_AUTO_TUNE_LAST=7d
COLD_REVIEW_AUTO_TUNE_MIN_SAMPLES=5
```

Set `COLD_REVIEW_AUTO_TUNE=off` to disable automatic writes.

Agent protection and intent-capsule defaults:

```bash
COLD_REVIEW_AGENT_BRIEF=on
COLD_REVIEW_INTENT_CONTEXT=on
COLD_REVIEW_INTENT_MAX_CHARS=1200
```

`COLD_REVIEW_INTENT_CONTEXT` only supplies a low-weight hint. Intent findings
without concrete diff evidence are downgraded below the default confidence
threshold and do not block.

Fixed safety floor:

```yaml
block_threshold: critical
confidence: medium
minimum_coverage_pct: 80
coverage_policy: warn
fail_on_unreviewed_high_risk: true
```

## When to use truncation policy

| Situation | Policy | Why |
|-----------|--------|-----|
| Normal usage | `warn` | Truncation adds warning, doesn't change decision |
| Large monorepo, frequent truncation | `soft-pass` | Don't block when review is incomplete and found nothing |
| High-security, every file must be reviewed | `fail-closed` | Block if ANY files were skipped |

## Diagnostic workflow

1. Something feels wrong (too many blocks, missed issue, etc.)
2. Run `quality-report --last 7d` to see rates
3. Check the `auto_tune` field in `run` output, or run `auto-tune --last 7d`
4. Run `aggregate-overrides` to see why people override
5. Check `stats --last 7d --by-path` for noisy repos
6. Adjust settings in `.cold-review-policy.yml` if you want to override automation
7. Wait another week, re-check
