# Cold Eyes Reviewer — 交接文件

## 現況

- **版本：** v1.9.2（master，2026-04-12）
- **分支：** master
- **測試：** 531 passed（coverage 87%，門檻 75%）
- **部署：** 已同步 `~/.claude/scripts/`
- **版本訊號：**
  - `__init__.py` = 1.9.2 ✓
  - CHANGELOG = v1.9.2 ✓
  - About = 已更新 ✓
  - pytest = 531 passed ✓
  - tag = v1.9.2 ✓
  - Release = v1.9.2 ✓
- **CI：** Tests ✓ + Release ✓
- **Lint：** ruff clean（cold_eyes/ + tests/）
- **Eval：** 33/33 deterministic，regression check pass

## 架構

v1.9.0 新增 memory module（FP pattern extraction + matching），接入 calibration pipeline。
v1.9.1-v1.9.2 為文件修正，無 runtime 變更。

```
cold-review.sh              （同 v1.8.0，無變更）
  └→ cold_eyes/cli.py       CLI entry → engine.py → 各模組

cold_eyes/
  memory.py                  v1.9.0 NEW — FP pattern extraction + matching + category baselines
  policy.py                  v1.9.0 UPDATED — calibrate_evidence() 加 Rule 3 (FP match) + Rule 4 (category cap)
  engine.py                  v1.9.0 UPDATED — extract_fp_patterns() 在 parse 後、apply_policy 前執行
  constants.py               v1.9.0 UPDATED — DEPLOY_FILES 加入 memory.py
  detector.py                （同 v1.8.0）
  schema.py                  （同 v1.7.0）
  review.py                  （同 v1.7.0）
  prompt.py                  （同 v1.6.0）
  triage.py                  （同 v1.5.0）
  context.py                 （同 v1.6.0）
  git.py                     （同 v1.7.0）
  （其餘模組同 v1.8.0）

cold-review-prompt.txt       v1.9.1 UPDATED — self-disclosure: 3 input types + limitations
cold-review-prompt-shallow.txt （同 v1.6.0，shallow 真的只看 diff）

evals/
  cases/                     33 total（+3 FP memory cases）
  manifest.json              v1.9.0 UPDATED — 33 cases，ground_truth 15/18
  eval_runner.py             v1.9.0 UPDATED — _evaluate_case() passes fp_patterns

docs/
  roadmap.md                 v1.9.0 UPDATED — v1.9.0 section
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

## 本次會話做了什麼（2026-04-12）

### 起點

接手 v1.8.0（`f0a6898`，469 tests）。HANDOVER 指定：收尾 + 性價比階段 5。

### v1.8.0 收尾

| # | 做了什麼 | 結果 |
|---|---------|------|
| 1 | CI 確認 | Tests ✓ + Release ✓ |
| 2 | GitHub About 更新 | 469 tests, evidence-bound claims, detectors |

### Phase 5：FP Memory + Confidence Calibration（v1.9.0）

| # | 做了什麼 | 檔案 | 測試變化 |
|---|---------|------|---------|
| WP1 | FP pattern extraction + matching | `memory.py` | +27 |
| WP2 | Rule 3 in calibrate_evidence() + engine wiring | `policy.py`, `engine.py`, `constants.py` | 0 |
| WP3 | Category baselines + Rule 4 | `memory.py`, `policy.py` | +25 |
| WP4 | 3 eval cases + manifest + version bump + CHANGELOG + roadmap | 多檔 | +4 |

### 文件事實對齊（v1.9.1 + v1.9.2）

用戶依北極星原則（「只從基本事實長出答案」）審查 repo 描述，發現兩類問題：

**說少的（v1.9.1 — prompt + About）：**
- Deep prompt 聲稱「只看到 git diff」，但 model 實際收到 diff + context block + detector hints
- 修正：prompt 改為明列 3 種 input types 及各自來源和限度
- GitHub About 的「Zero-context」改為「Cold-read」

**說少的（v1.9.2 — README 6 處）：**
- 介紹：「zero-context」「only the git diff」→ 區分 deep/shallow 各看到什麼
- 流程圖：3 步 → 10 步 pipeline
- Output 範例：補 evidence-bound 欄位
- 安裝指令：補 `cold-review-prompt-shallow.txt`
- Eval 數字：24 cases / 5 categories → 33 / 7（3 處）

**說多的（v1.9.2 同 commit — README 5 處）：**
- 「It catches」→「It asks the model to check for」（能力不等於保證）
- 「→ Claude fixes」→「Claude Code decides what to do next」（Cold Eyes 只擋不修）
- Token 成本表寫死 $0.01-$2.00 → 改描述 4 個成本因素 + 訂閱制/API 計費差異
- Files 表列 11 模組 → 18 模組
- Prompt 描述停在 v1.0 → 列出實際內容

### Input budget cap（v1.9.2 追加，無版號變更）

diff + context + detector hints 拼接後無總預算上限，大 diff 觸發 "Prompt is too long"。

| # | 做了什麼 | 檔案 | 測試變化 |
|---|---------|------|---------|
| 1 | `max_input_tokens` 總預算控制 + 預算分配邏輯 | `engine.py` | +6 |
| 2 | `--max-input-tokens` CLI flag | `cli.py` | 0 |

### 驗證結果

- 531 tests passed（+62 from v1.8.0 的 469）
- Eval: 33/33 deterministic
- Lint (ruff): clean
- Coverage: 87%

### Commits

| Hash | 說明 |
|------|------|
| `8082f4e` | v1.9.0 Phase 5 commit + tag |
| `cd40137` | HANDOVER rewrite for v1.9.0 |
| `be9f241` | v1.9.1 prompt self-disclosure + tag |
| `e337310` | v1.9.2 README factual alignment (說少的) + tag |
| `c3e6aeb` | README overclaim fixes (說多的), 無版號變更 |

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

（同 v1.8.0，無新增 flags。FP memory 自動從 override history 讀取，無需設定。）

## 已知問題

- FP memory 在 history 為空時無效果（設計行為 — 新安裝的 graceful no-op）。
- `compute_category_baselines()` 的 total_reviews 估算（`total_overrides * 3`）是 heuristic。極端 override 率下可能不準確。
- Repo-type classification 是 file-path heuristic。混合型 repo 取最高分 type，可能不完美。
- Evidence calibration 對 old-format model output 的影響：high confidence 無 evidence → 降為 medium。
