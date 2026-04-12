# Cold Eyes Reviewer — 交接文件

## 現況

- **版本：** v1.10.0（master，`4024329`，2026-04-12）
- **分支：** master
- **測試：** 773 passed / 0 failed
- **部署：** 已同步 `~/.claude/scripts/`（v1 + v2 全部模組）
- **版本訊號：**
  - `__init__.py` = 1.10.0
  - CHANGELOG = v1.10.0
  - tag = v1.10.0
  - Release = v1.10.0
  - pytest = 773 passed

## 本次會話做了什麼（2026-04-12，Session 2 — Debug Review）

### 起點

接手 v1.9.2（`b282ed2`）+ 31 untracked v2 files（前一 session 寫的，772 passed / 1 failed）。

### 完成內容

1. **修 4 個 lint issues** — unused var/imports（`risk_classifier`、`calibration`、`strategy`、`taxonomy`）
2. **修 circular import** — `types.py` shadow stdlib `types`，重命名為 `type_defs.py`，更新 10 個 import
3. **修 Windows path bug** — `_parse_ruff()` 的 `:` split 在 `C:\` 路徑壞掉，加 drive letter 偵測
4. **修 code quality** — `session_runner.py` ternary side-effect → `if`、`translator.py` dead code 移除、`Literal.__args__` → explicit lists
5. **完整 debug checklist 審查** — 邏輯正確性 6 項、邊界條件 5 項、整合性 4 項、測試覆蓋 4 項
6. **升版 v1.10.0** — `__init__`、CHANGELOG、tag、GitHub Release 全對齊
7. **部署** — `cp` 至 `~/.claude/scripts/`

### Commits

| Hash | 說明 |
|------|------|
| `67a0873` | feat(v2): add correctness session engine (Phase A-E) + debug review |
| `4024329` | chore: bump version to v1.10.0, align CHANGELOG and HANDOVER |

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
  │   ├─ if all passed → return "passed"
  │   │
  │   ├─ translate()               ← retry/translator.py
  │   ├─ should_stop()             ← retry/stop.py
  │   ├─ select_strategy()         ← retry/strategy.py
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
    store.py                     JSONL-based SessionStore
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
    stop.py                      5 stop conditions
  noise/
    dedup.py                     (type, file, check) deduplication
    grouping.py                  proximity + same-check root-cause clustering
    retry_suppression.py         suppress previously-seen findings
    fp_memory.py                 wraps v1 memory.py for v2 findings
    calibration.py               wraps v1 policy.calibrate_evidence() for v2
  runner/
    session_runner.py            top-level run_session() entry point
    metrics.py                   collect_metrics() + aggregate_metrics()
```

---

## Debug Review 結果

### 修了什麼（6 bugs + 2 code quality）

| # | 檔案 | 問題 | 修法 |
|---|------|------|------|
| 1 | `risk_classifier.py:38` | F841 `test_count` unused | 移除 |
| 2 | `calibration.py:3` | F401 `CONFIDENCE_ORDER` unused | 移除 import |
| 3 | `strategy.py:3` | F401 `VALID_STRATEGIES` unused | 移除 import |
| 4 | `taxonomy.py:3` | F401 `FAILURE_CATEGORIES` unused | 移除 import |
| 5 | `types.py` | shadow stdlib `types` → circular import | 重命名為 `type_defs.py`，10 imports 更新 |
| 6 | `result.py:79` | `_parse_ruff()` `:` split 在 Windows `C:\` 壞掉 | 偵測 drive letter |
| 7 | `session_runner.py:176` | ternary side-effect | 改為 `if` statement |
| 8 | `translator.py:122` | dead code `return "low"` | 移除 |

### 審查後不需修的項目

| 項目 | 結論 |
|------|------|
| `generator.py` path join | RISK_CATEGORIES patterns 足夠具體，偏保守合理 |
| `stop.py:16` `>=` | 語義正確：max_retries = max briefs allowed |
| `retry_suppression.py` key | 各 gate parser field naming 在同 gate 內一致 |
| `store.py` concurrent write | v2.0 single-threaded known limitation |
| `catalog.py` `shutil.which()` | Windows 已處理 `.exe` |
| `fp_memory.py` try/except | 標準 optional dependency pattern |

---

## 下次 Session 可做的事

1. **接入持久化** — `run_session()` 接 `SessionStore.save()` 和 `history.log_to_history()`，讓 v2 session 被 v1 stats/quality-report 看到
2. **補測試覆蓋** — `available_gate_ids=None` auto-detection、`engine_adapter` 實際使用、`grouping.py` edge cases
3. **接入真實 gate** — external gates 的 subprocess wiring 完整但未實際跑過
4. **constants.py DEPLOY_FILES** — 未包含 v2 sub-packages，目前靠手動 cp

---

## 環境變數

（v2 新增模組不引入新的環境變數，全部沿用 v1）

| 變數 | 預設 | 說明 |
|---|---|---|
| `COLD_REVIEW_MODE` | `block` | block / report / off |
| `COLD_REVIEW_MODEL` | `opus` | deep review 的 model |
| `COLD_REVIEW_SHALLOW_MODEL` | `sonnet` | shallow review 的 model |
| `COLD_REVIEW_MAX_TOKENS` | `12000` | diff 的 token 預算 |
| `COLD_REVIEW_CONTEXT_TOKENS` | `2000` | context section 的 token 預算（0=停用）|
| `COLD_REVIEW_MAX_INPUT_TOKENS` | `max_tokens+context_tokens+1000` | 總 token 上限 |
| `COLD_REVIEW_BLOCK_THRESHOLD` | `critical` | 擋的 severity 門檻 |
| `COLD_REVIEW_CONFIDENCE` | `medium` | confidence 硬過濾門檻 |
| `COLD_REVIEW_LANGUAGE` | `繁體中文（台灣）` | 輸出語言 |
| `COLD_REVIEW_SCOPE` | `working` | diff 範圍 |
| `COLD_REVIEW_BASE` | 未設 | pr-diff scope 的 base branch |
| `COLD_REVIEW_TRUNCATION_POLICY` | `warn` | warn / soft-pass / fail-closed |

## 注意事項

- v1 pipeline 完全未修改。`engine.run()` 被 `gates/orchestrator.py` 包裝，不是替換。
- v2 純 stdlib，無新增依賴。`pyproject.toml` 的 `include = ["cold_eyes*"]` 已自動涵蓋 sub-packages。
- Session store 用 JSONL（同 v1 history），路徑 `~/.claude/cold-review-sessions/sessions.jsonl`。
- Gate catalog 目前 5 個 builtin gates，只有 `llm_review` 是 v1 整合；其餘 4 個 external gates 靠 subprocess。
- `max_retries` 語義是 "max briefs allowed"（`>=` check），不是 "retries after initial attempt"。
- v2 task breakdown 原始文件在 `C:\Users\kk789\Downloads\cold-eyes-reviewer_v2_task_breakdown.md`。
