# Cold Eyes Reviewer — 交接文件

## 現況

- **版本：** v1.11.1（master，已 commit）
- **分支：** master
- **測試：** 773 passed / 0 failed
- **部署：** 待同步 `~/.claude/scripts/`
- **版本訊號：**
  - `__init__.py` = 1.11.1
  - CHANGELOG = v1.11.1
  - tag = 待打
  - pytest = 773 passed

## 本次會話做了什麼（2026-04-13，Session 4 — Bug Hunt + Fix）

### 起點

接手 v1.11.0（`e7cf2f5`）。HANDOVER 列出 4 項待辦（E2E 驗證、shell hook、補測試、部署）。桌面有 cold-eyes-report.md（12 輪 bug hunt，96 bugs）。

### 完成內容

#### A. Bug Hunt Round 13（新增 5 bugs）

用 3 個平行 agent（v2 modules / v1 modules / tests+shell）掃描 data type boundary + cross-module contract violation。新增 5 bugs 寫入桌面報告：

| # | 嚴重度 | 摘要 |
|---|--------|------|
| 97 | major | `grouping.py` — 無行號 findings 全部 line=0 → 錯誤 cluster |
| 98 | major | `result.py` — JSON null → None 傳播 → downstream TypeError |
| 99 | major | `memory.py` — `_extract_fp` UnicodeDecodeError 丟掉 API 結果 |
| 100 | minor | `schema.py` — `add_event` 存 dict by reference |
| 101 | minor | `test_triage.py` — mock 缺 Claude CLI wrapper |

桌面報告累計：**2 critical, 34 major, 65 minor（101 bugs）**

#### B. Bug Fix 第一批（29 bugs fixed）

5 個平行 agent 修不同檔案組，避免衝突。修完後手動修復 3 個 agent 間衝突：
- engine.py 兩組改動合併
- Bug #4 修復（noise reduction 清空 findings 不再讓 fail gate pass）
- Bug #10 ceiling division 調整測試邊界值

**修復清單（29 bugs）：**

| # | 嚴重度 | 檔案 | 修法摘要 |
|---|--------|------|----------|
| #22 | **critical** | `engine.py`, `gates/result.py` | 加 `outcome["issues"]`；parser 改讀 top-level issues |
| #38 | **critical** | `prompt.py` | `_sanitize_language()`：50 字上限 + 去控制字元 + allowlist |
| #1 | major | `git.py` | 截斷後 `estimate_tokens` 重新檢查，CJK fallback |
| #3 | major | `retry/stop.py` | no-progress 用 gate 數量做 stride |
| #4 | major | `session_runner.py` | 移除 `not has_hard_failures and not calibrated` 假 pass 條件 |
| #5 | major | `retry/stop.py` | `>=` → `>` 修 off-by-one |
| #23 | major | `engine.py` | mode/threshold/scope/truncation_policy 加 `.lower()` |
| #24 | major | `cli.py` | v2 path 加 `filter_file_list()` |
| #25 | major | `session/store.py` | write-to-temp-then-rename 原子寫入 |
| #27 | major | `policy.py` | 未知 threshold 預設 0（最嚴格）|
| #30 | major | `noise/grouping.py` | proximity 比對 anchor 非 last |
| #41 | major | `engine.py` | `max_input_tokens=0` 正確 fallback |
| #42 | major | `filter.py` | `errors="replace"` 防 UnicodeDecodeError |
| #44 | major | `session_runner.py` | retry 使用 `re_run_gates` |
| #45 | major | `session_runner.py` | `previous_findings` 跨 iteration 累積 |
| #53 | major | `policy.py` | `fail-closed` 不被 override 繞過 |
| #54 | major | `engine.py` | policy 值 cast 加 try/except |
| #58 | major | `git.py` | untracked files 用 repo root 絕對路徑 |
| #70 | major | `session_runner.py` | 空 results → `failed_terminal` |
| #97 | major | `noise/grouping.py` | `_get_line` 返回 None，無行號不 cluster |
| #98 | major | `gates/result.py` | `or ""` 防 None 傳播 |
| #10 | minor | `git.py` | ceiling division `(n+3)//4` |
| #16 | minor | `noise/dedup.py` | 第一個 message 也入 supporting |
| #28 | minor | `session/store.py` | corrupt JSONL skip 不 crash |
| #65 | minor | `engine.py` | 空 diff 用 `effective_model` |
| #74 | minor | `noise/calibration.py` | 保留 `fp_match_count` |
| #82 | minor | `noise/calibration.py` | 不再 double downgrade |
| #94 | minor | `noise/calibration.py` | `calibrate_evidence` 加 try/except fallback |

**修改的檔案（13 production + 7 test）：**

```
cold_eyes/engine.py          (+26 −4)   — #22, #23, #41, #54, #65
cold_eyes/prompt.py          (+16)      — #38
cold_eyes/gates/result.py    (+13 −7)   — #22, #98
cold_eyes/runner/session_runner.py (+32 −5) — #4, #44, #45, #70
cold_eyes/retry/stop.py      (+10 −4)   — #3, #5
cold_eyes/git.py             (+15 −3)   — #1, #10, #58
cold_eyes/cli.py             (+4)       — #24
cold_eyes/policy.py          (+29 −13)  — #27, #53
cold_eyes/filter.py          (+2 −1)    — #42
cold_eyes/noise/grouping.py  (+15 −6)   — #30, #97
cold_eyes/noise/calibration.py (+22 −6) — #74, #82, #94
cold_eyes/noise/dedup.py     (+3 −1)    — #16
cold_eyes/session/store.py   (+21 −4)   — #25, #28
tests/ (7 files)             — 配合修改調整 mock 結構和斷言
```

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
    generator.py                 rule-based contract generation
    quality_checker.py           quality score + warnings
  gates/
    risk_classifier.py           session-level risk aggregation
    catalog.py                   gate registry (5 builtin gates)
    selection.py                 contract-driven + risk-escalation gate selection
    orchestrator.py              sequential gate execution, wraps engine.run()
    result.py                    gate-specific output parsers (pytest, ruff, llm_review)
  retry/
    taxonomy.py                  failure classification (11 categories)
    brief.py                     RetryBrief create/validate
    signal_parser.py             extract actionable signals from gate output
    translator.py                gate failures → retry brief
    strategy.py                  8 retry strategies + escalation logic
    stop.py                      5 stop conditions（stride-based progress check）
  noise/
    dedup.py                     (type, file, check) deduplication
    grouping.py                  anchor-based proximity + same-check clustering
    retry_suppression.py         suppress previously-seen findings（cumulative）
    fp_memory.py                 wraps v1 memory.py for v2 findings
    calibration.py               wraps v1 policy.calibrate_evidence() for v2（try/except）
  runner/
    session_runner.py            top-level run_session() entry point
    metrics.py                   collect_metrics() + aggregate_metrics()
```

---

## 本次修改的行為變化（下手者需注意）

| 改動 | 舊行為 | 新行為 |
|------|--------|--------|
| `max_retries` 語義 | `>=` check：max_retries=3 → 3 total runs | `>` check：max_retries=3 → 4 total runs（initial + 3 retries） |
| pass 判定 | noise 清空 + soft fail → pass | 只有 all gates status="pass" 才 pass |
| 空 gates | `all([])=True` → pass | → `failed_terminal` |
| 未知 threshold | 預設 3（只擋 critical） | 預設 0（全擋） |
| `fail-closed` + override | override 繞過 fail-closed | fail-closed 永遠不被繞過 |
| `_parse_llm_review` | 讀不存在的 `outcome["review"]` → 0 findings | 讀 `outcome["issues"]` → 正確提取 findings |
| `estimate_tokens` | `ascii // 4`（1-3 chars → 0） | `(ascii+3) // 4`（ceiling，≥1） |

---

## 下次 Session 要做的事

### 未提交改動（最優先）

1. **Review + Commit** — 20 files 的 bugfix 已就緒，773 tests pass。需 review 後 commit。
2. **升版決定** — 29 bugs 是否值得升版（e.g., v1.12.0）。行為變化不小（見上表），建議升版。

### 繼續修 Bug（報告中剩餘 72 bugs）

桌面報告 `cold-eyes-report.md` 剩餘未修的 bugs（101 − 29 = 72）：

**Major（13 remaining）：**
- #2 engine.py input_remaining 負數 → context/hints 靜默 skip
- #26 gates/selection.py 最低保證只在 selected 全空時觸發
- #52 history.py keep_entries=0 清空歷史
- #55 doctor.py subprocess 缺 encoding
- #56 doctor.py git not installed → FileNotFoundError
- #57 orchestrator.py subprocess 缺 explicit encoding
- #59 override.py TOCTOU race
- #71 cli.py v2 sessions 不產生 v1 history entry
- #87 claude.py os.unlink temp file on Windows
- #88 review.py Claude CLI format 假設
- #89 history.py concurrent append lost during prune
- #51 history.py non-atomic archive
- #99 engine.py + memory.py _extract_fp UnicodeDecodeError

**Minor（59 remaining）：** #6, #11, #12, #13, #15, #17, #19, #20, #21, #29, #31, #32, #33, #34, #35, #36, #37, #46, #47, #48, #49, #50, #60, #61, #62, #63, #64, #66, #67, #68, #69, #72, #73, #75, #76, #77, #78, #79, #80, #81, #83, #84, #85, #86, #90, #91, #92, #93, #95, #96, #99, #100, #101, etc.

### 原有待辦（仍有效）

3. **E2E 驗證** — 在真實 repo 跑 `python cli.py run --v2`
4. **shell hook 啟用** — `cold-review.sh` 加 `--v2` flag
5. **補測試覆蓋** — `available_gate_ids=None` auto-detection、`engine_adapter` 實際使用
6. **部署** — `cp` 至 `~/.claude/scripts/`

---

## 環境變數

（v2 新增模組不引入新的環境變數，全部沿用 v1）

| 變數 | 預設 | 說明 |
|---|---|---|
| `COLD_REVIEW_MODE` | `block` | block / report / off（現在自動 lowercase） |
| `COLD_REVIEW_MODEL` | `opus` | deep review 的 model |
| `COLD_REVIEW_SHALLOW_MODEL` | `sonnet` | shallow review 的 model |
| `COLD_REVIEW_MAX_TOKENS` | `12000` | diff 的 token 預算 |
| `COLD_REVIEW_CONTEXT_TOKENS` | `2000` | context section 的 token 預算（0=停用）|
| `COLD_REVIEW_MAX_INPUT_TOKENS` | `max_tokens+context_tokens+1000` | 總 token 上限（0 或負數 → 用預設）|
| `COLD_REVIEW_BLOCK_THRESHOLD` | `critical` | 擋的 severity 門檻（現在自動 lowercase；未知值 → 全擋）|
| `COLD_REVIEW_CONFIDENCE` | `medium` | confidence 硬過濾門檻 |
| `COLD_REVIEW_LANGUAGE` | `繁體中文（台灣）` | 輸出語言（現在被 sanitize：50 字上限） |
| `COLD_REVIEW_SCOPE` | `working` | diff 範圍（現在自動 lowercase） |
| `COLD_REVIEW_BASE` | 未設 | pr-diff scope 的 base branch |
| `COLD_REVIEW_TRUNCATION_POLICY` | `warn` | warn / soft-pass / fail-closed（現在自動 lowercase）|

## 長期事項（不可自行移除，需 user 確認）

- **v2 E2E 驗證未完成** — user 需在真實 repo 跑 `python cli.py run --v2`，然後檢查 `~/.claude/cold-review-sessions/sessions.jsonl` 確認 session 流程正確。每次 session 開頭應提醒 user 此事，直到 user 明確說測完、決定是否切為預設後才可移除本項。

## 注意事項

- v1 pipeline 有修改（engine.py 加了 `outcome["issues"]`、`.lower()`、cast 修復等），但 `engine.run()` 的對外 contract 不變 — 回傳的 dict 多了 `issues` key。
- v2 純 stdlib，無新增依賴。`pyproject.toml` 的 `include = ["cold_eyes*"]` 已自動涵蓋 sub-packages。
- Session store 用 JSONL（同 v1 history），路徑 `~/.claude/cold-review-sessions/sessions.jsonl`。現在用原子寫入。
- Gate catalog 目前 5 個 builtin gates，只有 `llm_review` 是 v1 整合；其餘 4 個 external gates 靠 subprocess。
- `max_retries` 語義改為 "actual retries after initial attempt"（`>` check）。`max_retries=3` → 4 total runs。
- Bug report 在 `C:\Users\kk789\Desktop\cold-eyes-report.md`（13 輪，101 bugs）。
- v2 task breakdown 原始文件在 `C:\Users\kk789\Downloads\cold-eyes-reviewer_v2_task_breakdown.md`。
