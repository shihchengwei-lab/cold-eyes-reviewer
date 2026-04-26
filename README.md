# Cold Eyes Reviewer

![Tests](https://github.com/shihchengwei-lab/cold-eyes-reviewer/actions/workflows/test.yml/badge.svg)
![Claude Code](https://img.shields.io/badge/Claude%20Code-Stop--hook-blue)
![Review](https://img.shields.io/badge/Review-diff--centered-green)
![Scope](https://img.shields.io/badge/Scope-not%20full%20review-lightgrey)

A diff-centered, second-pass review gate for [Claude Code](https://docs.anthropic.com/en/docs/claude-code). Runs automatically after every session turn via Stop hook, defaults to gate mode, auto-tunes the quality/time balance from local review history, and turns blocks into agent repair tasks with a fresh-review rerun protocol.

This tool was built after observing [Cinder](https://not-a-mascot.vercel.app/index-en.html), a Claude Code buddy companion that provided independent commentary during coding sessions. Cinder was silently shut down on April 11, 2026. Cold Eyes carries forward the idea that a second pair of eyes — even artificial ones — catches things the first pair misses. Cinder was a companion. Cold Eyes is a gate.

## Quick start

```bash
bash install.sh
python ~/.claude/scripts/cold_eyes/cli.py init
python ~/.claude/scripts/cold_eyes/cli.py doctor
```

Then add the Stop hook shown in the Install section to `~/.claude/settings.json`.

Cold Eyes treats staged changes as the primary review target by default. Pure chat and no-change turns skip quickly, while unstaged or untracked source/config changes are scanned as delta protection so they cannot silently pass.

## What it is

Cold Eyes runs as a Stop hook after each Claude Code turn. It is diff-first: staged changes are the primary intent, and v2 adds a fast review envelope that decides whether to skip, reuse cache, review, or block before calling the model. The default posture is quality-first gate mode: block medium-confidence critical findings, prevent source/config deltas from silently passing, preserve high-risk coverage protection, and let low-frequency auto-tune reduce review time only after recent history is clean. When it blocks, it produces an agent-facing repair task, a plain-language message the agent can relay to a non-engineer user, and a rerun protocol: fix the current diff, run relevant checks, stage the changes that should be reviewed, then end the turn so the next Stop hook starts a fresh Cold Eyes review. It does not compare against previous block records. On the deep path it pulls in **limited, structured supporting context** such as recent commit messages, co-changed files from git history, detector hints, and an optional low-weight user-intent capsule from Claude Code hook metadata. In the unified v2 path, Cold Eyes can also run selected local checks (tests, lint, type, build) once when the diff shape justifies it.

## What it is not

- **Not a replacement for human review.** It is a pre-hint before the real reviewer looks.
- **Not a full PR review platform.** No cross-file search, no repo-wide symbol analysis, no issue tracking.
- **Not a full-context code understanding system.** What the deep path sees is bounded to a handful of git-adjacent signals, not the whole codebase.
- **Not requirement-aware / intent-aware in the strong sense.** The optional intent capsule is a low-weight hint. A mismatch still needs concrete diff evidence before it can block.
- **Not a sufficient gate for semantic design correctness.** Multi-file logic, business rules, architectural decisions are out of scope.

## When it works best

- Claude Code workflows where an automatic second pass catches surface-level slips before they compound.
- Catching high-cost surface issues: removed error handling, hardcoded secrets, dangling references within the diff, obvious injection shapes.
- Claude Code loops where quality-first blocking is useful, with auto-tune trimming review time only after recent history stays clean.

## When not to use it as a blocking gate

- Tasks where the bug is driven by requirements or specs that are not visible in the diff.
- Large, non-local semantic refactors where most of the signal lives outside the changed lines.
- Teams with very low false-positive tolerance that have not yet measured Cold Eyes' noise rate on their own code.
- Repos that cannot tolerate any interruption yet. Use `COLD_REVIEW_MODE=report` as a temporary local override while collecting history.

## Review paths overview

- **Shallow** — test-only or low-risk diffs. Lighter model, critical-only prompt, diff as sole input. Fast and cheap.
- **Deep** (default for source changes) — full model, diff + bounded supporting context + detector hints. This is what the project name refers to: a diff-centered review with a small amount of structured support.
- **Automatic local checks** — when a risky Python or dependency change is present, the unified v2 path may run available checks once and fold the result into the same gate outcome.

### Why deeper paths exist

The diff alone is sometimes not enough to distinguish a real bug from a valid change (a renamed function, a removed resource that was handled elsewhere). The deep path's context block and detector hints exist to reduce that class of false calls without turning the tool into a full-context reviewer. Local checks add mechanical evidence without creating a second review mode: they run once, do not retry, and do not validate against prior block history.

## How it works

The v2 gate starts with a fast envelope scan. It skips pure chat/no-change turns, skips docs/generated-only changes when safe, reuses a trusted cache when the effective envelope is unchanged, and only calls the model when source/config changes need review. If source/config delta cannot fit in the review target, or the working tree changes during review, it blocks instead of silently passing.

```
Claude Code session ends
       │
       ▼
  cold-review.sh (shim — guards + fail-closed result parser)
       │
       ├─ off mode / recursion / no git repo → exit
       ├─ atomic lock held by another review → lightweight envelope decision
       │
       ▼
  cold_eyes/cli.py → engine.py (unified v2)
       │
       ├─ 1. envelope scan → 2. target/cache decision → 3. risk-rank
       ├─ 4. triage: skipped_safe / shallow (test-only) / deep (source/risk)
       │      skip → exit immediately, no model call
       │      shallow → lighter model (sonnet) + critical-only prompt
       │      deep → full pipeline below
       ├─ 5. build diff (token-budgeted, high-risk files first)
       ├─ 6. context retrieval (deep only: recent commits + co-changed files from git)
       ├─ 7. detector hints (deep only: regex state/invariant signals + repo-type focus)
       ├─ 8. call Claude CLI with system prompt
       ├─ 9. parse review → FP memory lookup → evidence calibration → confidence filter
       ├─ 10. policy decision
       │
       ├─ block mode: issues at or above threshold → block
       │      Agent fixes current diff → ends turn → next Stop hook starts a fresh review
       ├─ report mode: log review → pass
       ├─ 11. selected local checks run once when useful
       └─ all engine-level exits logged to ~/.claude/cold-review-history.jsonl
          (no git repo and recursion guard exits are still shell-only)
```

## Output format

Every issue includes severity, confidence, category, file, line_hint, a three-part structure (check / verdict / fix), and evidence-bound fields:

```json
{
  "schema_version": 1,
  "pass": false,
  "review_status": "completed",
  "summary": "Chinese page links to English chapter",
  "issues": [
    {
      "severity": "major",
      "confidence": "high",
      "category": "reference",
      "file": "index.html",
      "line_hint": "L43",
      "check": "index.html line 43 links to ch3-en.html but this is the Chinese page",
      "verdict": "Cross-language reference.",
      "fix": "Change to ch3.html",
      "evidence": ["line 43: href=\"ch3-en.html\" in a zh-TW page block"],
      "what_would_falsify_this": "If ch3-en.html is intentionally linked as a cross-language reference",
      "suggested_validation": "Check if other zh pages also link to -en variants",
      "abstain_condition": ""
    }
  ]
}
```

- `evidence` — specific diff lines or facts supporting the claim. Issues with high confidence but empty evidence are automatically downgraded to medium.
- `what_would_falsify_this` — conditions under which the claim would not hold.
- `suggested_validation` — how to verify the claim (run a test, check a file, etc.).
- `abstain_condition` — hidden context the claim assumes. Issues with abstain conditions are downgraded by one confidence level.

- `schema_version` — model review output schema version (currently `1`). Bumped on breaking changes to the review JSON structure (field removal, semantic change, required field addition). Adding optional fields (e.g., `override_reason`) does not bump the version.
- envelope `schema_version` — gate-envelope schema version (currently `2`). This is separate from the LLM review issue schema.
- `gate_state` — authoritative v2 gate state, such as `protected`, `protected_cached`, `skipped_no_change`, `skipped_safe`, `blocked_unreviewed_delta`, `blocked_stale_review`, or `blocked_infra`.
- `line_hint` — approximate line reference from diff hunk headers (e.g., `"L42"`, `"L42-L50"`). Empty string when uncertain. Displayed with `~` prefix (e.g., `(~L42)`) to indicate it is an estimate, not a precise location. In block mode, verify the line number before acting on it.
- `protection` — optional block wrapper with `user_message`, `agent_task`, `risk_summary`, `rerun_protocol`, and low-weight intent metadata. It is added after the review decision and does not change schema version.
- `target` — optional review-target summary with staged/unstaged/untracked counts, partial-stage files, and target policy action. It is added outside the model review and does not change schema version.
- `envelope` — optional v2 gate summary with changed files, review target, unreviewed delta, hashes, and cache identity.
- `checks` — optional local-check summary with mode, results, warnings, and whether a hard check failed. Added after the model review and does not change schema version.

**Severity levels:**
- `critical` — production crash, data loss, security breach, or evidence-backed correctness bugs that make production runtime fail directly, such as dangling imports/references, removed required error handling, resource leaks, or partial state updates
- `major` — incorrect behavior under normal use
- `minor` — suboptimal but functional

## Install

### 1. Deploy scripts

```bash
# Option A: use the install script
bash install.sh

# Option B: manual copy
mkdir -p ~/.claude/scripts
cp -r cold_eyes/ cold-review.sh cold-review-prompt.txt cold-review-prompt-shallow.txt ~/.claude/scripts/
```

The install script creates a low-noise Agent health notice schedule by default. It runs every 7 days at 09:00, writes a notice only when the gate setup needs attention, and stays quiet when healthy.

Adjust or disable it at install time:

```bash
COLD_REVIEW_HEALTH_INTERVAL_DAYS=14 COLD_REVIEW_HEALTH_TIME=08:30 bash install.sh
COLD_REVIEW_HEALTH_SCHEDULE=off bash install.sh
```

### 2. Add Stop hook to `~/.claude/settings.json`

```json
{
  "hooks": {
    "Stop": [
      {
        "hooks": [
          {
            "type": "command",
            "command": "bash ~/.claude/scripts/cold-review.sh",
            "timeout": 120000
          }
        ]
      }
    ]
  }
}
```

### 3. Initialize repo (optional)

```bash
python ~/.claude/scripts/cold_eyes/cli.py init
```

Creates a gate-mode `.cold-review-policy.yml` and `.cold-review-ignore` in the current repo if they don't exist.
Use `--force` only when you intentionally want to replace an existing policy file.

### 4. Verify installation

```bash
python ~/.claude/scripts/cold_eyes/cli.py doctor
```

Checks Python, Git, Claude CLI, deploy files, hook config, and current repo. All checks should show `"ok"`. `"info"` items are optional hints.

Use `doctor --fix` to auto-remove legacy helper if detected, restore the Agent health notice schedule when supported, and clear stale health notices after the setup is clean. Other failures require manual action.

### 5. Done

Next time Claude Code finishes a turn with uncommitted changes, Cold Eyes will review them.

### Recommended adoption path

Cold Eyes now starts in a balanced gate posture: block mode, critical-only blocking, medium confidence, fast deep model, staged scope, and coverage visibility. Auto-tune then adjusts the balance from history:

1. **Hold quality** — if recent history has blocks, overrides, infra failures, or incomplete high-risk coverage, keep full context and stronger coverage posture.
2. **Balanced** — if history is quiet and not slow, keep the baseline.
3. **Fast-safe** — if history is clean but expensive, reduce bounded context first.

## Token usage

Every review consumes tokens from your Claude usage quota. How much depends on:

- **Review depth** — skip uses zero tokens (no model call), shallow uses fewer than deep
- **Model choice** — opus costs more per token than sonnet; sonnet more than haiku
- **Diff size** — larger diffs send more input tokens (budget default: 12000)
- **Context and hints** — deep reviews add up to ~2200 tokens (context + detector hints) on top of the diff

**Automatic local checks:** selected checks (`pytest`, `ruff`, `mypy`, `pip check`) use no model tokens. They can add wall-clock time, so the default `auto` mode runs them only for risky Python or dependency changes, prefers mapped pytest targets when obvious, runs each selected check once, and treats timeouts as warnings instead of blocks.

Subscription users (Pro/Max): reviews count against your plan's usage quota, not billed separately. API users: cost follows Anthropic's published per-token pricing, which changes over time.

To reduce token usage manually: use `COLD_REVIEW_MODEL=haiku`, lower `COLD_REVIEW_MAX_TOKENS`, or set `COLD_REVIEW_CONTEXT_TOKENS=0` to disable context retrieval.

## Automatic local checks

`COLD_REVIEW_CHECKS=auto` lets the unified v2 path run selected local checks once when the diff shape justifies it:

- Python source or high-risk Python changes can run `ruff check <changed files>` and `mypy <changed files>` as soft checks.
- Test changes or high-risk Python changes in a repo with tests can run `pytest --tb=short -q` as a hard check. When an obvious matching test file exists, Cold Eyes targets that test file first instead of immediately sweeping the full suite.
- Python dependency/build config changes can run `python -m pip check --quiet` as a hard check.

Hard check failures can block in `COLD_REVIEW_MODE=block`. Soft check failures are folded into the Agent repair task but do not block by themselves. Missing tools and timeouts are warnings, not blockers.

## What gets reviewed

By default (`COLD_REVIEW_SCOPE=staged`), Cold Eyes treats staged changes as the **primary review target** (`git diff --cached`). This keeps normal reading, handoff review, and scratch work from triggering a model review on every Stop hook.

Stage the changes you want the gate to review before ending the turn. To restore the older "review everything in my working tree" behavior, set `COLD_REVIEW_SCOPE=working`.

In v2, Cold Eyes also scans a working-tree delta envelope before deciding. Unstaged or untracked source/config changes are either included in a small shadow review target or blocked as unreviewed delta when they are too large, unreadable, binary, over budget, or high risk. Docs/generated/image-only changes can skip as `skipped_safe` without calling the model.

A pass means the configured effective review target passed, not necessarily the entire working tree. In staged scope, the target sentinel still records unstaged, untracked, and partially staged files for status visibility.

Other scopes:
- `COLD_REVIEW_SCOPE=working` — review all uncommitted changes: staged, unstaged, and untracked
- `COLD_REVIEW_SCOPE=head` — review `git diff HEAD` (staged + unstaged, no untracked)
- `COLD_REVIEW_SCOPE=pr-diff` — review `git diff <base>...HEAD` (PR changes vs base branch, requires `COLD_REVIEW_BASE`)

## Configuration

### Policy file (per-repo)

Place `.cold-review-policy.yml` in your project root to override the gate defaults for that repo. This replaces the need for global environment variables in repos that need specific settings.

```yaml
# .cold-review-policy.yml
mode: report
model: sonnet
max_tokens: 8000
block_threshold: major
confidence: high
language: English
scope: staged
truncation_policy: warn
minimum_coverage_pct: 80
coverage_policy: warn
fail_on_unreviewed_high_risk: true
dirty_worktree_policy: warn
untracked_policy: warn
partial_stage_policy: block-high-risk
shadow_scope: working_delta
include_untracked: true
enable_envelope_cache: true
max_shadow_delta_files: 8
max_shadow_delta_bytes: 60000
infra_failure_policy: block_when_review_required
lock_active_policy: block_when_review_required
stale_review_policy: block
docs_only_policy: skip_safe
generated_only_policy: skip_safe
checks: auto
check_timeout_sec: 120
```

All keys are optional. Only include what you want to override.

**Resolution priority:** CLI arg > environment variable > manual policy file > auto policy file > hardcoded default.

If `COLD_REVIEW_MODE=block` is set as an env var, it overrides the policy file's `mode: report`. Manual `.cold-review-policy.yml` values override auto-tuned values. If neither env var nor policy file sets a value, the hardcoded default applies.

Supported keys: `mode`, `model`, `shallow_model`, `max_tokens`, `context_tokens`, `max_input_tokens`, `block_threshold` (or `threshold`), `confidence`, `language`, `scope`, `base`, `truncation_policy`, `minimum_coverage_pct`, `coverage_policy`, `fail_on_unreviewed_high_risk`, `dirty_worktree_policy`, `untracked_policy`, `partial_stage_policy`, `shadow_scope`, `include_untracked`, `enable_envelope_cache`, `max_shadow_delta_files`, `max_shadow_delta_bytes`, `infra_failure_policy`, `lock_active_policy`, `stale_review_policy`, `docs_only_policy`, `generated_only_policy`, `checks`, `check_timeout_sec`.

`doctor` check 8 reports whether this file exists and what keys it sets.

### Environment variables

| Variable | Default | Options | Description |
|---|---|---|---|
| `COLD_REVIEW_MODE` | `block` | `block`, `report`, `off` | Block and force fix / log only / disable |
| `COLD_REVIEW_MODEL` | `sonnet` | `opus`, `sonnet`, `haiku` | Which model runs the deep review |
| `COLD_REVIEW_SHALLOW_MODEL` | `sonnet` | `opus`, `sonnet`, `haiku` | Which model runs the shallow review |
| `COLD_REVIEW_MAX_TOKENS` | `12000` | any integer | Token budget for diff |
| `COLD_REVIEW_CONTEXT_TOKENS` | `2000` | any integer (0 = off) | Token budget for context section (deep review only) |
| `COLD_REVIEW_BLOCK_THRESHOLD` | `critical` | `critical`, `major` | Minimum severity that triggers a block |
| `COLD_REVIEW_CONFIDENCE` | `medium` | `high`, `medium`, `low` | Minimum confidence to keep (hard filter) |
| `COLD_REVIEW_LANGUAGE` | `繁體中文（台灣）` | any string | Output language |
| `COLD_REVIEW_SCOPE` | `staged` | `staged`, `working`, `head`, `pr-diff` | Diff scope: staged only / all uncommitted / vs HEAD / vs base branch |
| `COLD_REVIEW_BASE` | (unset) | any branch name | Base branch for `pr-diff` scope (e.g. `main`) |
| `COLD_REVIEW_TRUNCATION_POLICY` | `warn` | `warn`, `soft-pass`, `fail-closed` | How to handle truncated diffs (see Truncation policy) |
| `COLD_REVIEW_MINIMUM_COVERAGE_PCT` | `80` | `0`-`100` | Minimum percentage of changed files that must be fully reviewed |
| `COLD_REVIEW_COVERAGE_POLICY` | `warn` | `warn`, `block`, `fail-closed` | How to handle coverage below the minimum or incomplete coverage |
| `COLD_REVIEW_FAIL_ON_UNREVIEWED_HIGH_RISK` | `true` | `true`, `false` | Block if a high-risk path was not fully reviewed |
| `COLD_REVIEW_DIRTY_WORKTREE_POLICY` | `warn` | `ignore`, `warn`, `block-high-risk`, `block` | How unstaged files outside the review target are handled |
| `COLD_REVIEW_UNTRACKED_POLICY` | `warn` | `ignore`, `warn`, `block-high-risk`, `block` | How untracked files outside the review target are handled |
| `COLD_REVIEW_PARTIAL_STAGE_POLICY` | `block-high-risk` | `ignore`, `warn`, `block-high-risk`, `block` | How partially staged files are handled |
| `COLD_REVIEW_SHADOW_SCOPE` | `working_delta` | `working_delta`, `off`, `none` | Whether staged scope also scans unstaged/untracked source/config delta |
| `COLD_REVIEW_INCLUDE_UNTRACKED` | `true` | `true`, `false` | Include untracked files in the review envelope and shadow delta |
| `COLD_REVIEW_ENABLE_ENVELOPE_CACHE` | `true` | `true`, `false` | Reuse matching protected or blocked envelope history without another model call |
| `COLD_REVIEW_MAX_SHADOW_DELTA_FILES` | `8` | any integer | Maximum unstaged/untracked source/config files added to shadow review |
| `COLD_REVIEW_MAX_SHADOW_DELTA_BYTES` | `60000` | any integer | Maximum bytes per shadow delta file before blocking as unreviewed |
| `COLD_REVIEW_INFRA_FAILURE_POLICY` | `block_when_review_required` | `block_when_review_required`, `pass-and-log` | Whether review-required infra failures block |
| `COLD_REVIEW_LOCK_ACTIVE_POLICY` | `block_when_review_required` | `block_when_review_required`, `skip` | Whether lock contention blocks when changes need review |
| `COLD_REVIEW_STALE_REVIEW_POLICY` | `block` | `block`, `warn` | Whether file changes during review block as stale |
| `COLD_REVIEW_DOCS_ONLY_POLICY` | `skip_safe` | `skip_safe`, `shallow` | How docs-only envelopes are handled |
| `COLD_REVIEW_GENERATED_ONLY_POLICY` | `skip_safe` | `skip_safe`, `shallow` | How generated/image-only envelopes are handled |
| `COLD_REVIEW_CHECKS` | `auto` | `auto`, `off` | Run selected local checks once when useful |
| `COLD_REVIEW_CHECK_TIMEOUT_SEC` | `120` | any integer | Timeout per selected local check |
| `COLD_REVIEW_AUTO_TUNE` | `on` | `on`, `off` | Low-frequency automatic tuning after `run` |
| `COLD_REVIEW_AUTO_TUNE_INTERVAL_HOURS` | `24` | any integer | Minimum hours between automatic tuning checks per repo |
| `COLD_REVIEW_AUTO_TUNE_LAST` | `7d` | `24h`, `7d`, `2w`, etc. | History window used by automatic tuning |
| `COLD_REVIEW_AUTO_TUNE_MIN_SAMPLES` | `5` | any integer | Minimum history samples before automatic tuning writes policy |
| `COLD_REVIEW_AGENT_BRIEF` | `on` | `on`, `off` | Add agent repair task, user-facing message, and fresh-review rerun protocol to blocks |
| `COLD_REVIEW_INTENT_CONTEXT` | `on` | `on`, `off` | Read a low-weight user intent capsule from Claude Code hook metadata when available |
| `COLD_REVIEW_INTENT_MAX_CHARS` | `1200` | any integer | Character cap for the low-weight intent capsule |
| `COLD_REVIEW_ALLOW_ONCE` | (unset) | `1` | **Deprecated.** Use `arm-override` instead. Still works but emits a warning. |
| `COLD_REVIEW_OVERRIDE_REASON` | (unset) | any text | Reason for override (used with ALLOW_ONCE or arm-override) |

```bash
# Use opus for a heavier deep review
export COLD_REVIEW_MODEL=opus

# Just log, don't block
export COLD_REVIEW_MODE=report

# Block on major issues too
export COLD_REVIEW_BLOCK_THRESHOLD=major

# Only keep high-confidence issues
export COLD_REVIEW_CONFIDENCE=high

# Review in English
export COLD_REVIEW_LANGUAGE=English

# Review every working-tree change
export COLD_REVIEW_SCOPE=working

# Review PR changes against main (CI mode)
export COLD_REVIEW_SCOPE=pr-diff
export COLD_REVIEW_BASE=main

# One-time override when blocked by a false positive
python ~/.claude/scripts/cold_eyes/cli.py arm-override --reason false_positive
```

### Overriding a block

Use `arm-override` to create a one-time override token. The token is consumed on the next block and cannot be reused.

```bash
# Arm a one-time override (default: expires in 10 minutes)
python ~/.claude/scripts/cold_eyes/cli.py arm-override --reason false_positive

# Custom TTL
python ~/.claude/scripts/cold_eyes/cli.py arm-override --reason acceptable_risk --ttl 5
```

The token is scoped to the current repo. After arming, the next block will be bypassed and the reason logged to history.

Override is human risk acceptance, not a normal pass. History keeps the original `cold_eyes_verdict`, writes `final_action: override_pass`, and marks `authority: human_override`. Use `--note` for extra context:

```bash
python ~/.claude/scripts/cold_eyes/cli.py arm-override --reason acceptable_risk --note "manual review completed"
```

**Legacy:** `COLD_REVIEW_ALLOW_ONCE=1` still works but is deprecated — it cannot truly be consumed (env vars persist in the parent shell), so it bypasses *every* block while set. A deprecation warning is emitted.

### Override reasons

Common reason values:

- `false_positive`
- `acceptable_risk`
- `urgent_hotfix`
- `test_environment_only`
- `infrastructure`
- `unclear`
- `other`

- `false_positive` — the reviewer flagged something that is not actually a problem
- `acceptable_risk` — the issue is real but acceptable in this context
- `unclear` — the reviewer's concern is ambiguous, needs investigation later
- `infrastructure` — overriding an infra failure, not a review finding

Override reasons are logged to history and can be aggregated:

```bash
python ~/.claude/scripts/cold_eyes/cli.py aggregate-overrides
```

### Strategy presets

Common configuration combinations for different risk tolerance levels:

| Preset | MODE | THRESHOLD | CONFIDENCE | Description |
|---|---|---|---|---|
| Conservative | block | critical | high | Only block high-confidence critical issues. Lowest friction. |
| Standard | block | critical | medium | **Default.** Block medium+ confidence critical issues. |
| Strict | block | major | medium | Also block major issues. |
| Aggressive | block | major | low | Block any issue at major or above. |
| Observe | report | — | low | Log everything, never block. Best for first-time adoption. |

Example — switch to Strict:

```bash
export COLD_REVIEW_BLOCK_THRESHOLD=major
export COLD_REVIEW_CONFIDENCE=medium
```

Example — Observe mode for a trial run:

```bash
export COLD_REVIEW_MODE=report
export COLD_REVIEW_CONFIDENCE=low
```

### Truncation policy

Controls what happens when a diff exceeds the token budget and files are skipped:

| Policy | Behavior |
|--------|----------|
| `warn` (default) | Adds a warning to the block message, does not change the block/pass decision |
| `soft-pass` | If truncated and no issues found in the reviewed portion, force pass |
| `fail-closed` | If any files were unreviewed, block regardless of findings |

```bash
export COLD_REVIEW_TRUNCATION_POLICY=fail-closed
```

Or in `.cold-review-policy.yml`:

```yaml
truncation_policy: fail-closed
```

Review outcomes include coverage visibility: `reviewed_files`, `total_files`, and `coverage_pct` fields show what proportion of the diff was actually reviewed.

### Coverage gate

Coverage is measured after filtering and risk ranking. Fully reviewed files count as covered. Partial files, files skipped by token budget, binary files, and unreadable files count as unreviewed.

`minimum_coverage_pct` sets the minimum reviewed-file percentage. `coverage_policy: warn` records the shortfall but does not block. `coverage_policy: block` blocks in `mode: block` when coverage is below the minimum. `coverage_policy: fail-closed` also blocks when any file is unreviewed. If `fail_on_unreviewed_high_risk: true`, high-risk unreviewed paths such as auth, payment, db, migration, secret, credential, config, or api files block independently of the percentage.

Coverage blocks are not model findings. They are logged separately under `coverage` and use `final_action: coverage_block`.

### Ignore rules

**Built-in low-signal patterns** (used by legacy filtering and review triage):

```
dist/*  build/*  .next/*  coverage/*  vendor/*
node_modules/*  *.min.js  *.min.css  *.map
```

v2 does not silently drop lockfiles, package manifests, workflow files, hook scripts, or Cold Eyes engine files from the envelope. They are treated as config/high-risk unless you intentionally exclude them in `.cold-review-ignore`.

**Per-repo patterns:** Create `.cold-review-ignore` in your project root to add project-specific exclusions. Uses fnmatch glob patterns, one per line. Lines starting with `#` are comments. This file lives in the repo, not in `~/.claude/scripts/`.

```
# Test fixtures
tests/fixtures/*

# Generated code
src/generated/*
```

Per-repo patterns are additive on top of the built-in list. `doctor` check 7 reports whether this file exists (info level, not required).

### Review prompt

Edit `~/.claude/scripts/cold-review-prompt.txt` to change what the reviewer checks for and how it responds.

## Failure modes

Cold Eyes logs its state to `~/.claude/cold-review-history.jsonl` at every exit path:

| State | Meaning |
|---|---|
| `skipped` | No review ran. Check `gate_state` for `skipped_no_change`, `skipped_safe`, `protected_cached`, or `off_explicit`. |
| `infra_failed` | Infrastructure failure on a path where review was not required. Review-required failures block as `gate_state: blocked_infra`. |
| `passed` | Review completed, no issues at or above threshold (after confidence filter) |
| `reported` | Review completed with issues remaining after confidence filter, mode is `report` (no block) |
| `blocked` | A block was emitted: model finding, incomplete coverage, local hard check, unreviewed delta, stale review, lock contention, or review-required infra failure |
| `overridden` | Would have blocked, but an override token was armed (or legacy `ALLOW_ONCE` was set). Override reason recorded in history. |

If reviews aren't running, check:
1. `~/.claude/cold-review-history.jsonl` — look for recent `infra_failed` or `skipped` entries. `failure_kind` and `stderr_excerpt` fields pinpoint the cause.
2. `python ~/.claude/scripts/cold_eyes/cli.py doctor` — checks environment health (failure messages include `Fix:` instructions)
3. `claude -d` — check for auth or rate limit issues

For detailed state analysis, see `docs/failure-modes.md`. For common issues, see `docs/troubleshooting.md`.

## Requirements

- Claude Code CLI with an active subscription
- Python 3.10+
- Git
- Bash (Git Bash on Windows)

See `docs/support-policy.md` for the full tested platform matrix.

## Files

| File | Purpose |
|---|---|
| `cold_eyes/` | Python package for the unified v2 pipeline: engine, review envelope, triage, target sentinel, context, detector, memory, policy, git, filter, review, schema, history, config, constants, prompt, doctor, CLI, model adapter, override token, auto-tune, intent capsule, protection brief, and local checks. |
| `cold-review.sh` | Stop hook entry point: guard checks (recursion/git), lock preflight, fail-closed result parser |
| `cold-review-prompt.txt` | Deep review system prompt: input type descriptions, check items, evidence principles, severity/confidence/category definitions, output schema |
| `cold-review-prompt-shallow.txt` | Shallow review system prompt: critical-only checks, minimal schema |
| `evals/` | Evaluation framework: 33 case fixtures (7 categories) + eval runner (deterministic/benchmark/sweep) + structured pipeline |
| `docs/` | Architecture, failure modes, troubleshooting, evaluation, scope strategy, history schema, tuning, support policy, roadmap, version policy, agent setup, release checklist, sample outputs |
| `pyproject.toml` | Package metadata and ruff/lint config (optional `pip install -e .` for `cold-eyes` CLI command) |
| `install.sh` / `uninstall.sh` | Deploy to / remove from `~/.claude/scripts/` |
| `.cold-review-ignore` | Per-repo ignore patterns (optional, placed in project root) |
| `.cold-review-policy.yml` | Per-repo configuration defaults (optional, placed in project root) |

## Building on top of Cold Eyes

Cold Eyes is a hook and a set of JSON files. Everything is designed to be readable and writable by other tools.

- **`cold-review-history.jsonl`** — One JSON object per line (includes `state`, `gate_state`, `duration_ms`, `diff_stats`, `min_confidence`, `scope`, review `schema_version`, optional `envelope`, optional `cache`, `override_reason`, `failure_kind`, `stderr_excerpt`, optional `target`, optional `checks`, and optional `protection` summary). Build a dashboard, filter by state, chart trends over time. Use `stats`, `quality-report`, and `auto-tune` commands to query it.
- **`cold-review-prompt.txt`** — Template with `{language}` placeholder. Swap in your own review criteria.
- **`.cold-review-ignore`** — fnmatch patterns. Add project-specific exclusions.
- **`.cold-review-policy.yml`** — Flat key-value config. Set per-repo defaults for mode, model, threshold, etc.

## Diagnostics

```bash
python ~/.claude/scripts/cold_eyes/cli.py doctor
```

Outputs a JSON report:

| Check | What it verifies |
|---|---|
| `python` | Python version |
| `git` | Git CLI available |
| `claude_cli` | Claude Code CLI available |
| `deploy_files` | All package files exist in `~/.claude/scripts/` |
| `settings_hook` | `settings.json` has a Stop hook referencing `cold-review.sh` |
| `git_repo` | Current directory is a git repository |
| `ignore_file` | `.cold-review-ignore` exists in repo root (info only) |
| `policy_file` | `.cold-review-policy.yml` exists and lists loaded keys (info only) |
| `legacy_helper` | No `cold-review-helper.py` in scripts dir (split-brain detection) |
| `shell_version` | `cold-review.sh` has no legacy patterns (`claude -p`, helper refs, `MAX_LINES`) |
| `legacy_env` | `COLD_REVIEW_MAX_LINES` not set (info only) |

If reviews aren't running, `doctor` is the first thing to check.

### Quick install check

```bash
python ~/.claude/scripts/cold_eyes/cli.py verify-install
```

Returns `{"action": "verify-install", "ok": true, "failures": []}` if the 2 critical checks (deploy files, hook config) pass. Git repo availability is reported as an environment warning, not a critical failure.

### Evaluation

```bash
# Deterministic eval — 33 cases, no model calls
python cold_eyes/cli.py eval --eval-mode deterministic

# Threshold sweep — precision/recall/F1 for all threshold x confidence combos
python cold_eyes/cli.py eval --eval-mode sweep

# Benchmark with real model
python cold_eyes/cli.py eval --eval-mode benchmark --model opus

# Save report to evals/results/
python cold_eyes/cli.py eval --save --format both

# Compare against a previous report
python cold_eyes/cli.py eval --save --compare evals/results/deterministic_prev.json
```

The eval framework tests the decision boundary (`parse_review_output` + `apply_policy`) against 33 cases across 7 categories: 10 true positives, 4 acceptable changes, 4 false negatives, 5 stress cases, 4 edge cases, 3 evidence-bound cases, and 3 FP memory cases. Reports include version metadata and can be saved as JSON/markdown and compared across runs. See `docs/evaluation.md` and `docs/trust-model.md` for details.

### Override aggregation

```bash
python ~/.claude/scripts/cold_eyes/cli.py aggregate-overrides
```

Returns a JSON summary of all override entries in history: total count, reasons grouped by frequency, and recent override entries. Use this to identify false-positive patterns and tune thresholds or prompts.

### Status

```bash
python ~/.claude/scripts/cold_eyes/cli.py status
python ~/.claude/scripts/cold_eyes/cli.py status --human
```

Returns a low-detail health signal for the current repo. It answers whether Cold Eyes has run normally without exposing the review findings. A normal block is still reported as healthy runtime behavior; infrastructure failures or missing history show as attention-needed states. Add `--human` for a short `READY` / `ATTENTION` / `NOT_PROTECTING` / `UNKNOWN` summary with review target and not-reviewed counts. Add `--stale-after-hours N` only if you also want to treat old history as unknown.

### Agent health notices

```bash
python ~/.claude/scripts/cold_eyes/cli.py agent-notice --write --only-problem
python ~/.claude/scripts/cold_eyes/cli.py install-health-schedule --every-days 7 --time 09:00
python ~/.claude/scripts/cold_eyes/cli.py remove-health-schedule
```

`agent-notice` is the scheduled, Agent-facing form of `status`: normal runs clear old notices, while setup/tool problems write `~/.claude/cold-review-agent-notice.txt`. The Stop hook surfaces that notice to the Agent on the next run. It does not include review findings or blocked-file details.

Notice levels stay low-detail:

- `attention` — Cold Eyes needs Agent attention.
- `gate_unreliable` — do not rely on the gate until setup is fixed.
- `schedule_missing` — the background health notice schedule is missing.

### Stats

```bash
python ~/.claude/scripts/cold_eyes/cli.py stats
python ~/.claude/scripts/cold_eyes/cli.py stats --last 7d
python ~/.claude/scripts/cold_eyes/cli.py stats --last 7d --by-reason --by-path
```

Returns a JSON summary of review activity from history:

- **Total and per-state counts** — passed, blocked, overridden, skipped, infra_failed, reported
- **`--last`** — filter by time window: `7d` (days), `24h` (hours), `2w` (weeks)
- **`--by-reason`** — override reasons grouped by frequency
- **`--by-path`** — per-repo breakdown with total, blocked, and overridden counts (sorted by blocked descending)

### Quality report

```bash
python ~/.claude/scripts/cold_eyes/cli.py quality-report
python ~/.claude/scripts/cold_eyes/cli.py quality-report --last 7d
```

Extended analysis: block rate, override rate, infra failure rate, top noisy paths, top issue categories, and `gate_quality` metrics including normal pass count, override rate, false-positive overrides, accepted-risk overrides, coverage block count/rate, and infra failure rate. `override_pass` is not counted as a normal pass.

### Auto-tune

```bash
# Inspect the current automatic decision
python ~/.claude/scripts/cold_eyes/cli.py auto-tune --last 7d

# Optional manual repo-local write
python ~/.claude/scripts/cold_eyes/cli.py auto-tune --last 7d --write-auto-policy
```

Quality-first machine-readable tuning. Normal `run` automatically checks it at low frequency, so the Stop hook can tune itself without you remembering a command. Automatic runs write a repo-specific policy under `~/.claude/cold-review-auto-policies/`, keeping the working tree clean. Manual `--write-auto-policy` writes `.cold-review-policy.auto.yml` in the repo when you want an explicit local artifact. Manual `.cold-review-policy.yml` values override all auto files.

Auto-tune never relaxes the critical threshold, never disables high-risk coverage protection, and only reduces `context_tokens` when recent history is clean but expensive. Disable automatic tuning with `COLD_REVIEW_AUTO_TUNE=off`.

### History management

```bash
# Keep only last 90 days
python ~/.claude/scripts/cold_eyes/cli.py history-prune --keep-days 90

# Keep only last 500 entries
python ~/.claude/scripts/cold_eyes/cli.py history-prune --keep-entries 500

# Archive entries before a date
python ~/.claude/scripts/cold_eyes/cli.py history-archive --before 2026-01-01
```

## Known limitations

- **Review history is append-only.** Use `history-prune` and `history-archive` to manage growth (see Diagnostics).
- **Large diffs get truncated.** Diffs over the token budget (default 12000) are cut. High-risk files are prioritized. Truncation metadata tracks partial files, budget-skipped files, binary files, and unreadable files separately. Block messages include a warning listing what was not reviewed.
- **Infra failures are diagnosable but not self-healing.** History records `failure_kind` (`timeout`, `cli_not_found`, `cli_error`, `empty_output`) and a `stderr_excerpt`. In v2, review-required infra failures block as `blocked_infra`; no-change/safe paths do not manufacture blocks.
- **Health notices still need a trigger.** The installer creates a weekly Windows scheduled task by default. If that schedule is disabled and the Stop hook is removed, Cold Eyes has no always-on process that can notify the Agent by itself.
- **`line_hint` is approximate.** Line references are extracted by the LLM from diff hunk headers, displayed with `~` prefix. The prompt instructs it to leave `line_hint` empty when uncertain, but hallucinated line numbers are possible. In block mode, always verify the line number before making fixes.
- **Windows (Git Bash) lock caveats.** The atomic `mkdir` lock and `kill -0` stale PID check work in Git Bash but are less reliable than on native Unix. When a real lock is active, v2 performs a lightweight envelope decision: no-change/cache paths can pass, while changed source/config can block as `blocked_lock_active`.
- **Local checks are bounded.** Selected checks run once and respect `COLD_REVIEW_CHECK_TIMEOUT_SEC`. Timeouts and missing tools are warnings, not blockers.

## Uninstall

```bash
bash uninstall.sh
```

Then remove the Stop hook entry from `~/.claude/settings.json`.

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md) for development setup, coding standards, and contribution workflow.

## Security

See [SECURITY.md](SECURITY.md) for vulnerability disclosure policy and trust boundaries.

## License

MIT
