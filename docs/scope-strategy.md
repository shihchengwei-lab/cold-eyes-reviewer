# Scope Strategy

Cold Eyes supports four diff scopes. Each has different trade-offs for coverage, noise, and truncation risk.

## Scope comparison

| Scope | What it sees | Includes untracked | Best for |
|-------|-------------|-------------------|----------|
| `working` | Staged + unstaged + untracked | Yes | Solo development, observation |
| `staged` | Staged primary target plus v2 shadow scan for source/config delta | Shadow scan only | Pre-commit gate |
| `head` | Staged + unstaged (vs HEAD) | No | Quick review of all edits |
| `pr-diff` | Diff against a base branch | No | CI / merge review |

## Choosing a scope

### Default gate posture

Use `staged` (the default). Staged files are the primary review target, so a dirty working tree or handoff-only session does not automatically trigger a full model review. v2 still scans unstaged and untracked source/config delta and either adds it to a small shadow review target or blocks if it cannot be safely reviewed.

```yaml
# .cold-review-policy.yml
scope: staged
```

### Full working-tree observation

Use `working` when you intentionally want Cold Eyes to see every uncommitted change, including new untracked files. This gives maximum visibility but may include noise from incomplete changes.

```yaml
scope: working
mode: block
block_threshold: critical
```

### CI / merge review

Use `pr-diff` with a base branch. Reviews the full diff between your branch and the target branch. Best for pull request checks.

```yaml
scope: pr-diff
base: main
```

### Observation mode

Use `working` with `mode: report`. See everything, block nothing. Good for the first week of adoption.

```yaml
scope: working
mode: report
```

## Scope and truncation

Larger scopes produce larger diffs, which increase truncation risk:

| Scope | Truncation risk | Why |
|-------|----------------|-----|
| `staged` | Low | User controls the primary target; shadow delta budget stays small |
| `head` | Medium | All uncommitted changes |
| `working` | Medium-High | Includes untracked files |
| `pr-diff` | High | Entire branch diff may be large |

When truncation occurs, Cold Eyes reviews files in risk-priority order (auth, payment, DB, migration, config, API first). Files that exceed the token budget are either partially reviewed or skipped entirely.

### Truncation policy options

Control how truncation affects the block decision:

| Policy | Behavior | Use when |
|--------|----------|----------|
| `warn` (default) | Adds warning, does not change decision | Normal usage |
| `soft-pass` | Forces pass if truncated and no issues found | Large repos where truncation is expected |
| `fail-closed` | Blocks if ANY files were unreviewed | High-security repos requiring full coverage |

```yaml
truncation_policy: fail-closed
```

## Scope interactions

### Dirty working tree + `staged` scope

If you have unstaged changes AND use `staged` scope, Cold Eyes treats the staged portion as the primary target. This is intentional: it matches the "review what I'm about to commit" mental model.

The v2 envelope then scans the rest of the working-tree delta. Unstaged or untracked source/config files are reviewed as shadow delta when they fit the file/byte budget, or blocked as `blocked_unreviewed_delta` when they do not. Docs/generated/image-only changes can skip safely without an LLM call.

The target sentinel still records files outside the configured review target for status visibility, and high-risk partial-stage files remain a block risk.

### `working` scope + noise

`working` scope may include files you don't intend to commit (temp files, scratch code, generated output). Use `.cold-review-ignore` to exclude noise patterns:

```
*.generated.*
vendor/
node_modules/
*.min.js
```

### `pr-diff` scope + missing base

If `base` is not set when using `pr-diff`, Cold Eyes raises a ConfigError. When review is required, v2 blocks as `blocked_infra`; shell-level failures that prevent valid engine JSON still fail closed in `cold-review.sh`.
