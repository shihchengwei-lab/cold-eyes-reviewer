# Release Note Template

Use this structure for every release. Goal: a reader can tell in under a minute whether this release changes behavior, cost, context use, or blocking posture.

## Copy This Block

```markdown
## vX.Y.Z — <short title>

### What changed

<1-2 sentences. "Add X", "Change Y", "Fix Z".>

### Behavior changes

- `none` or one bullet per Stop-hook behavior change.

### Cost changes

- `none` or changes to model tokens, local-check runtime, timeouts, or defaults.

### Context usage changes

- `none` or changes to deep-path context, detector hints, intent capsule, or local check inputs.

### Blocking / policy changes

- `none` or changes to `block_threshold`, `confidence`, coverage, local-check blocking, or override behavior.

### Migration / compatibility notes

- `none` or changed env vars, config keys, CLI flags, install behavior, or compatibility fallbacks.

### Who should care

<One line, e.g. "All Stop-hook users." / "Users with automatic local checks enabled." / "Docs-only.">

### Details

- <Grouped technical bullets.>
```

## Rules

- Every section is mandatory, even when the value is `none`.
- Do not redefine the product in release notes.
- Mention concrete identifiers users can grep for, such as `COLD_REVIEW_CHECKS`, `block_threshold`, `arm-override`, or `coverage_policy`.
- State the affected audience plainly.

## Example

```markdown
## v1.16.0 — unified local checks

### What changed

Retire the separate v2 session path and fold useful local checks into the unified v1 review.

### Behavior changes

- `run` always uses the unified v1 engine.
- `COLD_REVIEW_CHECKS=auto` can run selected local checks once.

### Cost changes

- Model token cost is unchanged. Wall-clock time can increase when selected local checks run.

### Context usage changes

- `none`

### Blocking / policy changes

- Hard local check failures (`pytest`, `pip check`) can block in block mode.

### Migration / compatibility notes

- `--v2` is retired and falls back to unified v1 with a warning.

### Who should care

All Stop-hook users, especially users who previously tried the v2 flag.
```
