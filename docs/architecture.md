# Architecture

## Layers

```
Layer 1 — Shell shim (cold-review.sh)
  Guards: off mode, recursion, missing engine, not a git repo
  Atomic lock (mkdir-based, stale PID detection)
  Hook input parsing (stop_hook_active check + hook input handoff)
  Invokes Layer 2, translates JSON output to hook decision
  Fail-closed: any parse failure in block mode emits a block decision

Layer 2 — CLI + Engine (cli.py → engine.py or session_runner.py)
  CLI dispatches to engine.run() (v1 default) or run_session() (v2, --v2 flag)
  Engine orchestrates the review pipeline (see Data Flow below)

Layer 3 — Modules (22 top-level + 6 sub-packages in cold_eyes/)
  v1 core: 22 modules, each with a single responsibility, no circular imports
  v2 sub-packages: session, contract, gates, retry, noise, runner
```

## Data flow (engine.run)

```
1. collect_files()        — git diff --name-only for the selected scope
2. filter_file_list()     — remove binary, lock, generated, ignored files
3. rank_file_list()       — sort by risk (security > core > config > test > docs)
4. build_diff()           — git diff with token budget, high-risk files first
                            tracks: truncated files, budget-skipped, binary, unreadable
5. load_intent_capsule()  — optional low-weight recent user goal from hook metadata
6. build_prompt_text()    — inject diff + language into system prompt template
7. ClaudeCliAdapter.review() — invoke Claude CLI via subprocess (encoding=utf-8)
8. parse_review_output()  — extract JSON from model response, strip markdown fences
9. validate_review()      — schema validation (schema_version, required fields, types)
10. filter_by_confidence() — remove issues below confidence threshold (deterministic)
11. apply_policy()        — truncation policy check → block/pass/report decision
12. attach_protection()   — turn blocks into agent repair task + user message
13. log_to_history()      — append outcome to ~/.claude/cold-review-history.jsonl
```

## Module responsibilities

| Module | Purpose |
|--------|---------|
| `constants.py` | Shared constants: severity/confidence order, state names, deploy file list |
| `config.py` | Policy file loader (flat YAML, no PyYAML dependency, recognised keys only) |
| `git.py` | `git_cmd()` wrapper, `collect_files`, `is_binary`, `build_diff` |
| `filter.py` | `filter_file_list` (ignore patterns), `rank_file_list` (risk sorting) |
| `prompt.py` | `build_prompt_text` (template + language substitution) |
| `claude.py` | `ModelAdapter` base, `ClaudeCliAdapter`, `MockAdapter`, `ReviewInvocation` |
| `review.py` | `parse_review_output` (JSON extraction from LLM response) |
| `schema.py` | `validate_review` (field presence, types, severity/confidence values) |
| `policy.py` | `apply_policy` (truncation + threshold + override → state), `format_block_reason` |
| `history.py` | `log_to_history`, `compute_stats`, `quality_report`, `prune`, `archive` |
| `autotune.py` | Quality-first auto-tune recommendations and low-frequency automatic policy writes |
| `intent.py` | Low-weight hook/transcript intent capsule extraction |
| `protection.py` | Agent repair task, user-facing message, and compact protection history summary |
| `override.py` | `arm_override` / `consume_override` (file-based, TTL expiry) |
| `doctor.py` | `run_doctor` (11 checks), `verify_install`, `run_doctor_fix`, `run_init` |
| `engine.py` | `run()` orchestrator, `_resolve()` settings, `_skip()`, `_infra_review()` |
| `cli.py` | argparse dispatcher for 11 subcommands + `--version` + `--v2` flag |
| `type_defs.py` | Shared TypedDict definitions + helpers (generate_id, now_iso) for v2 |
| `__init__.py` | `__version__` (single source of truth for package version) |
| `session/` | Session record schema, JSONL store, state machine (v2) |
| `contract/` | Correctness contract generation and quality checking (v2) |
| `gates/` | Risk classification, gate catalog, selection, orchestration, result parsing (v2) |
| `retry/` | Failure taxonomy, retry brief, signal parsing, strategy, stop conditions (v2) |
| `noise/` | Dedup, retry suppression, FP memory, calibration (v2) |
| `runner/` | Top-level `run_session()` entry point, metrics collection (v2) |

## Key design decisions

- **No PyYAML dependency.** Policy files use a flat `key: value` format parsed by a custom 40-line parser. Unknown keys are silently dropped for forward compatibility.
- **No network connections.** All external communication goes through `git` and `claude` CLI subprocesses. Cold Eyes never opens sockets.
- **Fail-closed by default.** Infrastructure failures (timeout, parse error, missing CLI) produce a block decision in block mode. This is deliberate: a broken reviewer should not silently pass unsafe code.
- **Confidence filter is deterministic.** The LLM assigns confidence levels, but the filter is a simple threshold comparison — no probabilistic logic.
- **Override tokens are file-based with TTL.** One-time use, stored in `~/.claude/`, expire after N minutes. No persistent state beyond the token file.
