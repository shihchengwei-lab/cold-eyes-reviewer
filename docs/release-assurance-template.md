# Release Assurance Template

Use this before releasing a gate-mode change.

## Scope

- Release:
- Date:
- Reviewer:
- Gate profile tested:

## Required Checks

- [ ] `pytest`
- [ ] `python cold_eyes/cli.py eval --eval-mode deterministic`
- [ ] `python cold_eyes/cli.py eval --eval-mode sweep`
- [ ] `init --profile gate` creates a usable `.cold-review-policy.yml`
- [ ] `scope: staged` reviews only staged diff
- [ ] `coverage_policy: warn` records warning without blocking
- [ ] `coverage_policy: block` emits Claude Stop-hook block JSON
- [ ] High-risk unreviewed file blocks independently
- [ ] Override history records `final_action: override_pass`
- [ ] Override is excluded from normal pass count
- [ ] `quality-report` shows override rate and coverage block rate
- [ ] Shell stdout is valid Claude Code JSON when blocked

## Manual Notes

- Coverage block reason includes percentage, minimum, unreviewed files, high-risk files, and next actions:
- Override reason/note sampled:
- Known risks:

## CLAUDE_AGENT_REVIEW

- Current Claude CLI flags checked:
- Current model aliases checked:
- Hook architecture remains command Stop hook:
