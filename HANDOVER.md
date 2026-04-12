# Cold Eyes Reviewer — 交接文件

## 現況

- **版本：** v1.9.2（master，`4054798`，2026-04-12）
- **分支：** master
- **測試：** 531 passed（coverage 87%，門檻 75%）
- **部署：** 已同步 `~/.claude/scripts/`（22 files verified）
- **版本訊號：**
  - `__init__.py` = 1.9.2 ✓
  - CHANGELOG = v1.9.2 ✓
  - About = 已更新 ✓
  - pytest = 531 passed ✓
  - tag = v1.9.2 ✓
  - Release = v1.9.2 ✓
- **CI：** Tests ✓（6 OS/Python 組合）、Shellcheck ✓、Lint ✓
- **Eval：** 33/33 deterministic，regression check pass

## 架構

```
cold-review.sh              （同 v1.8.0，無變更）
  └→ cold_eyes/cli.py       CLI entry → engine.py → 各模組

cold_eyes/
  engine.py                  v1.9.2 UPDATED — max_input_tokens 總預算控制
  cli.py                     v1.9.2 UPDATED — --max-input-tokens flag
  memory.py                  v1.9.0 — FP pattern extraction + matching + category baselines
  policy.py                  v1.9.0 — calibrate_evidence() Rule 3 (FP match) + Rule 4 (category cap)
  constants.py               v1.9.0 — DEPLOY_FILES 含 memory.py
  detector.py                （同 v1.8.0）
  schema.py                  （同 v1.7.0）
  review.py                  （同 v1.7.0）
  prompt.py                  （同 v1.6.0）
  triage.py                  （同 v1.5.0）
  context.py                 （同 v1.6.0）
  git.py                     （同 v1.7.0）
  （其餘模組同 v1.8.0）

cold-review-prompt.txt       v1.9.1 — self-disclosure: 3 input types + limitations
cold-review-prompt-shallow.txt （同 v1.6.0，shallow 只看 diff）

evals/
  cases/                     33 total（+3 FP memory cases）
  manifest.json              v1.9.0 — 33 cases，ground_truth 15/18
  eval_runner.py             v1.9.0 — _evaluate_case() passes fp_patterns

docs/
  roadmap.md                 v1.9.0 — v1.9.0 section
```

### Engine pipeline 流程

```
collect → filter → rank → triage → build_diff → [context] → [detector] → prompt → model → parse → [fp_memory] → calibrate → filter → policy
                          ^^^^^^^^               ^^^^^^^^^^^^^^^^^^^^^^^^^^^
                          skip/shallow/deep      max_input_tokens 總預算控制：
                                                 diff 先佔 → context 拿剩餘 → hints 剩餘夠才加
                                                                                ^^^^^^^^^^
                                                                                extract_fp_patterns()
                                                                                → calibrate_evidence(fp_patterns)
                                                                                → Rule 3: FP match -1/type
                                                                                → Rule 4: category cap
```

### Input budget 機制

原本 diff（`max_tokens`）、context（`context_tokens`）、detector hints（無預算）各自獨立，拼接後無總量上限。大 diff 可觸發 Claude CLI "Prompt is too long"。

`engine.py` 加入 `max_input_tokens` 作為共享總預算，三個元件依序扣除：

| 優先順序 | 元件 | 預算來源 | 超出行為 |
|---|---|---|---|
| 1 | diff | `max_tokens`（已有截斷機制） | 截斷個別檔案 |
| 2 | context | `min(context_tokens, 剩餘)` | 縮減或跳過 |
| 3 | detector hints | 剩餘 | 整段丟棄（`hints_dropped=True`） |

預設 `max_input_tokens = max_tokens + context_tokens + 1000 = 15000`。

## 本次會話做了什麼（2026-04-12）

### 起點

接手 v1.9.2（`c89984d`，525 tests）。用戶問 "Prompt is too long" 錯誤成因。

### 修了什麼

| # | 做了什麼 | 檔案 |
|---|---------|------|
| 1 | `max_input_tokens` 總預算控制 + 預算分配邏輯 | `engine.py`（+6 tests） |
| 2 | `--max-input-tokens` CLI flag | `cli.py` |
| 3 | CLI help string 超過 ruff E501 130 字元限制 | `cli.py` |
| 4 | CHANGELOG、HANDOVER 更新 | docs |

### Commits

| Hash | 說明 |
|------|------|
| `1024981` | fix(engine): add max_input_tokens total budget cap |
| `3752780` | docs: rewrite HANDOVER for input budget cap session handoff |
| `4054798` | fix(lint): shorten cli help string to pass ruff E501 |

### 驗證

- 531 tests passed（+6）
- CI: Tests ✓、Lint ✓、Shellcheck ✓
- 22 DEPLOY_FILES hash 一致

---

## 下次 Session 要做什麼

### 兩個方向皆暫緩

用戶決定 Phase 1-5 完成後暫不推進。原因：
- **Trust Phase 2（外部證據）** — 目前只有自己使用，無外部審核需求
- **實戰校準** — override history 資料不足，需要累積使用數據

### 如果要做事

最有價值的下一步是**日常使用累積數據**，然後：
1. 用 `cli.py stats` 和 `quality-report` 看 override 分佈
2. 檢驗 FP memory 的 min_count=2、last_days=90 是否合適
3. 根據結果調參

### 注意事項

- 模型名稱是純字串透傳，Claude CLI 支援的新模型直接可用，不需改程式碼。
- FP memory 在 history 為空時無效果（graceful no-op）。
- `compute_category_baselines()` 用 `total_overrides * 3` 估算 total_reviews，是 heuristic。
- Manifest ground_truth_summary 現在是 15/18。加 eval cases 要重新計算。
- 版號升太快的教訓：docs-only 變更不需要獨立 patch version，應累積後一次推。
- 性價比計畫全文見 `C:\Users\kk789\Downloads\cold-eyes-reviewer_cost_effective_roadmap_extreme.md`。

## 環境變數

| 變數 | 預設 | 說明 |
|---|---|---|
| `COLD_REVIEW_MODE` | `block` | block / report / off |
| `COLD_REVIEW_MODEL` | `opus` | deep review 的 model |
| `COLD_REVIEW_SHALLOW_MODEL` | `sonnet` | shallow review 的 model |
| `COLD_REVIEW_MAX_TOKENS` | `12000` | diff 的 token 預算 |
| `COLD_REVIEW_CONTEXT_TOKENS` | `2000` | context section 的 token 預算（0=停用）|
| `COLD_REVIEW_MAX_INPUT_TOKENS` | `max_tokens+context_tokens+1000` | 總 token 上限（diff+context+hints）|
| `COLD_REVIEW_BLOCK_THRESHOLD` | `critical` | 擋的 severity 門檻 |
| `COLD_REVIEW_CONFIDENCE` | `medium` | confidence 硬過濾門檻 |
| `COLD_REVIEW_LANGUAGE` | `繁體中文（台灣）` | 輸出語言 |
| `COLD_REVIEW_SCOPE` | `working` | diff 範圍 |
| `COLD_REVIEW_BASE` | 未設 | pr-diff scope 的 base branch |
| `COLD_REVIEW_TRUNCATION_POLICY` | `warn` | warn / soft-pass / fail-closed |

## CLI 命令

v1.9.2 新增 `--max-input-tokens` flag。其餘同 v1.8.0。FP memory 自動從 override history 讀取，無需設定。

## 已知問題

- FP memory 在 history 為空時無效果（設計行為 — 新安裝的 graceful no-op）。
- `compute_category_baselines()` 的 total_reviews 估算（`total_overrides * 3`）是 heuristic。極端 override 率下可能不準確。
- Repo-type classification 是 file-path heuristic。混合型 repo 取最高分 type，可能不完美。
- Evidence calibration 對 old-format model output 的影響：high confidence 無 evidence → 降為 medium。
