# Changelog

## v1.11.2 — 24 bug fixes (platform, atomicity, robustness)

Second bug-fix batch from 101-bug report. 12 major, 12 minor.

### Major
- **#2** `engine.py` — input_remaining 負數時 stderr 警告（context/hints 被 skip）
- **#26** `gates/selection.py` — `llm_review` 永遠加入 selected gates（不只 fallback）
- **#51** `history.py` — archive 改原子寫入（write-to-temp-then-rename）
- **#52** `history.py` — `keep_entries < 1` 拋 ValueError（防清空歷史）
- **#55** `doctor.py` — subprocess 加 `encoding="utf-8"`
- **#56** `doctor.py` — 捕 `FileNotFoundError`（git 未安裝）
- **#57** `gates/orchestrator.py` — external gate subprocess 加 `encoding="utf-8"`
- **#71** `cli.py` — v2 session 結果寫入 v1 history
- **#87** `claude.py` — `os.unlink` 加 try/except OSError（Windows handle lock）
- **#88** `review.py` — 同時支援 wrapped/unwrapped Claude CLI 輸出格式
- **#89** `history.py` — prune 改原子寫入
- **#99** `memory.py` — `errors="replace"` 防 UnicodeDecodeError

### Minor
- **#6** `gates/result.py` — exit_code≠0 時不覆寫 status 為 pass
- **#11** `detector.py` — regex `[/\\s]` 修正為 `[/\\]`（不再誤匹 `views`）
- **#12** `memory.py` — 路徑 `\` → `/` 統一（Windows 混合分隔符）
- **#13** `history.py` — `makedirs("")` 防護
- **#29** `override.py` — `ttl_minutes ≤ 0` 拋 ValueError
- **#33** `runner/metrics.py` — aborted sessions 不影響 pass_rate 分母
- **#63** `policy.py` — 未知 confidence 預設 0（最嚴格）
- **#67** `constants.py` — BUILTIN_IGNORE 加 `*.map`
- **#69** `review.py` — `{"result": null}` 不再靜默 pass
- **#72** `history.py` — archive 目錄 makedirs 無條件執行
- **#73** `engine.py` — hint tokens 計入 token_count
- **#75** `gates/result.py` — ruff parser 用 `[A-Z]\d{3,4}` regex

15 production files, 2 test files changed. 774 tests (+1), 0 failures.

## v1.11.1 — 29 bug fixes (data boundary + cross-module contracts)

Bug hunt rounds 1-13 累計 101 bugs；本版修復 29 個（2 critical, 15 major, 12 minor）。

### Critical
- **#22** `engine.py` + `gates/result.py` — `outcome["issues"]` 缺失 → parser 0 findings；加 key + 改讀 top-level issues
- **#38** `prompt.py` — language 注入；`_sanitize_language()` 50 字上限 + 去控制字元 + allowlist

### Major
- **#1** `git.py` — 截斷後 `estimate_tokens` 重算，CJK fallback
- **#3** `retry/stop.py` — no-progress 改用 gate 數量做 stride
- **#4** `session_runner.py` — noise 清空 findings 不再假 pass
- **#5** `retry/stop.py` — `>=` → `>` 修 off-by-one（max_retries 語義 = actual retries）
- **#23** `engine.py` — mode/threshold/scope/truncation_policy `.lower()`
- **#24** `cli.py` — v2 path 加 `filter_file_list()`
- **#25** `session/store.py` — write-to-temp-then-rename 原子寫入
- **#27** `policy.py` — 未知 threshold 預設 0（最嚴格）
- **#30** `noise/grouping.py` — proximity 比對 anchor 非 last
- **#41** `engine.py` — `max_input_tokens=0` 正確 fallback
- **#42** `filter.py` — `errors="replace"` 防 UnicodeDecodeError
- **#44** `session_runner.py` — retry 使用 `re_run_gates`
- **#45** `session_runner.py` — `previous_findings` 跨 iteration 累積
- **#53** `policy.py` — `fail-closed` 不被 override 繞過
- **#54** `engine.py` — policy 值 cast 加 try/except
- **#58** `git.py` — untracked files 用 repo root 絕對路徑
- **#70** `session_runner.py` — 空 results → `failed_terminal`
- **#97** `noise/grouping.py` — 無行號 findings 不 cluster
- **#98** `gates/result.py` — JSON null → `or ""` 防 None 傳播

### Minor
- **#10** `git.py` — ceiling division `(n+3)//4`
- **#16** `noise/dedup.py` — 第一個 message 也入 supporting
- **#28** `session/store.py` — corrupt JSONL skip 不 crash
- **#65** `engine.py` — 空 diff 用 `effective_model`
- **#74** `noise/calibration.py` — 保留 `fp_match_count`
- **#82** `noise/calibration.py` — 不再 double downgrade
- **#94** `noise/calibration.py` — `calibrate_evidence` 加 try/except fallback

### Behavior changes
| 改動 | 舊 | 新 |
|------|----|----|
| `max_retries` 語義 | `>=`：3 → 3 total | `>`：3 → 4 total（initial + 3 retries） |
| pass 判定 | noise 清空 + soft fail → pass | all gates pass 才 pass |
| 空 gates | `all([])=True` → pass | → `failed_terminal` |
| 未知 threshold | 預設 3 | 預設 0（全擋） |
| `fail-closed` + override | override 繞過 | 永不繞過 |

13 production files, 7 test files changed. 773 tests, 0 failures.

## v1.11.0 — v2 activation path

- **`--v2` CLI flag** — `cli.py run --v2` 走 `run_session()` pipeline，opt-in。v1 預設路徑不變。
- **持久化** — v2 session 結束後自動寫入 `SessionStore`（`~/.claude/cold-review-sessions/sessions.jsonl`）。
- **scope 解析對齊** — `_run_v2` 用 `_resolve(CLI > env > policy > default)`，與 `engine.run()` 一致。
- **shell hook 相容** — 輸出保留 `action`/`display`/`reason`，`cold-review.sh` 無需修改。
- **DEPLOY_FILES** — 加入 31 個 v2 檔案（6 sub-packages 全覆蓋）。
- 773 tests，0 failures。

## v1.10.0 — Correctness session engine (v2)

v1 pipeline 完全未修改。v2 在上層新增 session engine，包裝 `engine.run()` 為 `llm_review` gate。

- **6 個 sub-package** — `session/`, `contract/`, `gates/`, `retry/`, `noise/`, `runner/`
- **session engine** — `run_session(task, files)` 驅動 contract → gate → noise → retry loop
- **gate orchestration** — 5 builtin gates（llm_review, test_runner, lint_checker, type_checker, build_checker）
- **retry loop** — failure taxonomy（11 categories）、8 strategies、5 stop conditions
- **noise suppression** — dedup、retry suppression、FP memory、calibration
- **debug review** — 修 `types.py` stdlib shadow（→ `type_defs.py`）、`_parse_ruff` Windows path、4 lint issues、dead code
- 773 tests（+242），0 failures。純 stdlib，無新依賴。

## v1.9.2 — README factual alignment + input budget cap

### Total input budget enforcement

diff + context + detector hints 各自有獨立預算（或無預算），拼接後總量無上限，大 diff 可觸發 "Prompt is too long"。

- **`max_input_tokens`** — 新增 total token cap，控制所有送入 model 的 stdin 內容（diff + context + hints）。預設 = `max_tokens + context_tokens + 1000`。
- **預算分配** — diff 先佔預算，context 拿 `min(context_tokens, 剩餘)`，detector hints 剩餘夠就加、不夠整段丟棄（`hints_dropped=True`）。
- **設定方式** — CLI `--max-input-tokens`、env `COLD_REVIEW_MAX_INPUT_TOKENS`、policy file `max_input_tokens`。
- 531 tests (+6)。

### README factual alignment

README described v1.4-era behavior. Updated 6 areas to match v1.9 reality:

- **Intro** — "zero-context" → "cold-read". Deep reviews now described as seeing diff + context + detector hints; shallow reviews as diff-only.
- **Pipeline diagram** — 3-step sketch → 10-step numbered pipeline with triage, context, detector, FP memory, and calibration.
- **Output example** — added evidence-bound fields (evidence, what_would_falsify_this, suggested_validation, abstain_condition) with explanations of automatic downgrade rules.
- **Install command** — added missing `cold-review-prompt-shallow.txt`.
- **Eval numbers** — 24 cases / 5 categories → 33 cases / 7 categories (3 locations).

## v1.9.1 — Prompt self-disclosure + deploy fix

- **Deep prompt rewritten** — removed "零 context" / "只看到 git diff" claims. Prompt now explicitly describes the 3 input types the model may receive: git diff, context block (v1.6.0+), detector hints (v1.8.0+). Each described with source, purpose, and limitations.
- **GitHub About updated** — "Zero-context" → "Cold-read". Shallow prompt unchanged (shallow path truly has no context).
- **Full deploy sync** — previous deploys only copied changed files, leaving stale modules (e.g. prompt.py from pre-v1.6.0). All 22 DEPLOY_FILES now synced.

## v1.9.0 — False-Positive Memory + Confidence Calibration (Phase 5)

Override history now feeds back into calibration: recurring false-positive patterns are automatically detected and used to downgrade confidence on matching issues. Category-level confidence caps prevent chronically noisy categories from producing high-confidence blocks. 525 tests (was 469).

### FP pattern extraction (WP1)

- **`cold_eyes/memory.py`** — new module. `extract_fp_patterns(history_path, min_count, last_days)` scans override history for recurring category, path, and check patterns.
- **`match_fp_pattern(issue, fp_patterns)`** — checks if an issue matches 0-3 known FP pattern types (category, path, check prefix).

### Calibration integration (WP2)

- **Rule 3 in `calibrate_evidence()`** — issues matching FP patterns are downgraded: -1 confidence per match type (max -2 downgrades). Issues annotated with `fp_match_count`.
- **Engine wiring** — `extract_fp_patterns()` runs after model parse, before `apply_policy()`. FP memory stats (`fp_memory_overrides`, `fp_memory_patterns`) added to outcome.

### Per-category confidence baselines (WP3)

- **`compute_category_baselines(fp_patterns)`** — categories with override ratio >= 0.5 are capped at "low"; >= 0.3 at "medium".
- **Rule 4 in `calibrate_evidence()`** — applies category caps after FP match downgrades. Caps never upgrade confidence.

### Eval (WP4)

- **3 new eval cases** — `fp-memory-known-pattern` (pass: double FP match demotes to low), `fp-memory-category-cap` (pass: high-ratio cap), `fp-memory-no-match` (block: real issue unaffected).
- **33/33 deterministic**, regression check pass.

### Tests

- 525 tests (+56): FP extraction (14+13 backslash), FP matching (13), FP calibration rules (12+6), category baselines (7+1), eval FP cases (5).

## v1.8.0 — State/Invariant Detector + Repo-Specific Focus (Phase 4)

Two detectors added to the deep review path: a fixed state/invariant detector and a repo-type-adaptive focus selector. Both are regex-based pre-model analysis that enrich the prompt with targeted hints. 469 tests (was 421).

### State/invariant detector (WP1)

- **`cold_eyes/detector.py`** — new module. `detect_state_signals(diff_text)` scans diff for 5 pattern types: state_check, transition_call, fsm_pattern, rollback_pattern, state_assignment.
- **Hint injection** — when state signals are found, detector hints are prepended to the diff text, guiding the model to check for missing pre-checks, incomplete transitions, missing rollback, and broken validation order.
- **Pattern ordering** — more specific patterns match first (state_check before state_assignment) to avoid false classification.

### Repo-specific detector (WP2)

- **`classify_repo_type(files)`** — classifies changed files into 5 repo types: web_backend, sdk_library, db_data, infra_async, general.
- **Focus profiles** — each repo type maps to a secondary detector focus with 3 targeted checks:
  - web_backend → auth / permission (bypass, authorization gap, missing middleware)
  - sdk_library → contract break (breaking API, missing deprecation, type contract)
  - db_data → migration / persistence (schema drift, missing reverse migration, serialization)
  - infra_async → concurrency / staleness (race condition, stale data, error handling)
- **`build_detector_hints(diff_text, files)`** — combines state signals + repo focus into a single hint block.

### Engine integration

- **Deep path only** — detectors run after context retrieval, before prompt. Shallow/skip paths unaffected.
- **Outcome fields** — `detector_repo_type`, `detector_focus`, `state_signal_count` added to deep review outcomes when hints are present.

### Eval (WP3)

- **3 new eval cases** — `tp-state-missing-precheck` (block), `tp-partial-state-update` (block), `fn-legitimate-state-change` (pass).
- **30/30 deterministic**, regression check pass.

### Tests

- 469 tests (+48): state signal detection (22), repo classification (11), focus profiles (6), hint integration (9).

## v1.7.0 — Evidence-Bound Claim Schema (Phase 3)

Review output is now auditable: each issue carries an evidence chain, falsifier, and optional abstain condition. Issues without evidence or with hidden-context assumptions are automatically downgraded. 421 tests (was 400).

### Evidence-bound issue schema (WP1)

- **New issue fields** — `evidence` (list of strings), `what_would_falsify_this`, `suggested_validation`, `abstain_condition`. All optional (backward compatible).
- **Deep prompt updated** — requires evidence chains. Issues without evidence should lower confidence.
- **Parse defaults** — `parse_review_output()` sets empty defaults for all four fields.
- **Schema validation** — type checks on new fields if present (evidence must be list, others must be string).

### Abstain / falsifier calibration (WP2)

- **`calibrate_evidence()`** in policy.py — runs before confidence filter. Two rules:
  1. `confidence=high` + no evidence → downgraded to `medium`.
  2. Non-empty `abstain_condition` → confidence -1 level (high→medium, medium→low).
- **Stacking** — both rules apply in order. high + no evidence + abstain → low.
- **Backward compatible** — old-format responses (no evidence fields) get high→medium downgrade but still pass default medium confidence filter.

### Eval (WP3)

- **3 new eval cases** — `evidence-with-chain` (block), `evidence-abstain-demotes` (pass), `evidence-backward-compat` (block).
- **27/27 deterministic**, regression check pass (baseline v1.4.1 compatible).

### Bugfixes (pre-Phase 3)

- **Triage regex narrowed** — `secrets_privacy` no longer matches `environment.ts`, `keyboard.py`, `tokenizer.py`. `async_concurrency` no longer matches `service-worker.js`. Negative lookaheads exclude common non-risk filenames.
- **CJK token estimation** — `estimate_tokens()` replaces `len(text.encode("utf-8")) // 4`. ASCII: ~4 chars/token, non-ASCII: ~1 char/token. Fixes systematic undercount for Chinese text.
- **README env var table** — added `COLD_REVIEW_SHALLOW_MODEL` and `COLD_REVIEW_CONTEXT_TOKENS`.
- **Shell guard consistency** — engine-not-found guard now emits block JSON in block mode (matches Python-not-found guard).

### Tests

- 421 tests (+39): evidence schema (6), parse defaults (2), calibrate_evidence (9), policy integration (4), regex false positives (12), token estimation (6).

## v1.6.0 — Shallow Differentiation + Context Retrieval (Phase 2)

Shallow path now uses a lighter model and critical-only prompt. Deep path gets git-history context injection. 382 tests (was 346).

### Shallow differentiation (WP1)

- **Shallow prompt** — `cold-review-prompt-shallow.txt`: critical-only, shorter template. Shallow reviews skip minor/major checks.
- **Lighter model for shallow** — `COLD_REVIEW_SHALLOW_MODEL` env var (default: `sonnet`). Shallow reviews use a lighter model; deep reviews keep the main model.
- **`build_prompt_text(depth=)`** — prompt.py now selects template by depth. Fallback text covers both shallow and deep.
- **Engine differentiation** — `review_depth=shallow` now uses shallow prompt + shallow model instead of falling through to deep.

### Context retrieval (WP2)

- **`cold_eyes/context.py`** — new module. `build_context(files)` extracts recent commit messages and co-changed files from git history.
- **Deep path context injection** — context prepended to diff text before model call. Deep reviews now see git history alongside the diff.
- **`COLD_REVIEW_CONTEXT_TOKENS`** env var (default: 2000). Token budget for context section. Set to 0 to disable.
- **Outcome field** — `context_summary` added to deep review outcomes when context is present.

### Triage stats (WP3)

- **`by_review_depth`** in quality-report — triage distribution (skip/shallow/deep counts) now included in quality report output.
- **Triage safety tests** — 9 new tests confirming skip doesn't miss real problems (config with secrets keywords, mixed file types, risk category override).

### Configuration

- **New env vars** — `COLD_REVIEW_SHALLOW_MODEL`, `COLD_REVIEW_CONTEXT_TOKENS`.
- **New CLI flags** — `--shallow-model`, `--context-tokens`.
- **Policy file keys** — `shallow_model`, `context_tokens` added to `.cold-review-policy.yml`.

### Tests

- 382 tests (+36): shallow prompt (10), engine model selection (3), context retrieval (9), engine context integration (3), triage safety (9), quality-report triage (2).

## v1.5.0 — Cost-Effective Triage (Phase 1)

Skip / shallow / deep three-tier review depth triage. Diffs that don't need model review (docs, generated, config-only) are skipped at zero cost. 346 tests (was 306).

### Triage

- **`classify_file_role(path)`** — classifies files into 6 roles: test, docs, config, generated, migration, source. Pattern-based, no I/O.
- **`classify_depth(files)`** — rule-based depth classification: skip (docs/generated/config without secrets keywords), shallow (test-only, placeholder for future lighter model), deep (risk category match, source, migration).
- **8 risk categories** — auth_permission, state_invariant, migration_schema, persistence, public_api, async_concurrency, secrets_privacy, cache_retry. Structured replacement for triage decisions (existing `RISK_PATTERN` kept for file ranking).

### Engine

- **Triage step** inserted between rank and build_diff: `collect → filter → rank → triage → build_diff → prompt → model → parse → policy`.
- **Skip path** — `review_depth=skip` returns immediately, no diff build, no model call.
- **Shallow placeholder** — `review_depth=shallow` currently falls through to deep (hook for future lighter model/prompt).
- **Outcome fields** — `review_depth` and `why_depth_selected` added to all engine outcomes.
- **History records** — `review_depth` field added to history JSONL entries.

### Tests

- 346 tests (+40): file role classification (23), depth classification (15), engine triage integration (2).

## v1.4.1 — Trust Engineering Phase 2

Regression gate, baseline management, CI eval integration. 306 tests (was 303).

### Evaluation

- **`regression_check()`** — compares current deterministic eval against a saved baseline. Detects regressions (previously matching cases that now fail). Returns structured result with `regressed`, `regressions`, `cases_added`, `cases_removed`.
- **`--regression-check <baseline.json>`** — CLI flag runs regression check, exits 1 on regression, 0 on success.
- **`evals/baseline.json`** — canonical baseline committed to repo (24/24 pass at critical/medium).

### CI

- **Eval steps in CI** — `test.yml` now runs deterministic eval and regression check after pytest. No model calls needed.

### Documentation

- **Baseline management** in `docs/evaluation.md` — update workflow, when to update, regression check usage.

### Tests

- 306 tests (+3): regression check — baseline vs self (1), action change without match change (1), regression detected with high confidence (1).

## v1.4.0 — Trust Engineering Phase 1

Eval corpus expansion (14→24 cases, 3→5 categories), structured eval pipeline, trust documentation. 303 tests (was 297).

### Evaluation

- **Eval corpus expanded** — 24 cases across 5 categories: true_positive (8), acceptable (4), false_negative (3), stress (5), edge (4). Added path traversal, eval injection, CJK comments, unicode identifiers, empty response, config-only changes, all-minor issues.
- **manifest.json** — case index with per-category counts and `validate_manifest()` integrity check.
- **schema.md** — formal case file format definition.
- **Structured eval pipeline** — `_make_report()` wraps all eval output with `cold_eyes_version`, `timestamp`, `eval_schema_version`. `format_markdown()` renders case tables and category summaries. `save_report()` persists to `evals/results/` as JSON and/or markdown. `compare_reports()` diffs two reports (cases added/removed/changed, F1 delta).
- **CLI eval flags** — `--save` (persist report), `--format json|markdown|both`, `--compare <path>` (diff against previous report).

### Documentation

- **trust-model.md** — capability boundaries, trust attributes, known gaps.
- **assurance-matrix.md** — per-category detection ability, FP/FN direction, scope limits.
- **SECURITY.md** — expanded trust boundaries (6 sections + attack surface table).
- **roadmap.md** — rewritten as four-stage trust engineering plan.

### Tests

- 303 tests (+6): report metadata (2), markdown formatting (2), report comparison (1), report saving (1).

## v1.3.1 — Phase Report Hardening

Third-party audit fixes: shell fail-closed, token estimation, config guard, dedup robustness. 289 tests (was 288).

### Fixes

- **Token estimation accuracy** — `len(text) // 4` → `len(text.encode("utf-8")) // 4`, more accurate for CJK diffs
- **Shell fail-closed on missing python** — resolves `python3`/`python`; block mode emits block decision if neither found
- **Shell guard ordering** — python detection moved after off-mode guard (off mode doesn't need python)
- **Shell quoting** — `$PYTHON_CMD` quoted in all usage sites
- **Config parser line limit** — counts only non-blank non-comment lines; warns on stderr instead of silent discard
- **History prune dedup** — `id()`-based identity replaced with `json.dumps` content hash
- **Removed `call_claude()`** — dead legacy wrapper with no external callers
- **README logging claim** — corrected "all states logged" to "engine-level exits logged"

### CI

- **Release workflow parity** — added ruff + shellcheck to `release.yml` (matches `test.yml`)

## v1.3.0 — Governance & Polish

Project governance, CI coverage gate, CLI version flag, actionable diagnostics. 289 tests (was 283).

### Governance

- **CONTRIBUTING.md** — development setup, code style, commit convention, deployment model
- **SECURITY.md** — vulnerability disclosure policy, scope, trust boundaries
- **Issue templates** — bug report and feature request forms (`.github/ISSUE_TEMPLATE/`)
- **PR template** — `.github/PULL_REQUEST_TEMPLATE.md` with checklist
- **Version policy** — `docs/version-policy.md` documents SemVer rules and signal alignment
- **Support policy** — `docs/support-policy.md` documents tested Python/OS/shell matrix
- **Roadmap** — `docs/roadmap.md` with priorities and explicit out-of-scope list

### Diagnostics

- **`--version` flag** — `python cli.py --version` prints version string
- **Actionable doctor messages** — all failure messages now include `Fix:` instructions with specific remediation steps
- **Troubleshooting guide** — `docs/troubleshooting.md` with 8 problem/solution pairs
- **Failure modes doc** — `docs/failure-modes.md` with state machine, infra failure taxonomy, truncation analysis

### Fixes

- **Skip on zero file_count** — engine now skips when all file diffs are empty (file_count=0), preventing false `infra_failed` blocks from empty Claude responses
- **Token estimation accuracy** — `len(text) // 4` → `len(text.encode("utf-8")) // 4`, more accurate for CJK diffs (3 UTF-8 bytes ≈ 1 token)
- **Shell fail-closed on missing python** — `cold-review.sh` resolves `python3`/`python` before use; if neither found, block mode emits block decision, report mode warns
- **Shell guard ordering** — python interpreter detection moved after off-mode guard (off mode doesn't need python)
- **Shell quoting** — `$PYTHON_CMD` quoted in all 3 usage sites to prevent word-split
- **Config parser line limit** — counts only non-blank non-comment lines (was total lines); warns on stderr when exceeding 50 instead of silent discard
- **History prune dedup** — `id()`-based object identity replaced with `json.dumps` content hash (robust across refactors)
- **Removed `call_claude()` legacy wrapper** — dead code, no external callers
- **README logging claim** — corrected "all states logged" to "engine-level exits logged" (shell guard skips are not logged)

### CI

- **Coverage in CI** — `pytest-cov` with 75% threshold (actual: 82%), coverage report in test output
- **Release workflow** — `.github/workflows/release.yml` runs tests, ruff, shellcheck, and verifies tag-to-`__version__` alignment before creating GitHub Release
- **Release checklist updated** — coverage gate and release workflow steps added

### Documentation

- **Architecture doc** — `docs/architecture.md` with layer diagram, data flow, module responsibilities, design decisions

## v1.2.0 — Evidence & Controls

5-phase credibility push: evaluation framework, risk controls, governance docs. 283 tests (was 234).

### Evaluation (Phase 2)

- **Eval framework** — 14 eval cases (6 true positive, 4 acceptable, 4 stress) with deterministic, benchmark, and sweep modes.
- **Threshold sweep** — Compares precision/recall/F1 across threshold x confidence combinations. Data confirms default `critical/medium` achieves F1=1.0.
- **`eval` subcommand** — `python cli.py eval --eval-mode deterministic|benchmark|sweep`.

### Risk controls (Phase 3)

- **Truncation policy** — New `truncation_policy` setting: `warn` (default, unchanged behavior), `soft-pass` (force pass when truncated and no issues), `fail-closed` (block if any files unreviewed).
- **Coverage visibility** — Review outcomes now include `reviewed_files`, `total_files`, `coverage_pct`.
- 25 new risk control tests (truncation policy, config resolution, state reachability).

### Governance docs (Phase 4)

- **History schema docs** — `docs/history-schema.md` with JSONL v2 field reference, examples per state, migration notes.
- **Tuning playbook** — `docs/tuning.md` with diagnostic workflow and threshold adjustment guide.
- **Sample artifacts** — 5 sample JSON files in `docs/samples/`.

### Agent-native polish (Phase 5)

- **`verify-install` subcommand** — Machine-readable install check (3 critical checks → ok/fail JSON).
- **Agent setup guide** — `docs/agent-setup.md` with 5-step installation and troubleshooting.

### Release discipline (Phase 1)

- **GitHub Release** — v1.1.0 now has a proper GitHub Release with notes.
- **Release checklist** — `docs/release-checklist.md`.

## v1.1.0 — Trust & Maturity

9-patch quality push (P0 trust, P1 publishability, P2 long-term ops). 234 tests (was 197).

### Trust (P0)

- **Shell fail-closed** — Empty output, invalid JSON, and missing action field no longer silently pass. Block mode emits infra failure decision; report mode warns to stderr.
- **Review state constants** — All 6 states (`passed`, `blocked`, `overridden`, `skipped`, `infra_failed`, `reported`) defined once in `constants.py`, consumed everywhere. No more hardcoded strings.
- **Shell parser integration tests** — 12 new tests extract and run the inline parser from `cold-review.sh` with controlled inputs.

### Publishability (P1)

- **`pyproject.toml`** — Package metadata, `cold-eyes` CLI entry point, ruff lint config.
- **`install.sh` / `uninstall.sh`** — Scripted deploy and removal.
- **`init` subcommand** — Creates default `.cold-review-policy.yml` and `.cold-review-ignore` in current repo.
- **`doctor --fix`** — Auto-repairs safe issues (e.g. removes legacy helper).
- **CI matrix** — GitHub Actions tests on 3 OS (ubuntu, macos, windows) x 2 Python (3.10, 3.12) + ruff lint + shellcheck.
- **Version bump** — `__version__` set to `1.1.0`.

### Long-term ops (P2)

- **`history-prune`** — Remove old entries by `--keep-days` or `--keep-entries`.
- **`history-archive`** — Move entries before a date to a separate archive file.
- **Formal review schema** — `cold_eyes/schema.py` defines required fields, valid values, and `validate_review()`. Parser now attaches `validation_errors` to malformed output. 16 schema regression tests.
- **`quality-report`** — Block rate, override rate, infra failure rate, top noisy paths, top issue categories.

## v1.0.0 — Stable Release

Remove deprecated `helper.py` (shell no longer uses it). No functional changes from v0.11.0. This version marks API stability: history JSONL v2 schema, CLI subcommands, env vars, policy file keys, and hook JSON output are now stable.

197 tests (5 helper tests removed with the module).

## v0.11.0 — Personal Hardening

9-patch hardening to make block mode trustworthy for daily use. 202 tests (was 162).

### Breaking changes

- **`git_cmd()` raises on failure** — Returns are now success-only; non-zero exit raises `GitCommandError`. No more silent pass-through on git errors.
- **`build_diff()` returns dict** — Replaces 5-tuple with dict containing `partial_files`, `skipped_budget`, `skipped_binary`, `skipped_unreadable`.
- **`adapter.review()` returns `ReviewInvocation`** — Captures `stdout`, `stderr`, `exit_code`, `failure_kind`. Backward-compatible tuple destructuring via `__iter__`.
- **Report-mode infra state renamed** — `"failed"` → `"infra_failed"` (consistent across block/report modes).
- **`COLD_REVIEW_MAX_LINES` removed from shell** — Use `COLD_REVIEW_MAX_TOKENS` only.
- **Shell lock mechanism** — Changed from plain file to `mkdir`-based atomic lock at `~/.claude/.cold-review-lock.d/`.

### New features

- **One-time override token** — `python cli.py arm-override --reason <reason>` creates a file-based token consumed on next block. Replaces env var `ALLOW_ONCE` (deprecated, still works with warning).
- **Typed git failures** — `GitCommandError` and `ConfigError` exceptions. `pr-diff` without `--base` raises `ConfigError` instead of silently returning empty.
- **Rich diff metadata** — `partial_files` (cut mid-content), `skipped_binary`, `skipped_unreadable`, `skipped_budget` tracked separately. `truncated=True` when any is non-empty — fixes bug where last file cut in half was not flagged.
- **Diagnosable infra failures** — `ReviewInvocation` captures stderr. History records `failure_kind` (`timeout`, `cli_not_found`, `cli_error`, `empty_output`) and `stderr_excerpt`.
- **Language-aware block labels** — `format_block_reason()` uses English labels (Check/Verdict/Fix) when language is not Chinese.
- **Block reason shows file + line** — `[CRITICAL] auth.py (~L42)` instead of just `[CRITICAL] (~L42)`.
- **Effective pass after filter** — Report mode uses `len(filtered_issues) == 0` instead of model's raw `pass` field.

### Shell rewrite

- `cold-review.sh` reduced to pure shim (~100 lines): guards + invoke CLI + translate JSON
- Removed: `helper.py` dependency, `log_state()` function, `MAX_LINES` conversion, direct `claude -p` call
- `parse-hook` inlined as python one-liner
- Atomic `mkdir` lock with stale PID detection and single retry

### Doctor improvements

3 new checks (total 11):
- `legacy_helper` — detects `cold-review-helper.py` in scripts dir (split-brain)
- `shell_version` — detects legacy patterns in `cold-review.sh`
- `legacy_env` — detects `COLD_REVIEW_MAX_LINES` still set

`DEPLOY_FILES` expanded from 5 to 16 (complete package).

### Tests

202 tests (+40): git failures 5, ReviewInvocation 5, override token 8, diff metadata 5, policy state machine 7, doctor 4, shell integrity 4, misc 2.

## v0.8.0 — Package Restructure

Monolithic `cold_review_engine.py` (739 lines) split into `cold_eyes/` package (12 modules). Helper duplication eliminated.

### Breaking changes

- **Deploy command changed:** `cp -r cold_eyes/ cold-review.sh cold-review-prompt.txt ~/.claude/scripts/`
- **CLI entry point moved:** `python cold_eyes/cli.py` replaces `python cold_review_engine.py`
- **Legacy files removed:** `cold_review_engine.py` and `cold-review-helper.py` deleted

### Architecture

- `cold_eyes/` package: constants, git, filter, prompt, claude, review, policy, history, doctor, engine, cli, helper (12 modules)
- Helper consolidated from 12 commands to 2 (`parse-hook`, `log-state`) — the only ones the shell actually calls
- All shared constants in `cold_eyes/constants.py` — single source of truth
- No circular dependencies: constants → git/filter/review → policy/history → engine → cli

### Tests

110 tests (engine 95 + helper 5 + shell smoke 10). Helper test count reduced from 42 to 5 because engine tests now cover all previously-duplicated logic.

## v0.7.0 — Phase 1.4 Feedback Loop

### New features

- **Override reason tracking** — `COLD_REVIEW_OVERRIDE_REASON` env var records why a block was overridden. Stored in history as `override_reason` field on `state: "overridden"` entries. Free-text; suggested values documented (false_positive, acceptable_risk, unclear, infrastructure).
- **Override hint in block messages** — Block messages now show how to override with a reason: `COLD_REVIEW_ALLOW_ONCE=1 COLD_REVIEW_OVERRIDE_REASON='<reason>'`.
- **`aggregate-overrides` command** — `python cold_review_engine.py aggregate-overrides` summarises override patterns from history (total count, reason breakdown, recent entries).

### Fixes

- **`line_hint` marked as approximate** — Block messages now display line hints with `~` prefix (e.g., `(~L42)`) to indicate they are estimates. README updated with guidance to verify before acting in block mode.
- **`.cold-review-ignore` documentation** — README now lists all 12 built-in ignore patterns, explains that `.cold-review-ignore` is a per-repo file (not deployed to scripts/), and clarifies how per-repo patterns layer on top of built-in patterns.
- **`schema_version` bump rules** — README now defines when `schema_version` is bumped (breaking changes only) and when it is not (optional field additions).

### Tests

152 tests (17 new: override reason 8, history override 3, aggregation 3, helper 2, README 1).

## v0.6.0 — Phase 1 Alpha

Phase 1 implementation based on the productization roadmap. Five features targeting single-developer daily use.

### New features

- **`doctor` command** — `python cold_review_engine.py doctor` checks environment health: Python, Git, Claude CLI, deploy files, settings.json hook config, git repo status, and .cold-review-ignore. Returns structured JSON report with ok/fail/info status per check.
- **Diff scope control** — New `--scope` parameter (`working`/`staged`/`head`) and `COLD_REVIEW_SCOPE` env var. `staged` reviews only `git diff --cached`; `head` reviews `git diff HEAD`. Default `working` preserves existing behavior.
- **`line_hint` in issues** — Issues now include a `line_hint` field (e.g., `"L42"` or `"L42-L50"`) derived from diff hunk headers. Displayed in block messages as `[CRITICAL] (L42)`. Empty string when uncertain.
- **`schema_version`** — Review output and history entries now carry `schema_version: 1` for forward compatibility.

### Documentation

- **Strategy presets** — README documents 5 preset configurations (Conservative/Standard/Strict/Aggressive/Observe) with env var examples.
- **`COLD_REVIEW_SCOPE`** added to environment variables table.

### Tests

135 tests (37 new: doctor 11, scope 8, presets 1, line_hint 7, schema_version 10).

## v0.5.2 — CHANGELOG Backfill + Helper Description Fix

- CHANGELOG backfilled v0.5.0 and v0.5.1.
- Helper description changed from "Legacy shell interface" to "Shell-facing utilities".

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
