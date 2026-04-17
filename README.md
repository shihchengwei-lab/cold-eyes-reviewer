# Cold Eyes Reviewer

![Tests](https://github.com/shihchengwei-lab/cold-eyes-reviewer/actions/workflows/test.yml/badge.svg)
![Claude Code](https://img.shields.io/badge/Claude%20Code-Stop--hook-blue)
![Review](https://img.shields.io/badge/Review-diff--centered-green)
![Scope](https://img.shields.io/badge/Scope-not%20full%20review-lightgrey)

A diff-centered, second-pass review gate for [Claude Code](https://docs.anthropic.com/en/docs/claude-code). Runs automatically after every session turn via Stop hook.

This tool was built after observing [Cinder](https://not-a-mascot.vercel.app/index-en.html), a Claude Code buddy companion that provided independent commentary during coding sessions. Cinder was silently shut down on April 11, 2026. Cold Eyes carries forward the idea that a second pair of eyes — even artificial ones — catches things the first pair misses. Cinder was a companion. Cold Eyes is a gate.

## What it is

Cold Eyes runs as a Stop hook after each Claude Code turn and reviews the working-tree diff. It is diff-first: the git diff is the primary input. On the deep path it also pulls in **limited, structured supporting context** — recent commit messages and co-changed files from git history, plus regex-based detector hints — to reduce obvious blind spots. Shallow paths run on the diff alone with a lighter model. The v2 pipeline (opt-in via `--v2`) layers a multi-gate verification loop with retry, suppression, and optional non-LLM checks (tests, lint, type, build) around the same LLM review step.

## What it is not

- **Not a replacement for human review.** It is a pre-hint before the real reviewer looks.
- **Not a full PR review platform.** No cross-file search, no repo-wide symbol analysis, no issue tracking.
- **Not a full-context code understanding system.** What the deep path sees is bounded to a handful of git-adjacent signals, not the whole codebase.
- **Not requirement-aware / intent-aware in the strong sense.** It has no specification and does not know what the change is supposed to do.
- **Not a sufficient gate for semantic design correctness.** Multi-file logic, business rules, architectural decisions are out of scope.

## When it works best

- Claude Code workflows where an automatic second pass catches surface-level slips before they compound.
- Catching high-cost surface issues: removed error handling, hardcoded secrets, dangling references within the diff, obvious injection shapes.
- Teams willing to run in `report` mode first and calibrate thresholds before enabling blocking.

## When not to use it as a blocking gate

- Tasks where the bug is driven by requirements or specs that are not visible in the diff.
- Large, non-local semantic refactors where most of the signal lives outside the changed lines.
- Teams with very low false-positive tolerance that have not yet measured Cold Eyes' noise rate on their own code.
- New adopters who have not walked through the adoption path — start in `report`, then narrow.

## Review paths overview

- **Shallow** — test-only or low-risk diffs. Lighter model, critical-only prompt, diff as sole input. Fast and cheap.
- **Deep** (default for source changes) — full model, diff + bounded supporting context + detector hints. This is what the project name refers to: a diff-centered review with a small amount of structured support.
- **v2** (opt-in, `--v2`) — deeper verification path: the same LLM review step is wrapped in a multi-gate loop that can also run test / lint / type / build gates, with retry and noise suppression between iterations. Cost can rise up to ~4x a v1 run in the worst case (see Token usage). v2 is not the product headline; it is an opt-in deeper mode.

### Why deeper paths exist

The diff alone is sometimes not enough to distinguish a real bug from a valid change (a renamed function, a removed resource that was handled elsewhere). The deep path's context block and detector hints exist to reduce that class of false calls without turning the tool into a full-context reviewer. v2 exists to layer mechanical checks (tests, lint) around the LLM review when the user wants stricter gating.

## How it works

```
Claude Code session ends
       │
       ▼
  cold-review.sh (shim — guards + fail-closed result parser)
       │
       ├─ off mode / recursion / no git repo → exit
       ├─ atomic lock held by another review → exit
       │
       ▼
  cold_eyes/cli.py → engine.py (v1 default)
                   → session_runner.py (v2, opt-in via --v2)
       │
       ├─ 1. collect files → 2. filter (.cold-review-ignore) → 3. risk-rank
       ├─ 4. triage: skip (docs/generated) / shallow (test-only) / deep (source/risk)
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
       ├─ block mode: issues at or above threshold → block (Claude Code decides what to do next)
       ├─ report mode: log review → pass
       └─ all engine-level exits logged to ~/.claude/cold-review-history.jsonl
          (shell guard skips — off, recursion, no git repo, lock — are not logged)
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

- `schema_version` — output schema version (currently `1`). Bumped on breaking changes to the review JSON structure (field removal, semantic change, required field addition). Adding optional fields (e.g., `override_reason`) does not bump the version.
- `line_hint` — approximate line reference from diff hunk headers (e.g., `"L42"`, `"L42-L50"`). Empty string when uncertain. Displayed with `~` prefix (e.g., `(~L42)`) to indicate it is an estimate, not a precise location. In block mode, verify the line number before acting on it.

**Severity levels:**
- `critical` — production crash, data loss, or security breach
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

Creates default `.cold-review-policy.yml` and `.cold-review-ignore` in the current repo if they don't exist.

### 4. Verify installation

```bash
python ~/.claude/scripts/cold_eyes/cli.py doctor
```

Checks Python, Git, Claude CLI, deploy files, hook config, and current repo. All checks should show `"ok"`. `"info"` items are optional hints.

Use `doctor --fix` to auto-remove legacy helper if detected. Other failures require manual action.

### 5. Done

Next time Claude Code finishes a turn with uncommitted changes, Cold Eyes will review them.

### Recommended adoption path

1. Start with `COLD_REVIEW_MODE=report` — review results are logged but nothing is blocked. Read the history to see what it catches.
2. After a week, switch to `COLD_REVIEW_MODE=block` with `COLD_REVIEW_BLOCK_THRESHOLD=critical` (the default). Only critical issues block.
3. If the signal-to-noise ratio is good, optionally lower the threshold to `major`.

## Token usage

Every review consumes tokens from your Claude usage quota. How much depends on:

- **Review depth** — skip uses zero tokens (no model call), shallow uses fewer than deep
- **Model choice** — opus costs more per token than sonnet; sonnet more than haiku
- **Diff size** — larger diffs send more input tokens (budget default: 12000)
- **Context and hints** — deep reviews add up to ~2200 tokens (context + detector hints) on top of the diff

**v2 pipeline (`--v2`):** v2 adds multi-gate verification and a retry loop on top of the v1 review. Non-LLM gates (test runner, lint, type check) use no tokens. The LLM review gate is the same `engine.run()` call as v1. If all gates pass on the first try, token cost equals v1. If the retry loop triggers, each iteration makes one additional LLM call. With the default `max_retries=3`, the worst case is **4x the v1 cost** (1 initial + 3 retries). In practice, most reviews pass on the first iteration.

Subscription users (Pro/Max): reviews count against your plan's usage quota, not billed separately. API users: cost follows Anthropic's published per-token pricing, which changes over time.

To reduce token usage: use `COLD_REVIEW_MODEL=sonnet` or `haiku`, lower `COLD_REVIEW_MAX_TOKENS`, or set `COLD_REVIEW_CONTEXT_TOKENS=0` to disable context retrieval.

## What gets reviewed

By default (`COLD_REVIEW_SCOPE=working`), Cold Eyes reviews **all uncommitted changes** in the working tree — staged, unstaged, and untracked. It has no way to distinguish "changes Claude made" from "changes you had before opening the session."

**Commit or push before starting a new session.** This keeps the diff clean and the review accurate.

Other scopes:
- `COLD_REVIEW_SCOPE=staged` — only review `git diff --cached` (staged changes)
- `COLD_REVIEW_SCOPE=head` — review `git diff HEAD` (staged + unstaged, no untracked)
- `COLD_REVIEW_SCOPE=pr-diff` — review `git diff <base>...HEAD` (PR changes vs base branch, requires `COLD_REVIEW_BASE`)

## Configuration

### Policy file (per-repo)

Place `.cold-review-policy.yml` in your project root to set repo-level defaults. This replaces the need for global environment variables in repos that need specific settings.

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
```

All keys are optional. Only include what you want to override.

**Resolution priority:** CLI arg > environment variable > policy file > hardcoded default.

If `COLD_REVIEW_MODE=block` is set as an env var, it overrides the policy file's `mode: report`. If neither env var nor policy file sets a value, the hardcoded default applies.

Supported keys: `mode`, `model`, `max_tokens`, `block_threshold` (or `threshold`), `confidence`, `language`, `scope`, `base`, `truncation_policy`.

`doctor` check 8 reports whether this file exists and what keys it sets.

### Environment variables

| Variable | Default | Options | Description |
|---|---|---|---|
| `COLD_REVIEW_MODE` | `block` | `block`, `report`, `off` | Block and force fix / log only / disable |
| `COLD_REVIEW_MODEL` | `opus` | `opus`, `sonnet`, `haiku` | Which model runs the deep review |
| `COLD_REVIEW_SHALLOW_MODEL` | `sonnet` | `opus`, `sonnet`, `haiku` | Which model runs the shallow review |
| `COLD_REVIEW_MAX_TOKENS` | `12000` | any integer | Token budget for diff |
| `COLD_REVIEW_CONTEXT_TOKENS` | `2000` | any integer (0 = off) | Token budget for context section (deep review only) |
| `COLD_REVIEW_BLOCK_THRESHOLD` | `critical` | `critical`, `major` | Minimum severity that triggers a block |
| `COLD_REVIEW_CONFIDENCE` | `medium` | `high`, `medium`, `low` | Minimum confidence to keep (hard filter) |
| `COLD_REVIEW_LANGUAGE` | `繁體中文（台灣）` | any string | Output language |
| `COLD_REVIEW_SCOPE` | `working` | `working`, `staged`, `head`, `pr-diff` | Diff scope: all uncommitted / staged only / vs HEAD / vs base branch |
| `COLD_REVIEW_BASE` | (unset) | any branch name | Base branch for `pr-diff` scope (e.g. `main`) |
| `COLD_REVIEW_TRUNCATION_POLICY` | `warn` | `warn`, `soft-pass`, `fail-closed` | How to handle truncated diffs (see Truncation policy) |
| `COLD_REVIEW_ALLOW_ONCE` | (unset) | `1` | **Deprecated.** Use `arm-override` instead. Still works but emits a warning. |
| `COLD_REVIEW_OVERRIDE_REASON` | (unset) | any text | Reason for override (used with ALLOW_ONCE or arm-override) |

```bash
# Use sonnet to save tokens
export COLD_REVIEW_MODEL=sonnet

# Just log, don't block
export COLD_REVIEW_MODE=report

# Block on major issues too
export COLD_REVIEW_BLOCK_THRESHOLD=major

# Only keep high-confidence issues
export COLD_REVIEW_CONFIDENCE=high

# Review in English
export COLD_REVIEW_LANGUAGE=English

# Only review staged changes
export COLD_REVIEW_SCOPE=staged

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

**Legacy:** `COLD_REVIEW_ALLOW_ONCE=1` still works but is deprecated — it cannot truly be consumed (env vars persist in the parent shell), so it bypasses *every* block while set. A deprecation warning is emitted.

### Override reasons

Common reason values:

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

### Ignore rules

**Built-in patterns** (always active, no configuration needed):

```
*.lock  package-lock.json  pnpm-lock.yaml  yarn.lock
dist/*  build/*  .next/*  coverage/*  vendor/*
node_modules/*  *.min.js  *.min.css  *.map
```

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
| `skipped` | No changes, not a git repo, all files ignored, or another review in progress |
| `infra_failed` | Infrastructure failure: Claude CLI error, timeout, empty output, parse failure, git error, or config error. History includes `failure_kind` and `stderr_excerpt` for diagnosis. In block mode, this blocks. In report mode, it passes but logs the failure. |
| `passed` | Review completed, no issues at or above threshold (after confidence filter) |
| `reported` | Review completed with issues remaining after confidence filter, mode is `report` (no block) |
| `blocked` | Review completed, issues found at or above threshold, block emitted |
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
| `cold_eyes/` | Python package (19 top-level modules + 6 v2 sub-packages: session, contract, gates, retry, noise, runner). v1 core: engine, triage, context, detector, memory, policy, git, filter, review, schema, history, config, constants, prompt, doctor, CLI, model adapter, override token. v2 adds session engine, contract generation, multi-gate orchestration, retry loop, noise suppression. |
| `cold-review.sh` | Stop hook entry point: guard checks (off/recursion/lock/git), fail-closed result parser |
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

- **`cold-review-history.jsonl`** — One JSON object per line (includes `state`, `diff_stats`, `min_confidence`, `scope`, `schema_version`, `override_reason`, `failure_kind`, `stderr_excerpt`). Build a dashboard, filter by state, chart trends over time. Use `stats` and `aggregate-overrides` commands to query it.
- **`cold-review-sessions/sessions.jsonl`** — v2 session records (`--v2` only). Each line is a full session: contracts, gate plan, gate results, retry briefs, events timeline, final outcome. Path: `~/.claude/cold-review-sessions/sessions.jsonl`.
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

Extended analysis: block rate, override rate, infra failure rate, top noisy paths, and top issue categories.

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
- **Infra failures are diagnosable but not self-healing.** History records `failure_kind` (`timeout`, `cli_not_found`, `cli_error`, `empty_output`) and a `stderr_excerpt`. Check history for patterns.
- **`line_hint` is approximate.** Line references are extracted by the LLM from diff hunk headers, displayed with `~` prefix. The prompt instructs it to leave `line_hint` empty when uncertain, but hallucinated line numbers are possible. In block mode, always verify the line number before making fixes.
- **Windows (Git Bash) lock caveats.** The atomic `mkdir` lock and `kill -0` stale PID check work in Git Bash but are less reliable than on native Unix. Concurrent Claude Code sessions on Windows may occasionally bypass the lock.
- **v2 session store has no prune mechanism.** `~/.claude/cold-review-sessions/sessions.jsonl` grows indefinitely. v1 history has `history-prune` and `history-archive`; v2 sessions do not yet.

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
