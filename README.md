# Cold Eyes Reviewer

A zero-context code reviewer for [Claude Code](https://docs.anthropic.com/en/docs/claude-code). Runs automatically after every session turn via Stop hook. Catches issues before they ship.

Cold Eyes sees only the git diff. It doesn't know what you asked for, doesn't know your project history, doesn't share context with the session. That's the point.

## How it works

```
Claude Code session ends
       │
       ▼
  Stop hook fires
       │
       ├─ No git changes? → skip
       ├─ Already reviewing? → skip (prevents recursion)
       │
       ▼
  Cold Eyes reviews the diff
       │
       ├─ block mode: issues found → blocks, feeds reason back to Claude → Claude fixes → done
       └─ report mode: logs review to ~/.claude/cold-review-history.jsonl → done
```

One review, one fix, then pass. No infinite loops.

## Output format

Every issue uses a three-part structure:

- **Check** (what was seen)
- **Verdict** (is it a problem — shorter = more serious)
- **Fix** (what to do about it)

```json
{
  "pass": false,
  "issues": [
    {
      "check": "index.html line 43 links to ch3-en.html but this is the Chinese page",
      "verdict": "Cross-language reference.",
      "fix": "Change to ch3.html"
    }
  ],
  "summary": "Chinese page links to English chapter"
}
```

All reviews are saved to `~/.claude/cold-review-history.jsonl`. They don't disappear.

## Install

### 1. Copy scripts

```bash
mkdir -p ~/.claude/scripts
cp cold-review.sh cold-review-helper.py cold-review-prompt.txt cold-review-profile.json ~/.claude/scripts/
```

### 2. Add Stop hook to `~/.claude/settings.json`

Add an entry to the `hooks.Stop` array in your settings:

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

If you already have other Stop hooks, just add the new object to the existing array.

### 3. Done

Next time Claude Code finishes a turn with uncommitted changes, Cold Eyes will review them.

## Important: token usage

Every review consumes tokens from your own Claude subscription. You see what it costs, you control when it runs, you decide the model.

## Important: what gets reviewed

Cold Eyes reviews **all uncommitted changes** in the working tree — not just what Claude did in the current turn. It has no way to distinguish "changes Claude made" from "changes you had before opening the session."

**Commit or push before starting a new session.** This keeps the diff clean and the review accurate. If you leave uncommitted changes from a previous session, the reviewer will review those too and may block Claude for things it didn't do.

This is by design. The reviewer sees what git sees. No more, no less.

## Configuration

### Environment variables

| Variable | Default | Options | Description |
|---|---|---|---|
| `COLD_REVIEW_MODE` | `block` | `block`, `report`, `off` | Block and force fix / log only / disable |
| `COLD_REVIEW_MODEL` | `opus` | `opus`, `sonnet`, `haiku` | Which model runs the review |
| `COLD_REVIEW_MAX_LINES` | `500` | any integer | Max diff lines to review (large diffs get truncated) |

```bash
# Use sonnet to save tokens
export COLD_REVIEW_MODEL=sonnet

# Just log, don't block
export COLD_REVIEW_MODE=report

# Turn off temporarily
export COLD_REVIEW_MODE=off
```

### Personality profile

Edit `~/.claude/scripts/cold-review-profile.json` to customize the reviewer's character:

```json
{
  "name": "Cold Eyes",
  "personality": "A methodical reviewer with zero context and zero mercy.",
  "language": "繁體中文（台灣）",
  "stats": {
    "RIGOR": 90,
    "SNARK": 30,
    "PATIENCE": 60,
    "PARANOIA": 75
  }
}
```

- **RIGOR** — how strictly it enforces correctness
- **SNARK** — how sarcastic the tone is
- **PATIENCE** — how much it explains vs. just flags
- **PARANOIA** — how aggressively it flags minor concerns

### Review prompt

Edit `~/.claude/scripts/cold-review-prompt.txt` to change what the reviewer checks for and how it responds.

## Requirements

- Claude Code CLI with an active subscription
- Python 3.x (for JSON parsing)
- Git (for diff collection)
- Bash (Git Bash on Windows works)

## Files

| File | Purpose |
|---|---|
| `cold-review.sh` | Main Stop hook script |
| `cold-review-helper.py` | JSON parsing and prompt assembly |
| `cold-review-prompt.txt` | System prompt template |
| `cold-review-profile.json` | Personality configuration |

## Background

This tool was built after observing [Cinder](https://github.com/shihchengwei-lab/Not-a-Mascot), a Claude Code buddy companion that provided independent commentary during coding sessions. Cinder was silently shut down on April 11, 2026. Cold Eyes carries forward the idea that a second pair of eyes — even artificial ones — catches things the first pair misses.

The difference: Cinder watched in real time and commented. Cold Eyes reviews after the fact and blocks if needed. Cinder was a companion. Cold Eyes is a gate.

## Known limitations

- **Review history grows forever.** `~/.claude/cold-review-history.jsonl` is append-only. If you use this daily for months, the file will get large. Periodically archive or truncate it yourself. A future version may add automatic rotation.
- **Large diffs get truncated.** Diffs over 500 lines (configurable via `COLD_REVIEW_MAX_LINES`) are cut to keep token usage reasonable. The reviewer is told the diff was truncated.
- **Silent on auth failure.** If your Claude Code subscription is expired or rate-limited, the review silently skips. Check stderr (`claude -d`) if you suspect reviews aren't running.

## License

MIT
