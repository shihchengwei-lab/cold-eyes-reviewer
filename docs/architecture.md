# Architecture

## Layers

```
Layer 1 - Shell shim (cold-review.sh)
  Guards: recursion, missing engine, not a git repo
  Atomic lock (mkdir-based, stale PID detection, lock-active decision delegated to engine)
  Hook input parsing (stop_hook_active check + hook input handoff)
  Invokes Layer 2, translates JSON output to hook decision
  Fail-closed: any parse failure in block mode emits a block decision

Layer 2 - CLI + Engine (cli.py -> engine.py)
  CLI always dispatches run to the unified v2 engine
  --v2 is a hidden compatibility flag and no longer starts a separate pipeline

Layer 3 - Modules
  Core review modules handle diff collection, triage, context, model review,
  policy, coverage, local checks, protection output, history, and diagnostics.
  Retired session/retry/contract experiment code is not part of the package.
```

## Data Flow

```
1. build_review_envelope()  inspect staged, unstaged, untracked, policy, prompt, and cache identity
2. fast_path_decision()     skip no-change/safe-only, reuse cache, review, or block unreviewed delta
3. inspect_review_target()  record staged/unstaged/untracked/partial-stage visibility
4. rank_file_list()         sort selected review target by risk
5. classify_depth()         skipped_safe / shallow / deep
6. build_diff()             git diff with token budget, high-risk files first
7. load_intent_capsule()    optional low-weight recent user goal from hook metadata
8. build_prompt_text()      select shallow or deep prompt
9. ClaudeCliAdapter.review() invoke Claude CLI via subprocess
10. parse_review_output()   extract JSON from model response
11. apply_policy()          confidence, evidence, truncation, threshold decision
12. build_coverage_report() attach coverage and block if policy requires
13. run_local_checks()      run selected local checks once when useful
14. post-review envelope    block stale review if files changed during review
15. attach_protection()     create agent task, user message, fresh-review rerun protocol
16. log_to_history()        append outcome to ~/.claude/cold-review-history.jsonl
```

## Module Responsibilities

| Module | Purpose |
|--------|---------|
| `engine.py` | Unified `run()` orchestrator and gate enforcement |
| `cli.py` | argparse dispatcher for subcommands, `--version`, and hidden retired `--v2` compatibility |
| `envelope.py` | v2 review envelope, shadow delta target, cache decision, and no-silent-pass delta blocks |
| `target.py` | Review-target sentinel for staged/unstaged/untracked/partial-stage visibility and target policy decisions |
| `local_checks.py` | Risk-based local check selection, changed-file targeting for soft checks, execution, result summaries, and hard-check block reason |
| `gates/result.py` | Normalizes local check output into structured findings |
| `protection.py` | Agent repair task, user-facing talking points, fresh-review rerun protocol, compact history summary |
| `history.py` | History logging, stats, quality report, prune, archive |
| `config.py` | Flat policy file loader and supported key validation |
| `doctor.py` | Environment checks, install verification, repo init |

## Key Design Decisions

- **Single product path.** Cold Eyes has one review pipeline. Local checks and the v2 envelope are protection layers, not separate reviewers.
- **No repair memory.** Block output can tell the main agent to fix and rerun, but Cold Eyes does not store pending block state or compare the next review against prior block records.
- **No retired session code in the runtime package.** The separate session, contract, retry, noise, and runner experiment is preserved only in release history, not as active source modules.
- **Local checks are bounded.** Selected checks run once. `pytest` and `pip check` are hard checks; `ruff` and `mypy` are soft checks scoped to changed Python files when possible. Missing tools and timeouts are warnings.
- **Target integrity is explicit.** A pass means the effective review target passed. Target metadata records files outside the primary target, and the v2 envelope reviews or blocks unstaged/untracked source/config delta so staged scope does not become a silent whole-working-tree blind spot.
- **No PyYAML dependency.** Policy files use a flat `key: value` format parsed by a small custom parser. Unknown keys are silently dropped for forward compatibility.
- **No network connections.** All external communication goes through `git` and `claude` CLI subprocesses. Cold Eyes never opens sockets.
- **Fail-closed shell parser.** The hook parser emits a block decision in block mode if engine output is missing or malformed.
