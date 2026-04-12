# Cold Eyes Reviewer — 交接文件

## 現況

- **版本：** v1.9.0（master，`8082f4e`，2026-04-12）
- **分支：** master
- **測試：** 525 passed（coverage 87%，門檻 75%）
- **部署：** 已同步 `~/.claude/scripts/`
- **版本訊號：**
  - `__init__.py` = 1.9.0 ✓
  - CHANGELOG = v1.9.0 ✓
  - About = 已更新 ✓
  - pytest = 525 passed ✓
  - tag = v1.9.0 ✓
  - Release = v1.9.0 ✓
- **CI：** Tests ✓ + Release ✓
- **Lint：** ruff clean（cold_eyes/ + tests/）
- **Eval：** 33/33 deterministic，regression check pass

## 架構

v1.9.0 新增 memory module（FP pattern extraction + matching），接入 calibration pipeline。

```
cold-review.sh              （同 v1.8.0，無變更）
  └→ cold_eyes/cli.py       CLI entry → engine.py → 各模組

cold_eyes/
  memory.py                  NEW — FP pattern extraction + matching + category baselines
  policy.py                  UPDATED — calibrate_evidence() 加 Rule 3 (FP match) + Rule 4 (category cap)
  engine.py                  UPDATED — extract_fp_patterns() 在 parse 後、apply_policy 前執行
  constants.py               UPDATED — DEPLOY_FILES 加入 memory.py
  detector.py                （同 v1.8.0）
  schema.py                  （同 v1.7.0）
  review.py                  （同 v1.7.0）
  prompt.py                  （同 v1.6.0）
  triage.py                  （同 v1.5.0）
  context.py                 （同 v1.6.0）
  git.py                     （同 v1.7.0）
  （其餘模組同 v1.8.0）

cold-review-prompt.txt       （同 v1.7.0）
cold-review-prompt-shallow.txt （同 v1.6.0）

evals/
  cases/                     33 total（+3 FP memory cases）
  manifest.json              UPDATED — 33 cases，ground_truth 15/18
  eval_runner.py             UPDATED — _evaluate_case() passes fp_patterns from case to apply_policy()

docs/
  roadmap.md                 UPDATED — v1.9.0 section
```

### Engine pipeline 流程

```
collect → filter → rank → triage → build_diff → [context] → [detector] → prompt → model → parse → [fp_memory] → calibrate → filter → policy
                          ^^^^^^^^                            ^^^^^^^^^^                   ^^^^^^^^^^
                          skip/shallow/deep                   state signals                extract_fp_patterns()
                                                              + repo-specific              → calibrate_evidence(fp_patterns)
                                                              focus hints                  → Rule 3: FP match -1/type
                                                                                           → Rule 4: category cap
```

- `extract_fp_patterns()` 讀取 override history，提取 3 種模式：category、path、check prefix
- `match_fp_pattern(issue, fp_patterns)` 檢查單一 issue 是否匹配 0-3 種模式
- `calibrate_evidence()` Rule 3：每匹配一種模式 → confidence -1（最多 -2）
- `calibrate_evidence()` Rule 4：高 override ratio 的 category → confidence 上限（>=0.5 → low，>=0.3 → medium）
- `compute_category_baselines()` 用 total_overrides * 3 估算 total_reviews，計算 category ratio
- engine.py 和 policy.py 對 memory module 的 import 有 try/except fallback，部署不同步時 graceful no-op

## 本次會話做了什麼（2026-04-12）

### 起點

接手 v1.8.0（`f0a6898`，469 tests）。HANDOVER 指定：收尾 + 性價比階段 5「False-Positive Memory + Confidence Calibration」。

### v1.8.0 收尾

| # | 做了什麼 | 結果 |
|---|---------|------|
| 1 | CI 確認 | Tests ✓ + Release ✓ |
| 2 | GitHub About 更新 | 469 tests, evidence-bound claims, detectors |

### Phase 5 執行

| # | 做了什麼 | 檔案 | 測試變化 |
|---|---------|------|---------|
| WP1 | FP pattern extraction: category, path, check prefix | `memory.py` | 0 |
| WP1 | FP pattern matching: 0-3 types, backslash-aware | `memory.py` | 0 |
| WP1 | Tests: extraction (14) + matching (13) | `tests/test_memory.py` | +27 |
| WP2 | Rule 3 in calibrate_evidence(): FP match → -1/type (max -2) | `policy.py` | 0 |
| WP2 | Engine wiring: extract_fp_patterns() before apply_policy() | `engine.py` | 0 |
| WP2 | Outcome fields: fp_memory_overrides, fp_memory_patterns | `engine.py` | 0 |
| WP2 | DEPLOY_FILES updated | `constants.py` | 0 |
| WP3 | compute_category_baselines(): ratio-based caps | `memory.py` | 0 |
| WP3 | Rule 4 in calibrate_evidence(): category confidence cap | `policy.py` | 0 |
| WP3 | Tests: FP calibration (12) + category cap (6) + baselines (7) | `tests/test_fp_calibration.py` | +25 |
| WP4 | 3 eval cases: known-pattern, category-cap, no-match | `evals/cases/` | 0 |
| WP4 | Manifest updated (33 cases, ground_truth 15/18) | `evals/manifest.json` | 0 |
| WP4 | Eval runner: fp_patterns passthrough | `evals/eval_runner.py` | 0 |
| WP4 | Eval test counts + FP memory test class (5) | `tests/test_eval.py` | +4 |
| WP4 | Version bump 1.8.0 → 1.9.0 | `cold_eyes/__init__.py` | 0 |
| WP4 | CHANGELOG v1.9.0 entry | `CHANGELOG.md` | 0 |
| WP4 | `docs/roadmap.md` v1.9.0 section | `docs/roadmap.md` | 0 |

### Bugfix（stop hook 觸發時發現）

- **Import guard for memory module** — engine.py 和 policy.py 對 `cold_eyes.memory` 的 import 加上 `try/except ImportError` fallback。原因：部署到 `~/.claude/scripts/` 時若 memory.py 尚未同步，import 失敗會導致 stop hook infra failure。加 guard 後 FP memory 在 module 缺失時 graceful no-op。

### 驗證結果

- 525 tests passed（+56 from v1.8.0 的 469）
- Eval: 33/33 deterministic
- Lint (ruff): clean
- Coverage: 87%

### Commits

| Hash | 說明 |
|------|------|
| `8082f4e` | v1.9.0 Phase 5 commit + tag |

---

## 下次 Session 要做什麼

### 性價比計畫全部完成 — 下一步方向

Phase 1-5 全部完成。接下來有兩個方向可選：

#### 方向 A：Trust engineering Phase 2（外部證據）

依 `docs/roadmap.md` Phase 2：
- Release-by-release assurance notes
- Challenge set（adversarial cases）
- Incident / miss postmortem template
- Head-to-head comparison framework

#### 方向 B：實戰校準

- 在更多 repo 上跑 cold review，收集真實 override 數據
- 用真實數據檢驗 FP memory 效果
- 根據結果調整 min_count、last_days、ratio 門檻

### 注意事項

- FP memory 從 override history 讀取，歷史資料越多效果越好。新安裝時 history 為空，FP memory 無效果（graceful no-op）。
- `compute_category_baselines()` 用 `total_overrides * 3` 估算 total_reviews。如果實際 override 率遠高或遠低於 1/3，可能需要調整乘數或改用真實 total。
- Manifest ground_truth_summary 現在是 15/18。如果未來加 eval cases，要重新計算。
- 性價比計畫全文見 `C:\Users\kk789\Downloads\cold-eyes-reviewer_cost_effective_roadmap_extreme.md`。

## 環境變數

| 變數 | 預設 | 說明 |
|---|---|---|
| `COLD_REVIEW_MODE` | `block` | block / report / off |
| `COLD_REVIEW_MODEL` | `opus` | deep review 的 model |
| `COLD_REVIEW_SHALLOW_MODEL` | `sonnet` | shallow review 的 model |
| `COLD_REVIEW_MAX_TOKENS` | `12000` | diff 的 token 預算 |
| `COLD_REVIEW_CONTEXT_TOKENS` | `2000` | context section 的 token 預算（0=停用）|
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
