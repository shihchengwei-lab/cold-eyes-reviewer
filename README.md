# Cold Eyes Reviewer

A zero-context code reviewer for [Claude Code](https://docs.anthropic.com/en/docs/claude-code). Runs automatically after every session turn via Stop hook.

Cold Eyes is a second-pass gate, not a full code review. It sees only the git diff — no conversation context, no project history, no requirements. It catches surface-level correctness, security, and consistency issues. It does not understand your intent.

## How it works

```
Claude Code session ends
       │
       ▼
  Stop hook fires
       │
       ├─ No git changes? → skip
       ├─ All files ignored? → skip
       ├─ Already reviewing? → skip (prevents recursion)
       │
       ▼
  Collect diff (filtered, risk-sorted, within token budget)
       │
       ▼
  Cold Eyes reviews the diff
       │
       ├─ block mode: issues at or above threshold → block → Claude fixes → done
       ├─ report mode: log review → done
       └─ all states logged to ~/.claude/cold-review-history.jsonl
```

## Output format

Every issue includes severity, confidence, category, file, and a three-part structure (check / verdict / fix):

```json
{
  "pass": false,
  "review_status": "completed",
  "summary": "Chinese page links to English chapter",
  "issues": [
    {
      "severity": "major",
      "confidence": "high",
      "category": "reference",
      "file": "index.html",
      "check": "index.html line 43 links to ch3-en.html but this is the Chinese page",
      "verdict": "Cross-language reference.",
      "fix": "Change to ch3.html"
    }
  ]
}
```

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

### 3. Done

Next time Claude Code finishes a turn with uncommitted changes, Cold Eyes will review them.

### Recommended adoption path

1. Start with `COLD_REVIEW_MODE=report` — review results are logged but nothing is blocked. Read the history to see what it catches.
2. After a week, switch to `COLD_REVIEW_MODE=block` with `COLD_REVIEW_BLOCK_THRESHOLD=critical` (the default). Only critical issues block.
3. If the signal-to-noise ratio is good, optionally lower the threshold to `major`.

## Token usage

Every review consumes tokens from your Claude subscription. You see what it costs, you control when it runs, you decide the model.

## What gets reviewed

Cold Eyes reviews **all uncommitted changes** in the working tree — not just what Claude did in the current turn. It has no way to distinguish "changes Claude made" from "changes you had before opening the session."

**Commit or push before starting a new session.** This keeps the diff clean and the review accurate.

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
| `COLD_REVIEW_ALLOW_ONCE` | (unset) | `1` | Set to skip block once (logged as override) |

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

# One-time override when blocked by a false positive
export COLD_REVIEW_ALLOW_ONCE=1
```

### Ignore rules

Create `.cold-review-ignore` in your project root to exclude files from review. Uses fnmatch glob patterns:

```
# Lock files
*.lock
package-lock.json

# Build output
dist/*
build/*

# Minified
*.min.js
```

Built-in defaults already skip common lock files, build output, and minified files. Project-level patterns are additive.

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
| `overridden` | Would have blocked, but `COLD_REVIEW_ALLOW_ONCE=1` was set |

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
| `cold-review.sh` | Main Stop hook script (thin orchestrator) |
| `cold_review_engine.py` | Review pipeline: diff building, Claude call, policy, confidence filter |
| `cold-review-helper.py` | JSON parsing, prompt assembly, ignore/rank logic |
| `cold-review-prompt.txt` | System prompt template |
| `.cold-review-ignore` | Default ignore patterns |

## Background

This tool was built after observing [Cinder](https://github.com/shihchengwei-lab/Not-a-Mascot), a Claude Code buddy companion that provided independent commentary during coding sessions. Cinder was silently shut down on April 11, 2026. Cold Eyes carries forward the idea that a second pair of eyes — even artificial ones — catches things the first pair misses.

The difference: Cinder watched in real time and commented. Cold Eyes reviews after the fact and blocks if needed. Cinder was a companion. Cold Eyes is a gate.

## Building on top of Cold Eyes

Cold Eyes is a hook and a set of JSON files. Everything is designed to be readable and writable by other tools.

- **`cold-review-history.jsonl`** — One JSON object per line (v2 format includes `state`, `diff_stats`, `min_confidence`). Build a dashboard, filter by state, chart trends over time.
- **`cold-review-prompt.txt`** — Template with `{language}` placeholder. Swap in your own review criteria.
- **`.cold-review-ignore`** — fnmatch patterns. Add project-specific exclusions.

## Known limitations

- **Review history grows forever.** `~/.claude/cold-review-history.jsonl` is append-only. Periodically archive or truncate it yourself.
- **Large diffs get truncated.** Diffs over the token budget (default 12000) are cut. High-risk files are prioritized. When truncation causes files to be skipped, block messages include a warning with the count of unreviewed files.
- **Silent on auth failure.** If your Claude subscription is expired or rate-limited, the review logs a `failed` state. Check stderr or history.

## License

MIT
