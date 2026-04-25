# Assurance Matrix

How well Cold Eyes detects different issue types, and what to expect.

## By issue category

The five categories from the review prompt (`cold-review-prompt.txt`), mapped to observable behavior.

| Category | Detectability | Blockability | Common FP | Common FN | Eval cases | Mitigation |
|---|---|---|---|---|---|---|
| **security** (injection, XSS, secrets, path traversal) | High | High (critical) | Test fixtures flagged as secrets | Subtle auth bypass not in diff | 4 TP, 2 FN | `confidence=high` reduces FP; FN cases in eval corpus |
| **correctness** (error handling, resource leak) | Medium-high | High (critical/major) | Intentional removal flagged | Multi-file logic errors | 2 TP | Override for intentional changes |
| **reference** (dangling import, dead ref) | Medium | Medium | Renamed-not-deleted | References to files not in diff | 1 TP | Broader diff scope (`pr-diff`) helps |
| **consistency** (text contradictions) | Low-medium | Low (usually minor) | Subjective wording changes | Cross-document inconsistency | 0 TP | Inherently limited — cross-document inconsistency needs a full-context view Cold Eyes does not have |
| **complexity** (copy-paste, unnecessary) | Low | Low (usually minor) | Legitimate duplication | Subtle over-engineering | 0 TP | Prompt excludes style preferences |

**Reading this table:** High detectability + low FP = reliable. Low detectability + high FN = don't rely on Cold Eyes alone for this category.

## By check type

The six checks from the review prompt, with what Cold Eyes sees and what it misses.

| Check | Scope | What Cold Eyes sees | What it misses |
|---|---|---|---|
| Logic errors / contradictions | Changed lines in diff | Obvious contradictions in modified code (removed validation, inverted condition) | Multi-file logic, business rules, intent mismatch |
| Security vulnerabilities | Changed lines in diff | Pattern-matched injection, hardcoded credentials, removed sanitization, eval/exec on user input | Configuration-dependent vulns, timing attacks, subtle authz bugs |
| Missing error handling | Changed lines in diff | Removed try/except, unclosed resources, deleted error paths | Error handling that should exist but was never written |
| Text/doc inconsistency | Changed text in diff | Changed text contradicting nearby text in the same diff | Cross-document inconsistency, outdated docs in unchanged files |
| Unnecessary complexity | Changed lines in diff | Copy-paste patterns visible in diff | Justified complexity, architectural decisions |
| Dangling references | Changed lines in diff | Deleted export still referenced in the same diff | References in files outside the diff |

## Infrastructure behavior

How Cold Eyes handles non-review situations.

| Situation | Behavior | State | Configurable |
|---|---|---|---|
| Empty diff (no changes) | Skip review, log | `skipped` + `skipped_no_change` | No |
| Docs/generated/image-only diff | Skip safe by default | `skipped` + `skipped_safe` | `docs_only_policy`, `generated_only_policy` |
| Matching protected envelope | Reuse cache without model call | `skipped` + `protected_cached` | `enable_envelope_cache` |
| Source/config shadow delta too large or unreviewed | Block before model call | `blocked` + `blocked_unreviewed_delta` | shadow delta budget keys |
| Diff exceeds token budget | Truncate by file priority, review partial | `blocked` or `passed` with truncation warning | `truncation_policy`: warn / soft-pass / fail-closed |
| Binary-only diff | Skip review, log when safe | `skipped` + `skipped_safe` | No |
| Claude CLI not found | Blocks when review is required; safe/no-change paths do not manufacture a block | `blocked` + `blocked_infra` or `infra_failed` | `infra_failure_policy` |
| CLI timeout / error | Blocks when review is required; safe/no-change paths do not manufacture a block | `blocked` + `blocked_infra` or `infra_failed` | `infra_failure_policy` |
| Malformed model output | Blocks when review is required | `blocked` + `blocked_infra` | `infra_failure_policy` |
| Python interpreter missing | Block (fail-closed) | Shell exits non-zero | No |
| Policy file too large | Warn + truncate at limit | Normal | 50-line content limit |

## Scope limitations

What a diff-centered review cannot do, and workarounds where they exist.

| Limitation | Impact | Workaround |
|---|---|---|
| No cross-file analysis | Cannot detect issues spanning files not in diff | Use `working` or `pr-diff` scope for broader diffs |
| No intent understanding | Cannot distinguish intentional from accidental changes | `arm-override` for known-good changes |
| No project history | Cannot detect regressions from previous versions | Compare with `git log` manually |
| Approximate line hints | `line_hint` may point to wrong line | Block output shows `~` prefix; always verify |
| Truncation gaps | Large diffs lose file coverage | Increase `max_tokens`, use `fail-closed` truncation policy |
| Model non-determinism | Same diff may get different findings across runs | Eval framework measures decision boundary; real-model variance is inherent |

## How to use this matrix

1. **Before adopting Cold Eyes:** Read the "What it misses" column. If your critical risk is in that column, Cold Eyes is not your primary defense.
2. **When tuning policy:** The FP/FN columns tell you which direction each category leans. Adjust threshold and confidence accordingly.
3. **When investigating a miss:** Check if the issue type is in-scope. If it's a known FN category, it's a product boundary, not a bug.
4. **When filing a bug:** If Cold Eyes missed something that IS in scope (high detectability category + issue visible in diff), that's a real miss worth reporting.
