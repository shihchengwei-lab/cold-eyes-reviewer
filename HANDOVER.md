# Cold Eyes Reviewer — 交接文件

## 現況

- **版本：** v1.11.3（master，已 push）
- **分支：** master
- **測試：** 774 passed / 0 failed
- **部署：** 已同步 `~/.claude/scripts/`（清除舊 `cold_eyes/cold_eyes/` 巢狀殘留 + `cold_review_engine.py`）
- **版本訊號：**
  - `__init__.py` = 1.11.3
  - CHANGELOG = v1.11.3
  - GitHub description = 774 tests
  - tag = 待打
  - pytest = 774 passed

## 本次會話做了什麼（2026-04-13，Session 6 — Bug Fix Final + Deploy）

### 起點

接手 v1.11.2（`1a63896`），101 bugs 中 53 已修，48 remaining（1 major + 47 minor）。

### 完成內容

#### A. Bug Fix — v1.11.3（48 bugs fixed）

5 個平行 agent 分組修 bug（core v1、v2 modules、CLI+infra、tests、shell+evals+docs），再修最後 4 個收尾。

**Major（1）：**

| # | 檔案 | 修法摘要 |
|---|------|----------|
| #59 | `override.py` | TOCTOU race → `os.rename` 原子搶佔（concurrent review 不再雙 pass）|

**Minor — Production（25）：**

| # | 檔案 | 修法摘要 |
|---|------|----------|
| #14 | `session_runner.py` | post-loop dead code（`gates_running` → `retrying`）|
| #15 | `session_runner.py` | `_all_gates_passing` True → 走 passed 而非 failed_terminal |
| #31 | `retry/translator.py` | 移除 dead `fix_scope` 變數 |
| #34 | `retry/signal_parser.py` | traceback signals 依 file path 去重 |
| #47 | `context.py` | CJK 截斷改依 ASCII/non-ASCII 比例加權 |
| #48 | `config.py` | YAML `12_000` strip underscore 正確解析 |
| #49 | `risk_classifier.py` + `generator.py` | 逐檔 regex match（不再 join 跨路徑）|
| #50 | `orchestrator.py` | parser 只讀 stdout（不混 stderr）|
| #60 | `cli.py` | `--v2` 配非 run 子命令時 stderr 警告 |
| #61 | `cli.py` | `--regression-check` + `--save` 並用時警告 |
| #62 | `schema.py` | `pass=True` + critical/major issues → 修正為 False |
| #64 | `triage.py` | conftest/fixtures/mocks 歸類 `test_support` |
| #68 | `engine.py` | diff 截斷用 `min(max_tokens, max_input_tokens)` |
| #76 | `doctor.py` | `git_repo` 移出 critical_checks → env_warnings |
| #77 | `calibration.py` | 移除未使用的 `session_context` 參數 |
| #78 | `strategy.py` | abort threshold 統一為 `retry_count >= 3` |
| #86 | `claude.py` | 文件記錄 Windows orphan grandchild 限制 |
| #90 | `git.py` | pr-diff base 未 fetch 時顯示 hint |
| #91 | `type_defs.py` | `now_iso()` 改 `Z` 尾綴（與 v1 一致）|
| #92 | `engine.py` | `run()` 接受 `history_path` 參數 |
| #94 | `calibration.py` | per-finding try/except fallback |
| #99 | `engine.py` | input 組裝順序改為 diff→context→hints |
| #100 | `session/schema.py` | `add_event` 複製 data dict |
| R9#97 | `git.py` | truncation notice 預留空間 |

**Minor — Shell（5）：**

| # | 修法摘要 |
|---|----------|
| #17 | env var 展開統一用 `${VAR:-}` |
| #19 | PID write 加 error check |
| #46 | stdin 加 1MB size cap |
| #81 | JSON parser 加 extraction fallback |
| #93 | `stop_hook_active` 改 strict boolean check |

**Minor — Tests（7）：**

| # | 修法摘要 |
|---|----------|
| #20 | mock lambda 改 optional 第二參數 |
| #21 | mock review_status `"clean"` → `"completed"` |
| #35 | 加 `validate_brief()` 驗證 |
| #37 | 移除 dead outer patch |
| #84 | assert 改為 specific `"passed"` |
| #85 | gate count assert 改 `== len(list_gates())` |
| #101 | test mocks 加 `{"result":"..."}` wrapper |

**Minor — Evals & Docs（10）：**

| # | 修法摘要 |
|---|----------|
| #32 | severity check bare pass 加說明 |
| #36 | benchmark response 改 `.txt` 副檔名 |
| #79 | sweep 加 `"minor"` threshold（9 組合）|
| #80 | baseline.json 重生為 33 cases |
| #83 | SECURITY.md TTL 修正為 10 分鐘 |
| #95 | quality_report.json 欄位對齊實際輸出 |
| #96 | evaluation.md case 數更新為 33 |
| R9#98 | stress cases category 改 `"correctness"` |

**修改的檔案（38 files）：**

```
22 production + 7 test + 3 eval + 2 doc + 1 shell + 1 security doc
38 files changed, 409 insertions(+), 156 deletions(-)
```

#### B. Deploy 同步

`cp` repo → `~/.claude/scripts/`。清除舊殘留：
- `cold_eyes/cold_eyes/`（巢狀複製）
- `cold_eyes/__pycache__/`
- `cold_review_engine.py`（v1.0 遺物）

#### C. Repo 頁面對齊

- GitHub description：773 → 774 tests
- README：built-in ignore 加 `*.map`
- README：verify-install 改為 2 critical checks（git_repo 移至 env_warnings）

#### D. Push

3 commits 推送（`fce961c..c4c0bac`）：

```
3a73862 fix: 48 bug fixes — 101/101 complete (v1.11.3)
2d15876 docs(handover): update for Session 6
c4c0bac docs(readme): align with v1.11.3
```

---

## 累計修復統計

| 版本 | Commit | Bugs fixed | Tests |
|------|--------|-----------|-------|
| v1.11.1 | `5571e90` | 29（2 critical, 15 major, 12 minor）| 773 |
| v1.11.2 | `1a63896` | 24（12 major, 12 minor）| 774 |
| v1.11.3 | `3a73862` | 48（1 major, 47 minor）| 774 |
| **合計** | | **101 / 101** | |

---

## 架構

### v2 pipeline 流程

```
run_session(task, files)
  ├─ create_session()
  ├─ generate_contracts()          ← contract/generator.py
  ├─ check_quality()               ← contract/quality_checker.py
  ├─ classify_risk()               ← gates/risk_classifier.py
  ├─ build_gate_plan()             ← gates/selection.py
  │
  ├─ LOOP (max_retries):
  │   ├─ run_gates()               ← gates/orchestrator.py
  │   │   ├─ llm_review → engine.run() (v1 pipeline)
  │   │   └─ test_runner / lint_checker / ... (subprocess)
  │   │
  │   ├─ merge_duplicates()        ← noise/dedup.py
  │   ├─ suppress_seen()           ← noise/retry_suppression.py
  │   ├─ calibrate()               ← noise/calibration.py
  │   │
  │   ├─ if all gates passed → return "passed"
  │   ├─ if no results → return "failed_terminal"
  │   │
  │   ├─ translate()               ← retry/translator.py
  │   ├─ should_stop()             ← retry/stop.py
  │   ├─ select_strategy()         ← retry/strategy.py
  │   ├─ apply re_run_gates filter ← strategy output
  │   └─ if stop/abort → return "failed_terminal"
  │
  └─ return SessionRecord
```

### Session 狀態機

```
created → contract_generated → gates_planned → gates_running
                                                   ↓
                                     passed    gates_failed
                                                   ↓
                                              retrying → gates_running (loop)
                                                   ↓
                                              failed_terminal

任何非 terminal 狀態 → aborted
```

### 目錄結構（v2 新增）

```
cold_eyes/
  type_defs.py                    共用 TypedDict + helpers (generate_id, now_iso)
  session/
    schema.py                    SessionRecord create/validate
    store.py                     JSONL-based SessionStore（原子寫入）
    state_machine.py             VALID_TRANSITIONS + transition()
  contract/
    schema.py                    CorrectnessContract create/validate
    generator.py                 rule-based contract generation（逐檔 regex match）
    quality_checker.py           quality score + warnings
  gates/
    risk_classifier.py           session-level risk aggregation（逐檔 regex match）
    catalog.py                   gate registry (5 builtin gates)
    selection.py                 contract-driven + risk-escalation gate selection（llm_review 保證）
    orchestrator.py              sequential gate execution, wraps engine.run()（只讀 stdout）
    result.py                    gate-specific output parsers (pytest, ruff, llm_review)
  retry/
    taxonomy.py                  failure classification (11 categories)
    brief.py                     RetryBrief create/validate
    signal_parser.py             extract actionable signals from gate output（traceback 去重）
    translator.py                gate failures → retry brief
    strategy.py                  8 retry strategies + escalation logic（abort >=3 統一）
    stop.py                      5 stop conditions（stride-based progress check）
  noise/
    dedup.py                     (type, file, check) deduplication
    grouping.py                  anchor-based proximity + same-check clustering
    retry_suppression.py         suppress previously-seen findings（cumulative）
    fp_memory.py                 wraps v1 memory.py for v2 findings
    calibration.py               wraps v1 policy.calibrate_evidence() for v2（per-finding try/except）
  runner/
    session_runner.py            top-level run_session() entry point
    metrics.py                   collect_metrics() + aggregate_metrics()（aborted 排除分母）
```

---

## v1.11.1–v1.11.3 行為變化（下手者需注意）

| 改動 | 舊行為 | 新行為 |
|------|--------|--------|
| `max_retries` 語義 | `>=` check：3 → 3 total | `>` check：3 → 4 total（initial + 3 retries）|
| pass 判定 | noise 清空 + soft fail → pass | 只有 all gates pass 才 pass |
| 空 gates | `all([])=True` → pass | → `failed_terminal` |
| 未知 threshold | 預設 3（只擋 critical）| 預設 0（全擋）|
| 未知 confidence | 預設 2（medium）| 預設 0（最嚴格）|
| `fail-closed` + override | override 繞過 | 永不繞過 |
| `_parse_llm_review` | 讀 `outcome["review"]` → 0 findings | 讀 `outcome["issues"]` |
| `estimate_tokens` | `ascii // 4`（1-3 chars → 0）| `(ascii+3) // 4`（ceiling，≥1）|
| gate selection | `llm_review` 只在空 list 時 fallback | `llm_review` 永遠加入（若 available）|
| `input_remaining` 負數 | 靜默 skip context/hints | stderr 警告 |
| `review.py` 解析 | 只接受 `{"result":"..."}` wrapper | 同時接受 wrapped/unwrapped |
| `{"result": null}` | 靜默 pass | `pass: False` |
| history prune/archive | 直接 `open("w")` 覆寫 | write-to-temp-then-rename |
| `keep_entries=0` | 清空歷史 | raise ValueError |
| v2 session | 不寫 v1 history | 寫入 v1 history（model="v2-session"）|
| `pass_rate` 分母 | 含 aborted | 只含 passed + failed_terminal |
| `ttl_minutes ≤ 0` | 創建已過期 token | raise ValueError |
| `*.map` 檔案 | 送入 review | BUILTIN_IGNORE 排除 |
| override consume | read→delete TOCTOU race | `os.rename` 原子搶佔 |
| context 截斷 | `max_tokens * 2`（CJK 2x 過量）| ASCII/non-ASCII 加權比例 |
| diff 截斷上限 | 只看 `max_tokens` | `min(max_tokens, max_input_tokens)` |
| input 組裝順序 | hints→context→diff | diff→context→hints（符合 prompt）|
| `now_iso()` 格式 | `+00:00` | `Z`（與 v1 一致）|
| schema validation | `pass=True` + critical issues 通過 | 自動修正為 `False` |
| `_all_gates_passing` | stop → failed_terminal | stop → passed |
| orchestrator parser | stdout + stderr | 只讀 stdout |
| risk_classifier | `" ".join(files)` → 跨路徑匹配 | 逐檔 match |
| abort threshold | translator `>=3`、strategy `>3` | 統一 `>=3` |
| truncation notice | 不計 token | 預留空間 |
| triage fallback | conftest/fixtures → `"source"` | → `"test_support"` |
| verify-install | 3 critical checks（含 git_repo）| 2 critical checks（git_repo 移至 env_warnings）|

---

## 下次 Session 要做的事

### Bug 修復已完成

101/101 bugs from `cold-eyes-report.md` 已全部修復。

### 原有待辦（仍有效）

1. **E2E 驗證** — 在��實 repo 跑 `python cli.py run --v2`
2. **shell hook 啟用** — `cold-review.sh` 加 `--v2` flag
3. **補測試覆蓋** — `available_gate_ids=None` auto-detection、`engine_adapter` 實際使用
4. **部署已完成** — ~~`cp` 至 `~/.claude/scripts/`~~（Session 6 已同步）

---

## 環境變數

（v2 新增模組不引入新的環境變數，全部沿用 v1）

| 變數 | 預設 | 說明 |
|---|---|---|
| `COLD_REVIEW_MODE` | `block` | block / report / off（自動 lowercase）|
| `COLD_REVIEW_MODEL` | `opus` | deep review 的 model |
| `COLD_REVIEW_SHALLOW_MODEL` | `sonnet` | shallow review 的 model |
| `COLD_REVIEW_MAX_TOKENS` | `12000` | diff 的 token 預算 |
| `COLD_REVIEW_CONTEXT_TOKENS` | `2000` | context section 的 token 預算（0=停用）|
| `COLD_REVIEW_MAX_INPUT_TOKENS` | `max_tokens+context_tokens+1000` | 總 token 上限（0 或負數 ��� 用預設；負數時 stderr 警告）|
| `COLD_REVIEW_BLOCK_THRESHOLD` | `critical` | severity 門檻（自動 lowercase；未知值 → 全擋）|
| `COLD_REVIEW_CONFIDENCE` | `medium` | confidence 門檻（未知值 → 最嚴格）|
| `COLD_REVIEW_LANGUAGE` | `繁體中文（台灣）` | 輸出語言（sanitize：50 字上限）|
| `COLD_REVIEW_SCOPE` | `working` | diff 範圍（自動 lowercase）|
| `COLD_REVIEW_BASE` | 未設 | pr-diff scope 的 base branch |
| `COLD_REVIEW_TRUNCATION_POLICY` | `warn` | warn / soft-pass / fail-closed（自動 lowercase）|

## 長期事項（不可自行移除，需 user 確認）

- **v2 E2E 驗證未完成** — user 需在真實 repo 跑 `python cli.py run --v2`，然後檢查 `~/.claude/cold-review-sessions/sessions.jsonl` 確認 session 流程正確。每次 session 開頭應提醒 user 此事，直到 user 明確說測完、決定是否切為預設後才可移除本項。

## 注意事項

- v1 pipeline 有修改（engine.py 加了 `outcome["issues"]`、`.lower()`、cast、input_remaining 警告、`history_path` 參數等），但 `engine.run()` ���對外 contract 向後相容 — 新參數皆有預設值。
- v2 純 stdlib，無新增依賴。`pyproject.toml` 的 `include = ["cold_eyes*"]` 已自動涵蓋 sub-packages。
- Session store 用 JSONL（同 v1 history），路徑 `~/.claude/cold-review-sessions/sessions.jsonl`。原子寫入。
- history.py 的 prune/archive 現在都用 write-to-temp-then-rename（防 crash 資料遺失，但不防 concurrent write）。
- override.py 的 `consume_override` 現在用 `os.rename` 原子搶佔（防 concurrent review 雙 pass）。
- Gate catalog 目前 5 個 builtin gates，`llm_review` 永遠加入（若 available）。其餘 4 個 external gates 靠 subprocess（只讀 stdout，不混 stderr）。
- `max_retries` 語義 = actual retries after initial attempt。`max_retries=3` → 4 total runs。
- v2 session 結果現在寫入 v1 history（`model="v2-session"`），v1 stats/quality-report 可見。
- review.py 同時支援 Claude CLI wrapped `{"result":"..."}` 和 unwrapped 格式。
- Bug report 在 `C:\Users\kk789\Desktop\cold-eyes-report.md`（13 輪，101 bugs，**101 fixed**）。
- v2 task breakdown 原始文件在 `C:\Users\kk789\Downloads\cold-eyes-reviewer_v2_task_breakdown.md`。
- Deploy 目錄 `~/.claude/scripts/` 已於 Session 6 同步，清除了舊殘留（巢狀 cold_eyes、pycache、cold_review_engine.py）。
