# Changelog

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
