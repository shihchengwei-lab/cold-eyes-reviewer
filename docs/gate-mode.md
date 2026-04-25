# Gate Mode

Gate mode turns Cold Eyes into a Claude Code Stop-hook blocking gate. It is still a diff-centered risk gate, not a full-context reviewer.

## Scope

Gate mode reviews the effective v2 review envelope. The default primary scope is `staged`, so normal reading, handoff review, and scratch edits do not trigger a full model review on every Stop hook. Stage the changes you want reviewed before ending the turn. v2 still scans unstaged and untracked source/config delta and either reviews it as a small shadow target or blocks if it cannot be safely reviewed. Use `working` manually when you want Cold Eyes to review every uncommitted working-tree change as the primary target. Cold Eyes does not know the full product intent, all untouched code paths, or every external contract. Its job is to stop obvious high-cost risk before Claude Code continues.

When gate mode blocks, the hook reason is agent-first: it tells the agent what
to fix, includes a plain-language message to relay to the user, and gives the
main agent a fresh-review rerun protocol. The user does not need to remember a
manual command: the agent fixes the current diff, runs relevant checks, then
ends the turn so the next Stop hook runs Cold Eyes again.

Cold Eyes does not use previous block records as repair memory. If the next
hook blocks again, that result is a new cold review of the current diff.

## Baseline Profile

```yaml
mode: block
scope: staged
model: sonnet
block_threshold: critical
confidence: medium
truncation_policy: warn
minimum_coverage_pct: 80
coverage_policy: warn
fail_on_unreviewed_high_risk: true
shadow_scope: working_delta
include_untracked: true
enable_envelope_cache: true
infra_failure_policy: block_when_review_required
lock_active_policy: block_when_review_required
stale_review_policy: block
```

Use:

```bash
python ~/.claude/scripts/cold_eyes/cli.py init
```

Gate is the default init profile. `init --force` replaces an existing `.cold-review-policy.yml`; without `--force`, existing policy is preserved.

## Adoption Path

1. **Hold quality** - recent blocks, overrides, infra failures, or high-risk coverage gaps keep full context and stronger coverage posture.
2. **Balanced** - quiet history keeps the baseline.
3. **Fast-safe** - clean but expensive history reduces bounded context first.

## Coverage Behavior

Coverage is based on candidate files after filtering and risk ranking.

- `reviewed_files`: files fully included in the model diff.
- `total_files`: candidate files after filtering and ranking.
- `unreviewed_files`: `partial_files`, `skipped_budget`, `skipped_binary`, and `skipped_unreadable`.
- Partial files count as incomplete.

Coverage block is not a model issue. It records `cold_eyes_verdict: incomplete`, `final_action: coverage_block`, and `authority: coverage_gate`.

## Intent Capsule

When Claude Code hook metadata exposes a transcript path, Cold Eyes extracts a
small recent-user-goal capsule for deep reviews. This is low authority: it can
help catch obvious "the diff does the opposite of what the user asked" cases,
but it cannot override diff evidence. Intent findings without concrete diff
evidence are downgraded below the default confidence threshold.

## Override Governance

Override means human risk acceptance, not normal pass.

- Review finding block: `cold_eyes_verdict: fail`, `final_action: block`, `authority: cold_eyes`.
- Coverage block: `cold_eyes_verdict: incomplete`, `final_action: coverage_block`, `authority: coverage_gate`.
- Delta block: `gate_state: blocked_unreviewed_delta`, `final_action: unreviewed_delta_block`, `authority: delta_sentinel`.
- Infra/stale/lock blocks: `gate_state: blocked_infra`, `blocked_stale_review`, or `blocked_lock_active`.
- Override: `state: overridden`, `action: pass`, `final_action: override_pass`, `authority: human_override`.

Suggested override reasons: `false_positive`, `acceptable_risk`, `urgent_hotfix`, `test_environment_only`, `infrastructure`, `unclear`, `other`.

## Claude Hook Compatibility

MVP stays on Claude Code command Stop hook. `cold-review.sh` must emit parseable JSON to stdout only when blocking:

```json
{"decision":"block","reason":"..."}
```

Status messages belong on stderr. Prompt hooks and agent hooks are out of scope for this MVP.

## CLAUDE_AGENT_REVIEW

- Do not change the `claude -p --append-system-prompt-file --output-format json` path in this MVP unless Claude Agent confirms current Claude Code CLI flags or model aliases need adjustment.
- Do not adopt Claude Code `type: "agent"` hooks in this MVP. The agent hook is experimental; Claude Agent should confirm before any hook-architecture upgrade.
