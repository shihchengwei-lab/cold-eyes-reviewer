# Architecture

## Layers

```
Layer 1 — Shell shim (cold-review.sh)
  Guards: off mode, recursion, missing engine, not a git repo
  Atomic lock (mkdir-based, stale PID detection)
  Hook input parsing (stop_hook_active check)
  Invokes Layer 2, translates JSON output to hook decision
  Fail-closed: any parse failure in block mode emits a block decision

Layer 2 — CLI + Engine (cli.py → engine.py)
  CLI dispatches to engine.run() or diagnostic subcommands
  Engine orchestrates the full review pipeline (see Data Flow below)

Layer 3 — Modules (15 files in cold_eyes/)
  Each module has a single responsibility, no circular imports
```

## Data flow (engine.run)

```
1. collect_files()        — git diff --name-only for the selected scope
2. filter_file_list()     — remove binary, lock, generated, ignored files
3. rank_file_list()       — sort by risk (security > core > config > test > docs)
4. build_diff()           — git diff with token budget, high-risk files first
                            tracks: truncated files, budget-skipped, binary, unreadable
5. build_prompt_text()    — inject diff + language into system prompt template
6. ClaudeCliAdapter.review() — invoke Claude CLI via subprocess (encoding=utf-8)
7. parse_review_output()  — extract JSON from model response, strip markdown fences
8. validate_review()      — schema validation (schema_version, required fields, types)
9. filter_by_confidence() — remove issues below confidence threshold (deterministic)
10. apply_policy()        — truncation policy check → block/pass/report decision
11. log_to_history()      — append outcome to ~/.claude/cold-review-history.jsonl
```

## Module responsibilities

| Module | Purpose |
|--------|---------|
| `constants.py` | Shared constants: severity/confidence order, state names, deploy file list |
| `config.py` | Policy file loader (flat YAML, no PyYAML dependency, 9 valid keys) |
| `git.py` | `git_cmd()` wrapper, `collect_files`, `is_binary`, `build_diff` |
| `filter.py` | `filter_file_list` (ignore patterns), `rank_file_list` (risk sorting) |
| `prompt.py` | `build_prompt_text` (template + language substitution) |
| `claude.py` | `ModelAdapter` base, `ClaudeCliAdapter`, `MockAdapter`, `ReviewInvocation` |
| `review.py` | `parse_review_output` (JSON extraction from LLM response) |
| `schema.py` | `validate_review` (field presence, types, severity/confidence values) |
| `policy.py` | `apply_policy` (truncation + threshold + override → state), `format_block_reason` |
| `history.py` | `log_to_history`, `compute_stats`, `quality_report`, `prune`, `archive` |
| `override.py` | `arm_override` / `consume_override` (file-based, TTL expiry) |
| `doctor.py` | `run_doctor` (11 checks), `verify_install`, `run_doctor_fix`, `run_init` |
| `engine.py` | `run()` orchestrator, `_resolve()` settings, `_skip()`, `_infra_review()` |
| `cli.py` | argparse dispatcher for 11 subcommands + `--version` |
| `__init__.py` | `__version__` (single source of truth for package version) |

## Key design decisions

- **No PyYAML dependency.** Policy files use a flat `key: value` format parsed by a custom 40-line parser. Unknown keys are silently dropped for forward compatibility.
- **No network connections.** All external communication goes through `git` and `claude` CLI subprocesses. Cold Eyes never opens sockets.
- **Fail-closed by default.** Infrastructure failures (timeout, parse error, missing CLI) produce a block decision in block mode. This is deliberate: a broken reviewer should not silently pass unsafe code.
- **Confidence filter is deterministic.** The LLM assigns confidence levels, but the filter is a simple threshold comparison — no probabilistic logic.
- **Override tokens are file-based with TTL.** One-time use, stored in `~/.claude/`, expire after N minutes. No persistent state beyond the token file.
