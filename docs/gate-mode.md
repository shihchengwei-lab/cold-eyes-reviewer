# Gate Mode

Gate mode turns Cold Eyes into a Claude Code Stop-hook blocking gate. It is still a diff-centered risk gate, not a full-context reviewer.

## Scope

Gate mode reviews the configured diff scope, usually `staged`. It does not know the full product intent, all untouched code paths, or every external contract. Its job is to stop obvious high-cost risk before Claude Code continues.

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
```

Use:

```bash
python ~/.claude/scripts/cold_eyes/cli.py init --profile gate
```

`init --profile gate --force` replaces an existing `.cold-review-policy.yml`; without `--force`, existing policy is preserved.

## Adoption Path

1. **Observe** - run in `report` mode first. Review history and tune ignores.
2. **Conservative gate** - block only high-confidence critical issues; keep coverage as warn.
3. **Standard gate** - use critical/medium with `minimum_coverage_pct: 80`.
4. **Strict gate** - enable `coverage_policy: block` or lower the block threshold only after measuring override rate.

## Coverage Behavior

Coverage is based on candidate files after filtering and risk ranking.

- `reviewed_files`: files fully included in the model diff.
- `total_files`: candidate files after filtering and ranking.
- `unreviewed_files`: `partial_files`, `skipped_budget`, `skipped_binary`, and `skipped_unreadable`.
- Partial files count as incomplete.

Coverage block is not a model issue. It records `cold_eyes_verdict: incomplete`, `final_action: coverage_block`, and `authority: coverage_gate`.

## Override Governance

Override means human risk acceptance, not normal pass.

- Review finding block: `cold_eyes_verdict: fail`, `final_action: block`, `authority: cold_eyes`.
- Coverage block: `cold_eyes_verdict: incomplete`, `final_action: coverage_block`, `authority: coverage_gate`.
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
