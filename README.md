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

Add this to your `hooks.Stop` array:

```json
{
  "hooks": [
    {
      "type": "command",
      "command": "bash ~/.claude/scripts/cold-review.sh",
      "timeout": 120000
    }
  ]
}
```

### 3. Done

Next time Claude Code finishes a turn with uncommitted changes, Cold Eyes will review them.

## Configuration

### Environment variables

| Variable | Default | Options | Description |
|---|---|---|---|
| `COLD_REVIEW_MODE` | `block` | `block`, `report`, `off` | Block and force fix / log only / disable |
| `COLD_REVIEW_MODEL` | `opus` | `opus`, `sonnet`, `haiku` | Which model runs the review |

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

## License

MIT
