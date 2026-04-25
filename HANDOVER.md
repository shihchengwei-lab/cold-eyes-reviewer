# Cold Eyes Reviewer Handover

Last updated: 2026-04-26

## Current State

- Version in source: `v2.0.0`
- Branch: `master`
- Latest pushed release commit: `7105fc9 Release v2.0.0 no silent pass delta gate`
- Latest tag / release: `v2.0.0`
- Latest GitHub Release title: `v2.0.0 - No Silent Pass Delta Gate`
- Repository: `https://github.com/shihchengwei-lab/cold-eyes-reviewer`
- Default branch: `master`
- Local deployed version: `2.0.0`
- Installed scripts path: `C:\Users\kk789\.claude\scripts`
- Windows-side `doctor`: `all_ok: true`
- Health notice schedule: configured as Windows scheduled task `Cold Eyes Reviewer Health Notice`
- GitHub Actions for latest pushed `master`, `v2.0.0`, and Release: success
- Working tree is clean after the v2.0.0 release and this handover update.

## Product Shape

Cold Eyes Reviewer is a single-path, diff-centered Stop hook reviewer for Claude Code.

The current contract is:

1. Claude Code finishes a turn.
2. `cold-review.sh` runs as a Stop hook.
3. Cold Eyes treats staged changes as the primary review target by default.
4. Before calling the model, the v2 envelope decides skip, cache, review, or block.
5. Pure chat/no-change turns and safe docs/generated turns do not call the LLM.
6. Unstaged or untracked source/config delta is reviewed as shadow delta or blocked if it cannot be safely reviewed.
7. If it blocks, it produces an Agent-facing repair task, a plain-language user message, and a fresh-review rerun protocol.
8. The main Agent fixes the current diff, runs relevant checks, stages the changes that should be reviewed, ends the turn, and the next Stop hook performs a brand-new review.

Important boundary:

- Cold Eyes does not use previous block records to validate repairs.
- Cold Eyes does not keep pending repair sessions.
- Cold Eyes does not decide product direction for the user.
- Intent context is low weight only; it cannot block without concrete diff evidence.
- History is for diagnostics, auto-tune, status, and override calibration, not repair memory.
- Default primary scope is `staged`, not `working`, to avoid slow reviews during normal reading or handoff-only turns.
- `gate_state` is now the authoritative v2 protection signal for status, history, and future automation.

## Recent Release Summary

### v2.0.0 - No Silent Pass Delta Gate

Status: committed, pushed, tagged, released, installed locally, and CI green.

Purpose: keep the low-friction staged default without allowing source/config changes outside the staged target to silently pass.

Changes:

- Added `cold_eyes/envelope.py` for v2 review envelope scanning, shadow delta target selection, cache matching, and no-silent-pass blocks.
- Added `GATE_SCHEMA_VERSION = 2` and authoritative `gate_state` values:
  - `protected`
  - `protected_cached`
  - `skipped_no_change`
  - `skipped_safe`
  - `blocked_issue`
  - `blocked_unreviewed_delta`
  - `blocked_stale_review`
  - `blocked_infra`
  - `blocked_lock_active`
  - `off_explicit`
- Added flat config/env keys:
  - `shadow_scope`
  - `include_untracked`
  - `enable_envelope_cache`
  - `max_shadow_delta_files`
  - `max_shadow_delta_bytes`
  - `infra_failure_policy`
  - `lock_active_policy`
  - `stale_review_policy`
  - `docs_only_policy`
  - `generated_only_policy`
- History entries can now include `gate_state`, `envelope`, `cache`, and `agent_action`.
- Stop hook lock contention now calls the engine with `--lock-active` instead of silently exiting.
- `mode: off` now records `off_explicit` instead of disappearing from history.
- README, failure modes, history schema, version policy, roadmap, gate-mode docs, scope strategy, trust model, troubleshooting, samples, and release assurance docs were updated for v2.

Behavior changes:

- Pure chat/no file changes records `skipped_no_change` and does not call the LLM.
- Docs/generated/image-only changes can record `skipped_safe` and do not call the LLM by default.
- Same trusted protected envelope records `protected_cached` and does not re-review.
- Unstaged or untracked source/config/test/migration delta is reviewed as shadow delta when it fits the budget.
- High-risk, binary, unreadable, unsupported, too-large, or over-budget source/config delta blocks as `blocked_unreviewed_delta`.
- Review-required infra failures block as `blocked_infra`.
- File changes during review block as `blocked_stale_review`.
- Lock contention with review-required changes blocks as `blocked_lock_active`.

Validation:

- `python -m pytest tests -q`: `662 passed, 6 skipped`
- `python -m ruff check .`: passed
- `git diff --check`: passed
- `python cold_eyes\cli.py eval --regression-check evals\baseline.json`: no regression, `33/33`
- `python cold_eyes\cli.py --version`: `cold-eyes-reviewer 2.0.0`
- `python C:\Users\kk789\.claude\scripts\cold_eyes\cli.py --version`: `cold-eyes-reviewer 2.0.0`
- Windows installed `doctor`: `all_ok: true`, deploy files `32 files`

Release:

- `https://github.com/shihchengwei-lab/cold-eyes-reviewer/releases/tag/v2.0.0`
- Release title: `v2.0.0 - No Silent Pass Delta Gate`

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

Latest local validation for v2.0.0:

- `python -m pytest tests -q`: `662 passed, 6 skipped`
- `python -m ruff check .`: passed
- `git diff --check`: passed
- `python cold_eyes\cli.py eval --regression-check evals\baseline.json`: no regression, `33/33`
- `python cold_eyes\cli.py --version`: `cold-eyes-reviewer 2.0.0`
- `python C:\Users\kk789\.claude\scripts\cold_eyes\cli.py --version`: `cold-eyes-reviewer 2.0.0`
- Windows installed `doctor`: `all_ok: true`

Windows installed `doctor` details from the latest check:

- Python: ok
- Git: ok
- Claude CLI: ok, `2.1.119 (Claude Code)`
- Deploy files: ok, 32 files in `C:\Users\kk789\.claude\scripts`
- Stop hook: ok
- Git repo: ok
- Policy file: ok
- Legacy helper: ok, no legacy helper
- Shell version: ok
- Health schedule: ok

Latest GitHub Actions:

- `master` Tests: success
  - v2.0.0 release commit: `https://github.com/shihchengwei-lab/cold-eyes-reviewer/actions/runs/24942125804`
  - v1.18.0 release commit: `https://github.com/shihchengwei-lab/cold-eyes-reviewer/actions/runs/24940912898`
  - Latest README quick start commit: `https://github.com/shihchengwei-lab/cold-eyes-reviewer/actions/runs/24939921011`
  - v1.17.1 release commit: `https://github.com/shihchengwei-lab/cold-eyes-reviewer/actions/runs/24937221771`
- `v2.0.0` Tests: success
  - `https://github.com/shihchengwei-lab/cold-eyes-reviewer/actions/runs/24942177919`
- `v2.0.0` Release: success
  - `https://github.com/shihchengwei-lab/cold-eyes-reviewer/actions/runs/24942177923`
- `v1.18.0` Tests: success
  - `https://github.com/shihchengwei-lab/cold-eyes-reviewer/actions/runs/24940980621`
- `v1.18.0` Release: success
  - `https://github.com/shihchengwei-lab/cold-eyes-reviewer/actions/runs/24940980651`
- `v1.17.1` Tests: success
  - `https://github.com/shihchengwei-lab/cold-eyes-reviewer/actions/runs/24937222235`
- `v1.17.1` Release: success
  - `https://github.com/shihchengwei-lab/cold-eyes-reviewer/actions/runs/24937222221`

Release:

- `https://github.com/shihchengwei-lab/cold-eyes-reviewer/releases/tag/v2.0.0`

## Last Released Repo Page Alignment

Checked after v2.0.0:

- Latest release is `v2.0.0 - No Silent Pass Delta Gate`.
- Latest tag is `v2.0.0`.
- Default branch is `master`.
- `origin/master` points at `7105fc9`.
- `v2.0.0` tag dereferences to `7105fc9`.
- README has a Quick start section near the top.
- README describes v2 envelope scanning, no-silent-pass delta protection, `gate_state`, and staged primary scope.
- `CHANGELOG.md` top entry is `v2.0.0 - feat: No Silent Pass Delta Gate`.
- `cold_eyes/__init__.py` reports `__version__ = "2.0.0"`.
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
  -> v2 review envelope scan / target sentinel / cache decision
  -> skip, cache, review, or block
  -> build staged + shadow delta review target
  -> shallow or deep review when needed
  -> Claude CLI review
  -> parse review JSON
  -> confidence / evidence / policy
  -> coverage gate
  -> selected local checks
  -> stale-review envelope check
  -> protection brief
  -> history logging
```

Important runtime modules:

- `cold_eyes/engine.py`: unified orchestration and default setting resolution
- `cold_eyes/envelope.py`: v2 review envelope, shadow delta, cache matching, and no-silent-pass delta blocks
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
- `COLD_REVIEW_SHADOW_SCOPE=working_delta`
- `COLD_REVIEW_INCLUDE_UNTRACKED=true`
- `COLD_REVIEW_ENABLE_ENVELOPE_CACHE=true`
- `COLD_REVIEW_MAX_SHADOW_DELTA_FILES=8`
- `COLD_REVIEW_MAX_SHADOW_DELTA_BYTES=60000`
- `COLD_REVIEW_INFRA_FAILURE_POLICY=block_when_review_required`
- `COLD_REVIEW_LOCK_ACTIVE_POLICY=block_when_review_required`
- `COLD_REVIEW_STALE_REVIEW_POLICY=block`
- `COLD_REVIEW_DOCS_ONLY_POLICY=skip_safe`
- `COLD_REVIEW_GENERATED_ONLY_POLICY=skip_safe`
- `COLD_REVIEW_CHECKS=auto`
- `COLD_REVIEW_CHECK_TIMEOUT_SEC=120`
- `COLD_REVIEW_AGENT_BRIEF=on`
- `COLD_REVIEW_INTENT_CONTEXT=on`
- `COLD_REVIEW_AUTO_TUNE=on`

Notes:

- `COLD_REVIEW_SCOPE=staged` keeps `git diff --cached` as the primary target; v2 still scans source/config working-tree delta.
- `COLD_REVIEW_SCOPE=working` restores the old full working-tree behavior.
- `COLD_REVIEW_SCOPE=head` reviews staged and unstaged changes against `HEAD`, but not untracked files.
- `COLD_REVIEW_SCOPE=pr-diff` reviews branch diff against `COLD_REVIEW_BASE`.
- Target sentinel policy values are `ignore`, `warn`, `block-high-risk`, and `block`.
- `gate_state` is the v2 protection signal. Common healthy states are `protected`, `protected_cached`, `skipped_no_change`, and `skipped_safe`; block states start with `blocked_`.
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

Installed package shape after v2.0.0:

- `C:\Users\kk789\.claude\scripts\cold_eyes`
- Active v2 envelope module under deployed `cold_eyes`: `envelope.py`
- Active target sentinel module under deployed `cold_eyes`: `target.py`
- Active support subpackage under deployed `cold_eyes`: `gates`
- Retired v2 directories should not appear in deployed scripts.

## Slow Stop Hook Diagnosis

The slowdown reported before v1.17.1 was caused by the default `working` scope reviewing the full dirty working tree on every Stop hook. v2.0.0 further reduced wasted review time by adding the no-silent-pass envelope: no-change turns skip, safe docs/generated turns skip, and matching protected envelopes can use cache without another LLM call.

The fix is now both local and repo-level:

- Repo hardcoded default was changed to `staged`.
- New `init` policy template writes `scope: staged`.
- v2 envelope keeps staged as the primary target while scanning source/config working-tree delta.
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
- Stronger after v2.0.0 because pure chat/no-change turns skip quickly, cached protected envelopes do not re-review, and unstaged/untracked source/config delta cannot silently pass.

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
- Reintroducing the retired `--v2` session path as a product route.
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
