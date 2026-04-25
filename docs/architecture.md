# Architecture

## Layers

```
Layer 1 - Shell shim (cold-review.sh)
  Guards: off mode, recursion, missing engine, not a git repo
  Atomic lock (mkdir-based, stale PID detection)
  Hook input parsing (stop_hook_active check + hook input handoff)
  Invokes Layer 2, translates JSON output to hook decision
  Fail-closed: any parse failure in block mode emits a block decision

Layer 2 - CLI + Engine (cli.py -> engine.py)
  CLI always dispatches run to the unified v1 engine
  --v2 is a hidden compatibility flag and no longer starts a separate pipeline

Layer 3 - Modules
  Core review modules handle diff collection, triage, context, model review,
  policy, coverage, local checks, protection output, history, and diagnostics.
  Retired session/retry/contract experiment code is not part of the package.
```

## Data Flow

```
1. collect_files()          git diff --name-only for the selected scope
2. filter_file_list()       remove binary, lock, generated, ignored files
3. rank_file_list()         sort by risk (security > core > config > test > docs)
4. classify_depth()         skip / shallow / deep
5. build_diff()             git diff with token budget, high-risk files first
6. load_intent_capsule()    optional low-weight recent user goal from hook metadata
7. build_prompt_text()      select shallow or deep prompt
8. ClaudeCliAdapter.review() invoke Claude CLI via subprocess
9. parse_review_output()    extract JSON from model response
10. apply_policy()          confidence, evidence, truncation, threshold decision
11. build_coverage_report() attach coverage and block if policy requires
12. run_local_checks()      run selected local checks once when useful
13. attach_protection()     create agent task, user message, fresh-review rerun protocol
14. log_to_history()        append outcome to ~/.claude/cold-review-history.jsonl
```

## Module Responsibilities

| Module | Purpose |
|--------|---------|
| `engine.py` | Unified `run()` orchestrator and gate enforcement |
| `cli.py` | argparse dispatcher for subcommands, `--version`, and hidden retired `--v2` compatibility |
| `local_checks.py` | Risk-based local check selection, changed-file targeting for soft checks, execution, result summaries, and hard-check block reason |
| `gates/result.py` | Normalizes local check output into structured findings |
| `protection.py` | Agent repair task, user-facing message, fresh-review rerun protocol, compact history summary |
| `history.py` | History logging, stats, quality report, prune, archive |
| `config.py` | Flat policy file loader and supported key validation |
| `doctor.py` | Environment checks, install verification, repo init |

## Key Design Decisions

- **Single product path.** Cold Eyes has one review pipeline. Local checks are a v1 protection layer, not a second reviewer.
- **No repair memory.** Block output can tell the main agent to fix and rerun, but Cold Eyes does not store pending block state or compare the next review against prior block records.
- **No retired session code in the runtime package.** The separate session, contract, retry, noise, and runner experiment is preserved only in release history, not as active source modules.
- **Local checks are bounded.** Selected checks run once. `pytest` and `pip check` are hard checks; `ruff` and `mypy` are soft checks scoped to changed Python files when possible. Missing tools and timeouts are warnings.
- **No PyYAML dependency.** Policy files use a flat `key: value` format parsed by a small custom parser. Unknown keys are silently dropped for forward compatibility.
- **No network connections.** All external communication goes through `git` and `claude` CLI subprocesses. Cold Eyes never opens sockets.
- **Fail-closed shell parser.** The hook parser emits a block decision in block mode if engine output is missing or malformed.
