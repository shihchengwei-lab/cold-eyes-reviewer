# Cold Eyes Reviewer Handover

Last updated: 2026-04-26

## Current State

- Version: `v1.18.0`
- Branch: `master`
- Latest pushed release commit: `f2d289f Release v1.18.0 target sentinel`
- Latest tag / release: `v1.18.0`
- Repository: `https://github.com/shihchengwei-lab/cold-eyes-reviewer`
- Default branch: `master`
- Local deployed version: `1.18.0`
- Installed scripts path: `C:\Users\kk789\.claude\scripts`
- Windows-side `doctor`: `all_ok: true`
- Health notice schedule: configured as Windows scheduled task `Cold Eyes Reviewer Health Notice`
- GitHub Actions for latest pushed `master`, `v1.18.0`, and Release: success
- Working tree is clean after the v1.18.0 release and this handover alignment.

## Product Shape

Cold Eyes Reviewer is a single-path, diff-centered Stop hook reviewer for Claude Code.

The current contract is:

1. Claude Code finishes a turn.
2. `cold-review.sh` runs as a Stop hook.
3. Cold Eyes reviews the staged git diff by default.
4. If it blocks, it produces an Agent-facing repair task, a plain-language user message, and a fresh-review rerun protocol.
5. The main Agent fixes the current diff, runs relevant checks, stages the changes that should be reviewed, ends the turn, and the next Stop hook performs a brand-new review.

Important boundary:

- Cold Eyes does not use previous block records to validate repairs.
- Cold Eyes does not keep pending repair sessions.
- Cold Eyes does not decide product direction for the user.
- Intent context is low weight only; it cannot block without concrete diff evidence.
- History is for diagnostics, auto-tune, status, and override calibration, not repair memory.
- Default scope is now `staged`, not `working`, to avoid slow reviews during normal reading or handoff-only turns.

## Recent Release Summary

### v1.18.0 - review-target sentinel

Status: committed, pushed, tagged, released, installed locally, and CI green.

Purpose: make Cold Eyes tell the Agent whether the configured review target actually covers the current changes, without requiring the user to understand staged diff, untracked files, or partial staging.

Changes:

- Added `cold_eyes/target.py` for staged, unstaged, untracked, partial-stage, and high-risk unreviewed file inspection.
- Added target policies:
  - `dirty_worktree_policy: warn`
  - `untracked_policy: warn`
  - `partial_stage_policy: block-high-risk`
- Added `status --human` with `READY`, `ATTENTION`, `NOT_PROTECTING`, and `UNKNOWN`.
- Added optional history `target` field.
- Added `final_action: target_block` and `authority: target_sentinel`.
- Updated protection output so target blocks tell the Agent to stage the complete intended change, intentionally ignore files, or switch scope.
- Updated docs to clarify that a pass means the configured review target passed, not necessarily the whole working tree.

Behavior changes:

- In staged scope, unstaged and untracked files now appear as target attention instead of silent blind spots.
- High-risk partially staged files block by default in `mode: block`.
- `working` scope still reviews untracked files as part of the target, so they are not counted as unreviewed.

Validation:

- `python -m pytest tests -q`: `650 passed, 6 skipped`
- `python -m ruff check .`: passed
- `git diff --check`: passed
- `python cold_eyes\cli.py eval --regression-check evals\baseline.json`: no regression, `33/33`
- `python cold_eyes\cli.py --version`: `cold-eyes-reviewer 1.18.0`
- Local deployed version: `cold-eyes-reviewer 1.18.0`
- Windows installed `doctor`: `all_ok: true`
- `status --human` currently reports `READY` in the clean working tree.

Release:

- `https://github.com/shihchengwei-lab/cold-eyes-reviewer/releases/tag/v1.18.0`

### Post-release README quick start

Commit: `36a6e74 docs: add quick start to readme`

Purpose: make the GitHub README easier for a new user to start from.

Changes:

- Added `## Quick start` immediately after the Cinder background paragraph and before `## What it is`.
- The quick start shows:
  - `bash install.sh`
  - `python ~/.claude/scripts/cold_eyes/cli.py init`
  - `python ~/.claude/scripts/cold_eyes/cli.py doctor`
- It tells users to add the Stop hook from the Install section to `~/.claude/settings.json`.
- It explicitly says Cold Eyes reviews staged changes by default.

Validation:

- `git diff --check -- README.md`: passed before commit.
- GitHub Actions `master` Tests: success, run `24939921011`.

### v1.17.1 - staged scope default

Purpose: fix high Stop-hook latency caused by reviewing the full working tree on every turn.

Changes:

- Changed the hardcoded default scope from `working` to `staged`.
- `init` now writes `scope: staged` for new policy files.
- README, gate-mode docs, scope strategy, tuning docs, shell comments, and tests now describe `staged` as the default.
- Users who want the previous behavior can still set:
  - `COLD_REVIEW_SCOPE=working`
  - or `scope: working` in `.cold-review-policy.yml`

Behavior changes:

- Reading handoff files, chatting, or keeping old unstaged edits no longer triggers a model review.
- The gate reviews only `git diff --cached` unless scope is overridden.
- With no staged changes, the hook exits quickly with `cold-review: skipped (no changes)`.

Validation:

- Local tests: `632 passed, 6 skipped`
- `python -m ruff check .`: passed
- `git diff --check`: passed
- Local deployed hook smoke test with dirty unstaged `HANDOVER.md`: skipped in about `0.6s`
- GitHub Actions:
  - `master` Tests: success, run `24937221771`
  - `v1.17.1` Tests: success, run `24937222235`
  - `v1.17.1` Release: success, run `24937222221`

Release:

- `https://github.com/shihchengwei-lab/cold-eyes-reviewer/releases/tag/v1.17.1`

### v1.17.0 - Agent health notices

Purpose: make gate health visible to the Agent without requiring the user to remember to ask.

Changes:

- Added `status`, a low-detail health command for the current repo.
- Added `agent-notice`, a low-detail Agent-facing health notice command.
- Install now creates a weekly Agent health notice schedule by default.
- Schedule timing is adjustable:
  - `COLD_REVIEW_HEALTH_INTERVAL_DAYS`
  - `COLD_REVIEW_HEALTH_TIME`
  - `COLD_REVIEW_HEALTH_SCHEDULE=off`
- `doctor --fix` can restore the scheduled health notice and clear stale notices.
- Stop hook infrastructure failures write a persistent Agent notice.
- Agent notices use low-detail levels:
  - `attention`
  - `gate_unreliable`
  - `schedule_missing`
- Automatic pytest targeting is more precise for high-risk Python source changes.

Behavior changes:

- Normal review blocks count as healthy runtime behavior.
- Missing or infrastructure-failed history asks for attention.
- The user does not need to manually ask "is the gate healthy?"
- The notice stays quiet when healthy and appears only when the setup needs Agent attention.

### v1.16.1 - cleanup and lightening

Purpose: make the repo structure match the unified v1 product path.

Changes:

- Removed retired v2 experiment packages from active source:
  - `cold_eyes/session`
  - `cold_eyes/contract`
  - `cold_eyes/retry`
  - `cold_eyes/noise`
  - `cold_eyes/runner`
  - `cold_eyes/type_defs.py`
- Removed tests that only covered those retired packages.
- Kept the hidden `--v2` compatibility flag. It only warns and falls back to unified v1.
- Made `cold_eyes/gates/result.py` self-contained.
- Scoped soft local checks to changed Python files when possible.

### v1.16.0 - unified local checks

Purpose: retire user-visible v2 split and fold useful local check behavior into v1.

Changes:

- `run` always uses the unified v1 engine.
- `--v2` is hidden compatibility only.
- No writes to `~/.claude/cold-review-sessions/sessions.jsonl`.
- Added optional `checks` outcome field.
- Added `COLD_REVIEW_CHECKS=auto|off`, default `auto`.
- Added `COLD_REVIEW_CHECK_TIMEOUT_SEC`, default `120`.
- `pytest` and `pip check` are hard checks.
- `ruff` and `mypy` are soft checks.
- Missing tools and timeouts warn but do not block.

## Validation

Latest local validation for v1.18.0:

- `python -m pytest tests -q`: `650 passed, 6 skipped`
- `python -m ruff check .`: passed
- `git diff --check`: passed
- `python cold_eyes\cli.py eval --regression-check evals\baseline.json`: no regression, `33/33`
- `python cold_eyes\cli.py --version`: `cold-eyes-reviewer 1.18.0`
- `python C:\Users\kk789\.claude\scripts\cold_eyes\cli.py --version`: `cold-eyes-reviewer 1.18.0`
- Windows installed `doctor`: `all_ok: true`

Windows installed `doctor` details from the latest check:

- Python: ok
- Git: ok
- Claude CLI: ok, `2.1.119 (Claude Code)`
- Deploy files: ok, 31 files in `C:\Users\kk789\.claude\scripts`
- Stop hook: ok
- Git repo: ok
- Policy file: ok
- Legacy helper: ok, no legacy helper
- Shell version: ok
- Health schedule: ok

Latest GitHub Actions:

- `master` Tests: success
  - v1.18.0 release commit: `https://github.com/shihchengwei-lab/cold-eyes-reviewer/actions/runs/24940912898`
  - Latest README quick start commit: `https://github.com/shihchengwei-lab/cold-eyes-reviewer/actions/runs/24939921011`
  - v1.17.1 release commit: `https://github.com/shihchengwei-lab/cold-eyes-reviewer/actions/runs/24937221771`
- `v1.18.0` Tests: success
  - `https://github.com/shihchengwei-lab/cold-eyes-reviewer/actions/runs/24940980621`
- `v1.18.0` Release: success
  - `https://github.com/shihchengwei-lab/cold-eyes-reviewer/actions/runs/24940980651`
- `v1.17.1` Tests: success
  - `https://github.com/shihchengwei-lab/cold-eyes-reviewer/actions/runs/24937222235`
- `v1.17.1` Release: success
  - `https://github.com/shihchengwei-lab/cold-eyes-reviewer/actions/runs/24937222221`

Release:

- `https://github.com/shihchengwei-lab/cold-eyes-reviewer/releases/tag/v1.18.0`

## Repo Page Alignment

Checked after v1.18.0:

- Latest release is `v1.18.0`.
- Latest tag is `v1.18.0`.
- Default branch is `master`.
- `v1.18.0` tag points at `f2d289f`.
- README has a Quick start section near the top.
- README describes staged scope as the default.
- Local README now also documents target sentinel policy keys and `status --human`.
- README still documents `working`, `head`, and `pr-diff` as explicit alternatives.
- README describes Agent health notices and automatic local checks.
- CI on `master` and tag are green.
- Release workflow is green.

## Current Architecture

Runtime path:

```text
cold-review.sh
  -> cold_eyes/cli.py
  -> cold_eyes/engine.py
  -> git diff collection / target sentinel / filtering / ranking
  -> skip, shallow, or deep review
  -> Claude CLI review
  -> parse review JSON
  -> confidence / evidence / policy
  -> coverage gate
  -> selected local checks
  -> protection brief
  -> history logging
```

Important runtime modules:

- `cold_eyes/engine.py`: unified orchestration and default setting resolution
- `cold_eyes/git.py`: diff scope collection and diff construction
- `cold_eyes/target.py`: target sentinel for staged, unstaged, untracked, partial-stage, and high-risk unreviewed file visibility
- `cold_eyes/cli.py`: public CLI and hidden retired `--v2` compatibility
- `cold_eyes/local_checks.py`: automatic local check selection and execution
- `cold_eyes/gates/result.py`: local check result parsing
- `cold_eyes/protection.py`: Agent task, user message, rerun protocol
- `cold_eyes/history.py`: append-only history, status, stats, quality report, prune, archive
- `cold_eyes/autotune.py`: low-frequency tuning from local history
- `cold_eyes/intent.py`: low-weight user intent capsule
- `cold_eyes/coverage_gate.py`: incomplete/high-risk coverage protection
- `cold_eyes/health.py`: Agent-facing health notices and Windows schedule integration
- `cold_eyes/doctor.py`: installation and environment diagnosis

## Default Behavior

Key defaults:

- `COLD_REVIEW_MODE=block`
- `COLD_REVIEW_MODEL=sonnet`
- `COLD_REVIEW_SHALLOW_MODEL=sonnet`
- `COLD_REVIEW_SCOPE=staged`
- `COLD_REVIEW_BLOCK_THRESHOLD=critical`
- `COLD_REVIEW_CONFIDENCE=medium`
- `COLD_REVIEW_CONTEXT_TOKENS=2000`
- `COLD_REVIEW_MINIMUM_COVERAGE_PCT=80`
- `COLD_REVIEW_COVERAGE_POLICY=warn`
- `COLD_REVIEW_FAIL_ON_UNREVIEWED_HIGH_RISK=true`
- `COLD_REVIEW_DIRTY_WORKTREE_POLICY=warn`
- `COLD_REVIEW_UNTRACKED_POLICY=warn`
- `COLD_REVIEW_PARTIAL_STAGE_POLICY=block-high-risk`
- `COLD_REVIEW_CHECKS=auto`
- `COLD_REVIEW_CHECK_TIMEOUT_SEC=120`
- `COLD_REVIEW_AGENT_BRIEF=on`
- `COLD_REVIEW_INTENT_CONTEXT=on`
- `COLD_REVIEW_AUTO_TUNE=on`

Notes:

- `COLD_REVIEW_SCOPE=staged` reviews only `git diff --cached`.
- `COLD_REVIEW_SCOPE=working` restores the old full working-tree behavior.
- `COLD_REVIEW_SCOPE=head` reviews staged and unstaged changes against `HEAD`, but not untracked files.
- `COLD_REVIEW_SCOPE=pr-diff` reviews branch diff against `COLD_REVIEW_BASE`.
- Target sentinel policy values are `ignore`, `warn`, `block-high-risk`, and `block`.
- `COLD_REVIEW_CHECKS=off` disables automatic local checks.
- `COLD_REVIEW_AGENT_BRIEF=off` disables the Agent repair brief and rerun protocol.
- `COLD_REVIEW_INTENT_CONTEXT=off` disables intent capsule extraction.
- `COLD_REVIEW_ALLOW_ONCE=1` is deprecated; use `arm-override`.

## Local Deployment Notes

Install command:

```bash
bash install.sh
```

Windows verification command:

```powershell
python "$env:USERPROFILE\.claude\scripts\cold_eyes\cli.py" doctor
```

Local deployed version check:

```powershell
python "$env:USERPROFILE\.claude\scripts\cold_eyes\cli.py" --version
```

Current local Claude Stop hook command in `C:\Users\kk789\.claude\settings.json`:

```text
bash C:/Users/kk789/.claude/scripts/cold-review.sh
```

The hook no longer needs an explicit `COLD_REVIEW_SCOPE=staged` override because staged scope is now the repo default.

Known environment detail:

- Running `bash install.sh` through WSL/Git Bash can report `claude_cli` as missing if that shell cannot see the Windows Claude CLI.
- The authoritative Windows-side check is the PowerShell `doctor` command above.
- Current Windows-side `doctor` is green.

Installed package shape after v1.18.0:

- `C:\Users\kk789\.claude\scripts\cold_eyes`
- Active target sentinel module under deployed `cold_eyes`: `target.py`
- Active support subpackage under deployed `cold_eyes`: `gates`
- Retired v2 directories should not appear in deployed scripts.

## Slow Stop Hook Diagnosis

The slowdown reported before v1.17.1 was caused by the default `working` scope reviewing the full dirty working tree on every Stop hook.

The fix is now both local and repo-level:

- Local Claude hook was changed to `COLD_REVIEW_SCOPE=staged`.
- Repo hardcoded default was changed to `staged`.
- New `init` policy template writes `scope: staged`.
- Docs and tests were updated.

If the user reports another multi-minute Stop delay:

1. Check whether Cold Eyes is still fast:

   ```powershell
   python "$env:USERPROFILE\.claude\scripts\cold_eyes\cli.py" status
   ```

2. Check recent Cold Eyes history for duration and scope:

   ```powershell
   Get-Content "$env:USERPROFILE\.claude\cold-review-history.jsonl" -Tail 20
   ```

3. If Cold Eyes entries show `scope: staged` and short durations, the remaining delay is likely from another Claude Stop hook, especially the Codex plugin hook if enabled.

4. In that case inspect `C:\Users\kk789\.claude\settings.json` and Claude plugin state, not Cold Eyes first.

## First-Principles Assessment

Current tool quality:

- Good as a daily safety layer for a non-engineer collaborating with AI.
- Useful because it blocks some high-cost, obvious diff-level mistakes without asking the user to read code review.
- Stronger after v1.14-v1.16 because block output is Agent-actionable.
- Stronger after v1.17.0 because gate health can notify the Agent without user prompting.
- Stronger after v1.17.1 because default staged scope makes the background gate low-noise enough for ordinary handoff reading and conversation.
- Stronger after v1.18.0 because target sentinel makes staged-scope blind spots visible and can block high-risk partial staging.

What it is not:

- Not a guarantee that no bugs ship.
- Not a product/spec decision maker.
- Not a full semantic codebase reviewer.
- Not a multi-language test orchestrator yet.

Remaining useful iteration areas:

1. Stop-hook duration attribution across multiple Claude hooks, so the Agent can say which hook is slow without exposing technical details to the user.
2. Better installer handling for Windows/Git Bash path differences, because `/mnt/c` vs `/c` matters on this machine.
3. Per-language local checks beyond Python, if the user starts using it heavily in JS/TS or other stacks.
4. Onboard and smoke-test commands, so first-time setup can be verified with one command and without a model call.
5. A small non-engineer summary for "what happened last run" that is more useful than raw history but less detailed than full findings.

Avoid:

- Reintroducing session memory or repair-session tracking.
- Reintroducing v2 as a product route.
- Making Cold Eyes decide user/product intent.
- Returning to `working` as the default scope.
- Expanding prompts as the main quality lever before measuring misses.

## If Continuing Work

Before editing:

```powershell
git status -sb
python cold_eyes\cli.py --version
python "$env:USERPROFILE\.claude\scripts\cold_eyes\cli.py" --version
python "$env:USERPROFILE\.claude\scripts\cold_eyes\cli.py" status --human
```

Before release:

```powershell
python -m pytest tests -q
python -m ruff check .
git diff --check
python cold_eyes\cli.py eval --regression-check evals\baseline.json
python "$env:USERPROFILE\.claude\scripts\cold_eyes\cli.py" doctor
```

After release:

```powershell
gh run list --limit 10
gh release list --limit 5
gh repo view shihchengwei-lab/cold-eyes-reviewer --json description,repositoryTopics,defaultBranchRef
```

Repo page alignment checklist:

- Latest release matches `cold_eyes.__version__`.
- README on `origin/master` matches current positioning.
- Default scope is documented as `staged`.
- About description does not mention retired v2/session/retry behavior.
- Topics still include `local-checks`.
- CI on `master` and tag are green.
