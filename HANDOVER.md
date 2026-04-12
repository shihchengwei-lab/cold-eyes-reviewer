# Cold Eyes Reviewer — 交接文件

## 現況

- **版本：** v1.11.2（master，已 push）
- **分支：** master
- **測試：** 774 passed / 0 failed
- **部署：** 待同步 `~/.claude/scripts/`
- **版本訊號：**
  - `__init__.py` = 1.11.2
  - CHANGELOG = v1.11.2
  - tag = 待打
  - pytest = 774 passed

## 本次會話做了什麼（2026-04-13，Session 5 — Bug Fix Round 2）

### 起點

接手 v1.11.0（`e7cf2f5`）+ Session 4 留下的 20 files 未提交改動（29 bugs fixed）。桌面 bug report 累計 101 bugs（13 輪）。

### 完成內容

#### A. Commit v1.11.1（Session 4 遺留）

將 Session 4 的 29 bug fixes commit 為 v1.11.1（`5571e90`）。

#### B. Bug Fix 第二批 — v1.11.2（24 bugs fixed）

5 個平行 agent 修不同檔案組，零重疊。修完後修正 2 個測試（memory.py 路徑正規化、override.py TTL 驗證）。

**修復清單（24 bugs）：**

| # | 嚴重度 | 檔案 | 修法摘要 |
|---|--------|------|----------|
| #2 | major | `engine.py` | `input_remaining` 負數 → stderr 警告（不再靜默 skip context/hints）|
| #26 | major | `gates/selection.py` | `llm_review` 永遠加入 selected gates（不只空 list fallback）|
| #51 | major | `history.py` | archive 改 write-to-temp-then-rename 原子寫入 |
| #52 | major | `history.py` | `keep_entries < 1` → raise ValueError（防清空歷史）|
| #55 | major | `doctor.py` | subprocess 加 `encoding="utf-8"` |
| #56 | major | `doctor.py` | 捕 `FileNotFoundError`（git 未安裝）|
| #57 | major | `gates/orchestrator.py` | external gate subprocess 加 `encoding="utf-8"` |
| #71 | major | `cli.py` | v2 session 結果寫入 v1 history（`log_to_history`）|
| #87 | major | `claude.py` | `os.unlink` 加 try/except OSError（Windows handle lock）|
| #88 | major | `review.py` | 同時支援 wrapped `{"result":"..."}` 和 unwrapped 格式 |
| #89 | major | `history.py` | prune 改原子寫入 |
| #99 | major | `memory.py` | `errors="replace"` 防 UnicodeDecodeError |
| #6 | minor | `gates/result.py` | exit_code≠0 時不覆寫 status 為 pass |
| #11 | minor | `detector.py` | regex `[/\\s]` → `[/\\]`（不再誤匹 `views`）|
| #12 | minor | `memory.py` | 路徑 `\` → `/` 統一（Windows 混合分隔符）|
| #13 | minor | `history.py` | `makedirs("")` 防護 |
| #29 | minor | `override.py` | `ttl_minutes ≤ 0` → raise ValueError |
| #33 | minor | `runner/metrics.py` | aborted sessions 不影響 pass_rate 分母 |
| #63 | minor | `policy.py` | 未知 confidence 預設 0（最嚴格）|
| #67 | minor | `constants.py` | BUILTIN_IGNORE 加 `*.map` |
| #69 | minor | `review.py` | `{"result": null}` 不再靜默 pass |
| #72 | minor | `history.py` | archive 目錄 makedirs 無條件執行 |
| #73 | minor | `engine.py` | hint tokens 計入 token_count |
| #75 | minor | `gates/result.py` | ruff parser 用 `[A-Z]\d{3,4}` regex |

**修改的檔案（15 production + 2 test）：**

```
cold_eyes/engine.py              (+7)      — #2, #73
cold_eyes/memory.py              (+6 −2)   — #99, #12
cold_eyes/history.py             (+62 −10) — #51, #52, #89, #13, #72
cold_eyes/doctor.py              (+7 −2)   — #55, #56
cold_eyes/gates/orchestrator.py  (+1)      — #57
cold_eyes/gates/selection.py     (+5 −2)   — #26
cold_eyes/cli.py                 (+17)     — #71
cold_eyes/review.py              (+38 −8)  — #88, #69
cold_eyes/gates/result.py        (+12 −2)  — #6, #75
cold_eyes/constants.py           (+2 −1)   — #67
cold_eyes/claude.py              (+5 −1)   — #87
cold_eyes/override.py            (+2)      — #29
cold_eyes/detector.py            (+2 −1)   — #11
cold_eyes/policy.py              (+4 −2)   — #63
cold_eyes/runner/metrics.py      (+5 −1)   — #33
tests/test_memory.py             (+2 −1)   — 配合 #12 路徑正規化
tests/test_override.py           (+15 −2)  — 配合 #29 TTL 驗證 + 新測試
```

#### C. Push

v1.11.1 + v1.11.2 一起推（`e7cf2f5..1a63896`）。

---

## 累計修復統計

| 版本 | Commit | Bugs fixed | Tests |
|------|--------|-----------|-------|
| v1.11.1 | `5571e90` | 29（2 critical, 15 major, 12 minor）| 773 |
| v1.11.2 | `1a63896` | 24（12 major, 12 minor）| 774 |
| **合計** | | **53 / 101** | |

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
    selection.py                 contract-driven + risk-escalation gate selection（llm_review 保證）
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
    metrics.py                   collect_metrics() + aggregate_metrics()（aborted 排除分母）
```

---

## v1.11.1 + v1.11.2 行為變化（下手者需注意）

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

---

## 下次 Session 要做的事

### 繼續修 Bug（報告中剩餘 48 bugs）

桌面報告 `cold-eyes-report.md` 累計 101 bugs，已修 53。

**Major（1 remaining）：**
- #59 override.py TOCTOU race — `consume_override` 兩個 concurrent review 都讀到 token → 都 pass。需 file locking 或 atomic consume。複雜度高，Windows 行為不同。

**Minor（47 remaining）：** #15, #17, #19, #20, #21, #31, #32, #34, #35, #36, #37, #46, #47, #48, #49, #50, #60, #61, #62, #64, #68, #76, #77, #78, #79, #80, #81, #83, #84, #85, #86, #90, #91, #92, #93, #95, #96, #100, #101, etc.

### 原有待辦（仍有效）

1. **E2E 驗證** — 在真實 repo 跑 `python cli.py run --v2`
2. **shell hook 啟用** — `cold-review.sh` 加 `--v2` flag
3. **補測試覆蓋** — `available_gate_ids=None` auto-detection、`engine_adapter` 實際使用
4. **部署** — `cp` 至 `~/.claude/scripts/`

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
| `COLD_REVIEW_MAX_INPUT_TOKENS` | `max_tokens+context_tokens+1000` | 總 token 上限（0 或負數 → 用預設；負數時 stderr 警告）|
| `COLD_REVIEW_BLOCK_THRESHOLD` | `critical` | severity 門檻（自動 lowercase；未知值 → 全擋）|
| `COLD_REVIEW_CONFIDENCE` | `medium` | confidence 門檻（未知值 → 最嚴格）|
| `COLD_REVIEW_LANGUAGE` | `繁體中文（台灣）` | 輸出語言（sanitize：50 字上限）|
| `COLD_REVIEW_SCOPE` | `working` | diff 範圍（自動 lowercase）|
| `COLD_REVIEW_BASE` | 未設 | pr-diff scope 的 base branch |
| `COLD_REVIEW_TRUNCATION_POLICY` | `warn` | warn / soft-pass / fail-closed（自動 lowercase）|

## 長期事項（不可自行移除，需 user 確認）

- **v2 E2E 驗證未完成** — user 需在真實 repo 跑 `python cli.py run --v2`，然後檢查 `~/.claude/cold-review-sessions/sessions.jsonl` 確認 session 流程正確。每次 session 開頭應提醒 user 此事，直到 user 明確說測完、決定是否切為預設後才可移除本項。

## 注意事項

- v1 pipeline 有修改（engine.py 加了 `outcome["issues"]`、`.lower()`、cast、input_remaining 警告等），但 `engine.run()` 的對外 contract 不變 — 回傳的 dict 多了 `issues` key。
- v2 純 stdlib，無新增依賴。`pyproject.toml` 的 `include = ["cold_eyes*"]` 已自動涵蓋 sub-packages。
- Session store 用 JSONL（同 v1 history），路徑 `~/.claude/cold-review-sessions/sessions.jsonl`。原子寫入。
- history.py 的 prune/archive 現在都用 write-to-temp-then-rename（防 crash 資料遺失，但不防 concurrent write）。
- Gate catalog 目前 5 個 builtin gates，`llm_review` 永遠加入（若 available）。其餘 4 個 external gates 靠 subprocess（已加 `encoding="utf-8"`）。
- `max_retries` 語義 = actual retries after initial attempt。`max_retries=3` → 4 total runs。
- v2 session 結果現在寫入 v1 history（`model="v2-session"`），v1 stats/quality-report 可見。
- review.py 同時支援 Claude CLI wrapped `{"result":"..."}` 和 unwrapped 格式。
- Bug report 在 `C:\Users\kk789\Desktop\cold-eyes-report.md`（13 輪，101 bugs，53 fixed）。
- v2 task breakdown 原始文件在 `C:\Users\kk789\Downloads\cold-eyes-reviewer_v2_task_breakdown.md`。
