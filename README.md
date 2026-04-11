# Cold Eyes Reviewer

A zero-context code reviewer for [Claude Code](https://docs.anthropic.com/en/docs/claude-code). Runs automatically after every session turn via Stop hook.

Cold Eyes is a second-pass gate, not a full code review. It sees only the git diff — no conversation context, no project history, no requirements. It catches surface-level correctness, security, and consistency issues. It does not understand your intent.

## How it works

```
Claude Code session ends
       │
       ▼
  cold-review.sh (guard checks only)
       │
       ├─ off mode / recursion / no git repo → exit
       ├─ lockfile held by another review → exit
       │
       ▼
  cold_review_engine.py (all review logic)
       │
       ├─ collect files → filter → risk-rank → build diff (token-budgeted)
       ├─ call Claude CLI with system prompt
       ├─ parse review → confidence hard-filter → policy decision
       │
       ├─ block mode: issues at or above threshold → block → Claude fixes
       ├─ report mode: log review → pass
       └─ all states logged to ~/.claude/cold-review-history.jsonl
```

## Output format

Every issue includes severity, confidence, category, file, line_hint, and a three-part structure (check / verdict / fix):

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
      "fix": "Change to ch3.html"
    }
  ]
}
```

- `schema_version` — output schema version (currently `1`). Bumped on breaking changes to the review JSON structure (field removal, semantic change, required field addition). Adding optional fields (e.g., `override_reason`) does not bump the version.
- `line_hint` — approximate line reference from diff hunk headers (e.g., `"L42"`, `"L42-L50"`). Empty string when uncertain. Displayed with `~` prefix (e.g., `(~L42)`) to indicate it is an estimate, not a precise location. In block mode, verify the line number before acting on it.

**Severity levels:**
- `critical` — production crash, data loss, or security breach
- `major` — incorrect behavior under normal use
- `minor` — suboptimal but functional

## Install

### 1. Copy scripts

```bash
mkdir -p ~/.claude/scripts
cp cold-review.sh cold-review-helper.py cold_review_engine.py cold-review-prompt.txt ~/.claude/scripts/
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

### 3. Verify installation

```bash
python ~/.claude/scripts/cold_review_engine.py doctor
```

Checks Python, Git, Claude CLI, deploy files, hook config, and current repo. All checks should show `"ok"`. `"info"` items are optional hints.

### 4. Done

Next time Claude Code finishes a turn with uncommitted changes, Cold Eyes will review them.

### Recommended adoption path

1. Start with `COLD_REVIEW_MODE=report` — review results are logged but nothing is blocked. Read the history to see what it catches.
2. After a week, switch to `COLD_REVIEW_MODE=block` with `COLD_REVIEW_BLOCK_THRESHOLD=critical` (the default). Only critical issues block.
3. If the signal-to-noise ratio is good, optionally lower the threshold to `major`.

## Token usage

Every review consumes tokens from your Claude subscription. You see what it costs, you control when it runs, you decide the model.

## What gets reviewed

By default (`COLD_REVIEW_SCOPE=working`), Cold Eyes reviews **all uncommitted changes** in the working tree — staged, unstaged, and untracked. It has no way to distinguish "changes Claude made" from "changes you had before opening the session."

**Commit or push before starting a new session.** This keeps the diff clean and the review accurate.

Other scopes:
- `COLD_REVIEW_SCOPE=staged` — only review `git diff --cached` (staged changes)
- `COLD_REVIEW_SCOPE=head` — review `git diff HEAD` (staged + unstaged, no untracked)

## Configuration

### Environment variables

| Variable | Default | Options | Description |
|---|---|---|---|
| `COLD_REVIEW_MODE` | `block` | `block`, `report`, `off` | Block and force fix / log only / disable |
| `COLD_REVIEW_MODEL` | `opus` | `opus`, `sonnet`, `haiku` | Which model runs the review |
| `COLD_REVIEW_MAX_TOKENS` | `12000` | any integer | Token budget for diff (len÷4 estimation) |
| `COLD_REVIEW_BLOCK_THRESHOLD` | `critical` | `critical`, `major` | Minimum severity that triggers a block |
| `COLD_REVIEW_CONFIDENCE` | `medium` | `high`, `medium`, `low` | Minimum confidence to keep (hard filter) |
| `COLD_REVIEW_LANGUAGE` | `繁體中文（台灣）` | any string | Output language |
| `COLD_REVIEW_SCOPE` | `working` | `working`, `staged`, `head` | Diff scope: all uncommitted / staged only / vs HEAD |
| `COLD_REVIEW_ALLOW_ONCE` | (unset) | `1` | Set to skip block once (logged as override) |
| `COLD_REVIEW_OVERRIDE_REASON` | (unset) | any text | Reason for override when using ALLOW_ONCE |

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

# One-time override when blocked by a false positive
export COLD_REVIEW_ALLOW_ONCE=1
export COLD_REVIEW_OVERRIDE_REASON="false_positive"
```

### Override reasons

When overriding a block, set `COLD_REVIEW_OVERRIDE_REASON` to explain why. Any free text works. Common values:

- `false_positive` — the reviewer flagged something that is not actually a problem
- `acceptable_risk` — the issue is real but acceptable in this context
- `unclear` — the reviewer's concern is ambiguous, needs investigation later
- `infrastructure` — overriding an infra failure, not a review finding

Override reasons are logged to history and can be aggregated:

```bash
python ~/.claude/scripts/cold_review_engine.py aggregate-overrides
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

### Ignore rules

**Built-in patterns** (always active, no configuration needed):

```
*.lock  package-lock.json  pnpm-lock.yaml  yarn.lock
dist/*  build/*  .next/*  coverage/*  vendor/*
node_modules/*  *.min.js  *.min.css
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
| `failed` | Claude CLI error, empty output, or parse failure |
| `passed` | Review completed, no issues at or above threshold |
| `reported` | Review completed with issues, but mode is `report` (no block) |
| `blocked` | Review completed, issues found at or above threshold, block emitted |
| `overridden` | Would have blocked, but `COLD_REVIEW_ALLOW_ONCE=1` was set. Override reason (if provided via `COLD_REVIEW_OVERRIDE_REASON`) is recorded in history. |

If reviews aren't running, check:
1. `~/.claude/cold-review-history.jsonl` — look for recent `failed` or `skipped` entries
2. `claude -d` — check for auth or rate limit issues

## Requirements

- Claude Code CLI with an active subscription
- Python 3.x
- Git
- Bash (Git Bash on Windows)

## Files

| File | Purpose |
|---|---|
| `cold_review_engine.py` | Core: diff building, Claude call, policy engine, confidence filter, history logging, doctor |
| `cold-review.sh` | Stop hook entry point: guard checks (off/recursion/lock/git), then calls engine |
| `cold-review-helper.py` | Shell-facing utilities: hook parsing, state logging, ignore/rank (called by shell; prompt delegates to engine) |
| `cold-review-prompt.txt` | System prompt template (schema_version, line_hint, categories, severity/confidence definitions) |
| `.cold-review-ignore` | Default ignore patterns |

## Background

This tool was built after observing [Cinder](https://github.com/shihchengwei-lab/Not-a-Mascot), a Claude Code buddy companion that provided independent commentary during coding sessions. Cinder was silently shut down on April 11, 2026. Cold Eyes carries forward the idea that a second pair of eyes — even artificial ones — catches things the first pair misses.

The difference: Cinder watched in real time and commented. Cold Eyes reviews after the fact and blocks if needed. Cinder was a companion. Cold Eyes is a gate.

## Building on top of Cold Eyes

Cold Eyes is a hook and a set of JSON files. Everything is designed to be readable and writable by other tools.

- **`cold-review-history.jsonl`** — One JSON object per line (v2 format includes `state`, `diff_stats`, `min_confidence`, `scope`, `schema_version`, `override_reason`). Build a dashboard, filter by state, chart trends over time. Override entries include `override_reason` when provided.
- **`cold-review-prompt.txt`** — Template with `{language}` placeholder. Swap in your own review criteria.
- **`.cold-review-ignore`** — fnmatch patterns. Add project-specific exclusions.

## Diagnostics

```bash
python ~/.claude/scripts/cold_review_engine.py doctor
```

Outputs a JSON report checking 7 items:

| Check | What it verifies |
|---|---|
| `python` | Python version |
| `git` | Git CLI available |
| `claude_cli` | Claude Code CLI available |
| `deploy_files` | All 4 script files exist in `~/.claude/scripts/` |
| `settings_hook` | `settings.json` has a Stop hook referencing `cold-review.sh` |
| `git_repo` | Current directory is a git repository |
| `ignore_file` | `.cold-review-ignore` exists in repo root (info only, not required) |

If reviews aren't running, `doctor` is the first thing to check.

### Override aggregation

```bash
python ~/.claude/scripts/cold_review_engine.py aggregate-overrides
```

Returns a JSON summary of all override entries in history: total count, reasons grouped by frequency, and recent override entries. Use this to identify false-positive patterns and tune thresholds or prompts.

## Known limitations

- **Review history grows forever.** `~/.claude/cold-review-history.jsonl` is append-only. Periodically archive or truncate it yourself.
- **Large diffs get truncated.** Diffs over the token budget (default 12000) are cut. High-risk files are prioritized. When truncation causes files to be skipped, block messages include a warning with the count of unreviewed files.
- **Silent on auth failure.** If your Claude subscription is expired or rate-limited, the review logs a `failed` state. Check stderr or history.
- **`line_hint` is approximate.** Line references are extracted by the LLM from diff hunk headers, displayed with `~` prefix. The prompt instructs it to leave `line_hint` empty when uncertain, but hallucinated line numbers are possible. In block mode, always verify the line number before making fixes.

## License

MIT
