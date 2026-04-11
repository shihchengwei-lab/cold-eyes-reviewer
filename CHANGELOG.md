# Changelog

## v0.5.1 — README Architecture Clarification

- Flow diagram now shows `cold-review.sh` (guard checks) and `cold_review_engine.py` (all review logic) as two distinct layers.
- Files table reordered: engine listed first as core component.

## v0.5.0 — Phase 0 Closure

Closed remaining Phase 0 gaps from the product plan.

### New features

- **Truncation warning in block messages** — When diff exceeds token budget and files are skipped, block messages now show `⚠ 審查不完整：diff 超過 token 預算，N 個檔案未審查。` FinalOutcome includes `truncated` and `skipped_count` fields.
- **Explicit CLI parameters** — Engine accepts `--confidence` and `--language` arguments. Shell passes them explicitly instead of relying on environment variable inheritance.
- **History records confidence threshold** — Every history entry now includes `min_confidence` field.

### Changes

- **Helper build-prompt deduplication** — `build_prompt()` now delegates to engine's `build_prompt_text()`, with fallback to local logic if engine unavailable.
- **CHANGELOG backfilled** — Added v0.3.0 and v0.4.0 entries.

### Tests

98 tests (8 new: truncation visibility, history confidence, helper dedup).

## v0.4.0 — Confidence Hard Filter

Replaced soft prompt steering with deterministic confidence filtering.

### New features

- **Confidence hard filter** — `COLD_REVIEW_CONFIDENCE` env var (high / medium / low, default: medium). Issues below the threshold are dropped by Python code, not LLM interpretation. Predictable and testable.
- **Language env var** — `COLD_REVIEW_LANGUAGE` replaces profile.json's language field. Default: `繁體中文（台灣）`.
- **"Cold Eyes" hardcoded in prompt** — Name has semantic function (cold = uncompromising, eyes = scrutiny). Not configurable by design.

### Breaking changes

- **`cold-review-profile.json` deleted** — With stats removed, only name and language remained. Name is hardcoded; language moved to env var. File no longer needed.
- **RIGOR / PARANOIA stats removed from prompt** — Soft steering replaced by hard confidence filter. Prompt no longer contains `{statistics}` placeholder.

### Tests

90 tests (8 new: confidence filter + prompt assembly).

## v0.3.0 — Credibility Overhaul

Moved all review logic from shell to testable Python engine.

### New features

- **Python review engine** — `cold_review_engine.py` handles diff building, Claude CLI call, policy enforcement, and history logging. Shell reduced to thin orchestrator with guard checks only.
- **Infrastructure failure blocking** — Block mode now blocks on CLI errors, empty output, and parse failures (instead of silently passing). State: `infra_failed`.
- **Binary detection** — Untracked binary files are skipped instead of included in diff.
- **Truncation-aware prompt** — Prompt explains `[Cold Eyes: diff truncated...]` marker to the reviewer.
- **Token budget in engine** — `build_diff()` manages token budget internally with per-file truncation and skip tracking.

### Changes

- **Shell thinned** — `cold-review.sh` reduced from ~215 to ~95 lines. Only runs guard checks (off mode, recursion, lockfile, git repo) before delegating to engine.
- **Dead config removed** — `SNARK`, `PATIENCE`, personality fields removed from profile.json. Line budget (`MAX_LINES`) replaced with token budget (`MAX_TOKENS`) as primary setting.

### Tests

77 tests (33 new: engine policy, parsing, diff building, binary detection).

## v0.2.0 — Alpha

14-phase refactoring from "working prototype" to "trusted alpha."

### New features

- **Block policy graduation** — Issues now carry `severity` (critical / major / minor). Blocking is controlled by `COLD_REVIEW_BLOCK_THRESHOLD` (default: `critical`). Minor issues no longer block.
- **Ignore mechanism** — `.cold-review-ignore` file with fnmatch patterns. Built-in defaults skip lock files, build output, and minified files. Project-level patterns are additive.
- **Risk-sorted diff selection** — High-risk paths (auth, payment, db, migration, config, api) are prioritized within the token budget. New files get a boost. No more blind `head -n` truncation.
- **Override mechanism** — `COLD_REVIEW_ALLOW_ONCE=1` skips block once. Override is logged to history.
- **Structured failure visibility** — All exit paths (skip, fail, pass, block, override) are logged to history with explicit `state` field. Parse failures are marked `review_status: "failed"` and do not block.

### Schema changes

- Review JSON now includes `review_status`, `severity`, `confidence`, `category`, `file` fields
- History entries now include `version: 2`, `state`, `diff_stats` (files, lines, truncated)
- Old history entries (without `version` field) remain readable as v1

### New files

- `docs/alpha-scope.md` — Defines what is in and out of scope for this release
- `.cold-review-ignore` — Default ignore patterns
- `tests/` — pytest test suite (38 tests)
- `.github/workflows/test.yml` — GitHub Actions CI
- `CHANGELOG.md`

### Changes

- `cold-review-prompt.txt` — Simplified. Severity/confidence/category definitions added. Personality rhetoric removed. Policy is enforced by code, not prompt.
- `cold-review-helper.py` — Added `log-state`, `should-block`, `filter-files`, `rank-files` commands. `parse-review` now fills defaults for missing fields and returns `review_status: "failed"` on parse errors (instead of fake issues). `format-block` shows severity prefix. `log-review` writes v2 history format with `state` and `diff_stats`.
- `cold-review.sh` — Diff collection rewritten to filter → rank → per-file collection. All exit paths log state. Block decision uses `should-block` with threshold. Override check added.
- `README.md` — Rewritten. Honest about scope and limitations. Documents failure modes, adoption path, all new configuration options.

### Breaking changes

- Parse failures no longer emit fake issues or block. They set `review_status: "failed"` and `pass: true`.
- `should-block` replaces `check-pass` for block decisions. `check-pass` is retained for logging.
- History format v2 has additional fields. Tools reading history should check for `version` field presence.

## v0.1.0 — Initial Release

First working prototype. Shell-based Stop hook with Python helper, profile-based personality, and block/report modes.
