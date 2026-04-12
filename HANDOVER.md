# Cold Eyes Reviewer — 交接文件

## 現況

- **版本：** v1.10.0（master）
- **分支：** master
- **測試：** 773 passed / 0 failed
- **v1 模組：** 完全未修改，531 既有測試不受影響
- **v2 模組：** 26 tasks across 5 phases，debug review 完成，242 新測試
- **Lint：** clean
- **狀態：** 已 commit、已升版、尚未部署

## 本次會話做了什麼（2026-04-12）

### 起點

接手 v1.9.2（`b282ed2`，531 tests）。用戶提供 v2 任務拆分文件 `cold-eyes-reviewer_v2_task_breakdown.md`，目標是把系統從 AI reviewer 重構成 **Agent coding correctness layer**。

### 完成內容

按計畫執行 5 個 Phase（A→E），26 個 task 全部交付：

| Phase | 內容 | 新模組 | 新測試 |
|-------|------|--------|--------|
| A — Data Skeleton | types, session, contract | 7 files | 93 tests |
| B — Gate Orchestration | risk classifier, catalog, selection, orchestrator, result | 5 files | 52 tests |
| C — Retry Loop | taxonomy, brief, signal parser, translator, strategy, stop | 6 files | 53 tests |
| D — Noise Suppression | dedup, grouping, suppression, fp_memory, calibration | 5 files | 30 tests |
| E — E2E Integration | session_runner, metrics + 5 scenario tests | 3 files | 13 tests |

**v2 新增：** 31 Python 檔案，2356 行程式碼，2076 行測試。

### 關鍵設計決策

1. v1 `engine.run()` **完全未動**，被包裝為 `llm_review` gate
2. 新增 6 個 sub-package：`session/`, `contract/`, `gates/`, `retry/`, `noise/`, `runner/`
3. 共用型別定義在 `cold_eyes/type_defs.py`（TypedDict + helpers）
4. 全部 rule-based deterministic，無 LLM 參與 orchestration
5. 純 stdlib，無新增外部依賴

### v2 核心入口

```python
from cold_eyes.runner.session_runner import run_session
session = run_session("fix auth bug", ["src/auth.py"])
```

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
    catalog.py                   gate registry (llm_review, test_runner, lint_checker, type_checker, build_checker)
    selection.py                 contract-driven + risk-escalation gate selection
    orchestrator.py              sequential gate execution, wraps engine.run()
    result.py                    gate-specific output parsers (pytest, ruff, llm_review)
  retry/
    taxonomy.py                  failure classification (11 categories)
    brief.py                     RetryBrief create/validate
    signal_parser.py             extract actionable signals from gate output
    translator.py                gate failures → retry brief
    strategy.py                  8 retry strategies + escalation logic
    stop.py                      5 stop conditions (max retries, repeated failure, no progress, scope expanding, all passing)
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

## Debug Review 結果（2026-04-12，第二次會話）

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

同時修了 `Literal.__args__`（CPython impl detail）→ explicit lists。

### 審查後不需修的項目

| 項目 | 結論 |
|------|------|
| `generator.py` path join | RISK_CATEGORIES patterns 足夠具體，偏保守合理 |
| `stop.py:16` `>=` | 語義正確：max_retries = max briefs allowed |
| `retry_suppression.py` key | 各 gate parser field naming 在同 gate 內一致 |
| `store.py` concurrent write | v2.0 single-threaded known limitation |
| `catalog.py` `shutil.which()` | Windows 已處理 `.exe` |
| `fp_memory.py` try/except | 標準 optional dependency pattern |

### 下次 Session 可做的事

- 升版（v2.0.0 或 v1.10.0）
- `run_session()` 接入 `SessionStore.save()` 和 `history.log_to_history()`
- 補測試覆蓋：`available_gate_ids=None` auto-detection、`engine_adapter` 實際使用
- 接入真實 gate（目前 external gates 靠 subprocess，但 wiring 完整）

---

## 環境變數

（與 v1.9.2 相同，v2 新增模組不引入新的環境變數）

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

- v2 新增檔案尚未 commit。所有變更都是 untracked files。
- v1 pipeline 完全未修改。`engine.run()` 被 `gates/orchestrator.py` 包裝，不是替換。
- v2 純 stdlib，無新增依賴。`pyproject.toml` 的 `include = ["cold_eyes*"]` 已自動涵蓋 sub-packages。
- Session store 用 JSONL（同 v1 history），路徑 `~/.claude/cold-review-sessions/sessions.jsonl`。
- Gate catalog 目前 5 個 builtin gates，只有 `llm_review` 是 v1 整合；其餘 4 個 external gates 靠 subprocess。
- v2 task breakdown 原始文件在 `C:\Users\kk789\Downloads\cold-eyes-reviewer_v2_task_breakdown.md`。
- 實作計畫在 `C:\Users\kk789\.claude\plans\effervescent-zooming-gray.md`。
