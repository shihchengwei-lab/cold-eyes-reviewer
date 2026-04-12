# Cold Eyes Reviewer — 交接文件

## 現況

- **版本：** v1.4.1（master，`fa01dfc`，2026-04-12）
- **分支：** master
- **測試：** 306 passed（coverage 82%，門檻 75%）
- **部署：** `~/.claude/scripts/` 需手動同步（本次加了 regression_check，不影響 runtime hook）
- **版本訊號：** 六訊號對齊中（CI running）
  - `__init__.py` = 1.4.1
  - CHANGELOG = v1.4.1
  - About = 306 tests
  - pytest = 306 passed
  - tag = v1.4.1
  - Release = v1.4.1（CI running）
- **CI：** Tests + Release 均已 trigger，等待結果

## 架構

同 v1.4.0 核心，regression gate 擴充。

```
cold-review.sh              Stop hook shim
  └→ cold_eyes/cli.py       CLI entry → engine.py → 各模組

evals/                       Evaluation framework
  eval_runner.py             deterministic / benchmark / sweep + validate_manifest()
                             + _make_report() / format_markdown() / save_report() / compare_reports()
                             + regression_check()  ← NEW
  baseline.json              canonical baseline (24/24 pass, critical/medium)  ← NEW
  manifest.json              24 cases 分類索引（5 categories）
  schema.md                  case file 格式正式定義
  cases/                     24 eval case fixtures
    tp_* (8)                 true_positive — 應 block 的真實問題
    ok_* (4)                 acceptable — 應 pass 的正常變更
    fn_* (3)                 false_negative — 看起來危險但可接受
    stress_* (5)             stress — 邊界條件
    edge_* (4)               edge — CJK、unicode、空回應、config-only
  results/                   （.gitignore'd）eval report 輸出目錄

.github/workflows/test.yml  CI: pytest + deterministic eval + regression check  ← UPDATED

docs/                        文件
  evaluation.md              eval system 文件（含 baseline management）← UPDATED
  trust-model.md             能力邊界、信任屬性、已知缺口
  assurance-matrix.md        per-category 偵測能力、FP/FN 方向、scope 限制
  roadmap.md                 四階段 trust engineering plan
  （其餘 docs 同 v1.4.0）

SECURITY.md                  擴充 trust boundaries（6 小節 + 攻擊面表格）
```

## 本次會話做了什麼（2026-04-12）

### 起點

接手 v1.4.0（`f1e81aa`，303 tests）。HANDOVER 指定：Phase 2 — Regression Gate + CI Integration。

### 執行

| # | 做了什麼 | 檔案 | 測試變化 | Commit |
|---|---------|------|---------|--------|
| WP1 | 加 `regression_check(baseline_path, cases_dir)` — 載入 baseline，跑 deterministic，用 compare_reports 比對，回傳 regressed/regressions | `evals/eval_runner.py` | 0 | `fa01dfc` |
| WP1 | CLI 加 `--regression-check <baseline.json>` — exit 1 on regression | `cold_eyes/cli.py` | 0 | `fa01dfc` |
| WP2 | 產出 baseline（24/24 pass），commit 到 `evals/baseline.json` | `evals/baseline.json` | 0 | `fa01dfc` |
| WP2 | `docs/evaluation.md` 加 regression gate + baseline management 章節 | `docs/evaluation.md` | 0 | `fa01dfc` |
| WP3 | CI 加 deterministic eval + regression check steps | `.github/workflows/test.yml` | 0 | `fa01dfc` |
| WP4 | 加 3 tests：baseline vs self (1), action change not regression (1), regression detected with high confidence (1) | `tests/test_eval.py` | +3 | `fa01dfc` |
| WP5 | `__init__.py` 1.4.0 → 1.4.1 | `cold_eyes/__init__.py` | 0 | `fa01dfc` |
| WP5 | CHANGELOG 加 v1.4.1 entry | `CHANGELOG.md` | 0 | `fa01dfc` |
| — | tag `v1.4.1` + push | — | 0 | tag |
| — | GitHub About 更新（306 tests） | — | 0 | — |

### 驗證結果

- 306 tests passed
- Deterministic eval: 24/24
- Regression check vs baseline: no regression, exit 0
- Lint (ruff): clean
- CI: triggered, pending

---

## 下次 Session 要做什麼

### 目標：Phase 3 — Eval Expansion + Threshold Tuning

### WP1: 擴充 eval corpus

目前 24 cases 涵蓋 5 categories。擴充方向：

1. **Real-world false positives** — 從實際使用中收集被 block 但應該 pass 的 case，加入 `acceptable` 或新增 `false_positive` category。
2. **Multi-file diffs** — 目前所有 case 都是單檔案 diff。加 2-3 個跨檔案 case 測試 ranking + truncation 互動。
3. **Language-specific patterns** — 加 Go、Rust、TypeScript 的 case（目前偏 Python/JS）。

### WP2: Sweep 分析 + 閾值報告

1. 擴充 corpus 後重跑 sweep，記錄 F1 變化。
2. 如果 F1 下降，用 `--compare` 找出哪些 case 導致退化。
3. 產出 threshold tuning 報告更新 `docs/evaluation.md`。

### WP3: Benchmark mode 整合

1. 用 `--eval-mode benchmark --model sonnet` 跑一次真實 model eval。
2. 比對 deterministic（mock）vs benchmark（real model）差異。
3. 如果 model accuracy 有落差，調整 mock responses 使 deterministic 更貼近真實行為。

### WP4: 收尾

1. 更新 baseline（`evals/baseline.json`）反映新 cases。
2. 版本 bump 視變更幅度決定。
3. `HANDOVER.md` 重寫。

### 注意事項

- 擴充 corpus 時記得同步更新 `evals/manifest.json`（`validate_manifest()` 會檢查一致性）。
- 加新 case 後跑 `--regression-check evals/baseline.json` 會顯示 `cases_added`，但不算 regression。更新 baseline 後才會歸零。
- Benchmark mode 需要 Claude CLI 安裝且有 API access。

## 環境變數

（同 v1.4.0，無變更）

| 變數 | 預設 | 說明 |
|---|---|---|
| `COLD_REVIEW_MODE` | `block` | block / report / off |
| `COLD_REVIEW_MODEL` | `opus` | opus / sonnet / haiku |
| `COLD_REVIEW_MAX_TOKENS` | `12000` | diff 的 token 預算 |
| `COLD_REVIEW_BLOCK_THRESHOLD` | `critical` | 擋的 severity 門檻 |
| `COLD_REVIEW_CONFIDENCE` | `medium` | confidence 硬過濾門檻 |
| `COLD_REVIEW_LANGUAGE` | `繁體中文（台灣）` | 輸出語言 |
| `COLD_REVIEW_SCOPE` | `working` | diff 範圍 |
| `COLD_REVIEW_BASE` | 未設 | pr-diff scope 的 base branch |
| `COLD_REVIEW_TRUNCATION_POLICY` | `warn` | warn / soft-pass / fail-closed |

## CLI 命令

v1.4.1 新增：

```bash
# Regression check — exit 1 on regression, 0 on success
python cold_eyes/cli.py eval --regression-check evals/baseline.json
```

v1.4.0 eval flags（仍可用）：

```bash
python cold_eyes/cli.py eval --save                          # 存 report 到 evals/results/
python cold_eyes/cli.py eval --save --format both            # JSON + markdown
python cold_eyes/cli.py eval --save --compare prev.json      # 比對前版
```

## 已知問題

- （同 v1.4.0，無新增）
