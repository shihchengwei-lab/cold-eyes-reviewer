# Cold Eyes Reviewer — 交接文件

## 現況

- **版本：** v1.4.0（master，`0f7d1cd`，2026-04-12）
- **分支：** master
- **測試：** 303 passed（coverage 82%，門檻 75%）
- **部署：** `~/.claude/scripts/` 需手動同步（本次加了 eval pipeline 函式，不影響 runtime hook）
- **版本訊號：** 六訊號全對齊 ✓
  - `__init__.py` = 1.4.0
  - CHANGELOG = v1.4.0
  - About = 303 tests
  - pytest = 303 passed
  - tag = v1.4.0
  - Release = v1.4.0（workflow success）
- **CI：** Tests + Release 均 success

## 架構

同 v1.3.1 核心，eval pipeline 擴充。

```
cold-review.sh              Stop hook shim
  └→ cold_eyes/cli.py       CLI entry → engine.py → 各模組

evals/                       Evaluation framework
  eval_runner.py             deterministic / benchmark / sweep + validate_manifest()
                             + _make_report() / format_markdown() / save_report() / compare_reports()
  manifest.json              24 cases 分類索引（5 categories）
  schema.md                  case file 格式正式定義
  cases/                     24 eval case fixtures
    tp_* (8)                 true_positive — 應 block 的真實問題
    ok_* (4)                 acceptable — 應 pass 的正常變更
    fn_* (3)                 false_negative — 看起來危險但可接受
    stress_* (5)             stress — 邊界條件
    edge_* (4)               edge — CJK、unicode、空回應、config-only
  results/                   （.gitignore'd）eval report 輸出目錄

docs/                        文件
  trust-model.md             能力邊界、信任屬性、已知缺口
  assurance-matrix.md        per-category 偵測能力、FP/FN 方向、scope 限制
  roadmap.md                 四階段 trust engineering plan
  evaluation.md              eval system 文件（24 cases + pipeline）
  （其餘 docs 同 v1.3.1）

SECURITY.md                  擴充 trust boundaries（6 小節 + 攻擊面表格）
```

## 本次會話做了什麼（2026-04-12）

### 起點

接手 v1.3.1（`70bc98b`，297 tests）。HANDOVER 指定：Phase 1 工具層 + bump v1.4.0。

### 執行

| # | 做了什麼 | 檔案 | 測試變化 | Commit |
|---|---------|------|---------|--------|
| WP2 | 加 `_make_report()` — 所有 mode 輸出包 envelope（version, timestamp, schema_version） | `evals/eval_runner.py` | 0 | `0f7d1cd` |
| WP2 | 加 `format_markdown()` — deterministic/sweep/benchmark → markdown table | `evals/eval_runner.py` | 0 | `0f7d1cd` |
| WP2 | 加 `save_report()` — 存 JSON + markdown 到 `evals/results/` | `evals/eval_runner.py` | 0 | `0f7d1cd` |
| WP2 | 加 `compare_reports()` — 比對兩份 report 差異（cases added/removed/changed, F1 delta） | `evals/eval_runner.py` | 0 | `0f7d1cd` |
| WP2 | CLI 加 `--save` / `--format json|markdown|both` / `--compare <path>` | `cold_eyes/cli.py` | 0 | `0f7d1cd` |
| WP5 | 加 6 tests：ReportMetadata(2), FormatMarkdown(2), CompareReports(1), SaveReport(1) | `tests/test_eval.py` | +6 | `0f7d1cd` |
| WP6 | `__init__.py` 1.3.1 → 1.4.0 | `cold_eyes/__init__.py` | 0 | `0f7d1cd` |
| WP6 | CHANGELOG 加 v1.4.0 entry（含前次 session 的 corpus + docs 變更） | `CHANGELOG.md` | 0 | `0f7d1cd` |
| WP6 | README eval section 更新（14→24, --save/--compare 範例, trust-model 引用） | `README.md` | 0 | `0f7d1cd` |
| WP6 | docs/evaluation.md 更新（5 categories, manifest, pipeline, trust-model 交叉引用） | `docs/evaluation.md` | 0 | `0f7d1cd` |
| — | `evals/results/` 加到 `.gitignore` | `.gitignore` | 0 | `0f7d1cd` |
| — | 修 `datetime.utcnow()` deprecation → `datetime.now(timezone.utc)` | `evals/eval_runner.py` | 0 | `0f7d1cd` |
| — | tag `v1.4.0` + push | — | 0 | tag |
| — | GitHub About 更新（303 tests） | — | 0 | — |

### 驗證結果

- 303 tests passed
- Deterministic eval: 24/24
- Sweep: critical/medium F1=1.0
- CI Tests: success
- CI Release: success
- 六訊號全對齊

---

## 下次 Session 要做什麼

### 目標：Phase 2 — Regression Gate + CI Integration

### WP1: Regression Gate

修改 `evals/eval_runner.py`，加一個函式：

**`regression_check(baseline_path, cases_dir)`** — 載入 baseline report JSON，跑 `run_deterministic()`，用 `compare_reports()` 比對。如果有 regression（previously passing case now fails），回傳 `{"regressed": True, "details": [...]}`。無 regression 回傳 `{"regressed": False}`。

整合到 CLI（`cold_eyes/cli.py`）：
- `python cli.py eval --regression-check <baseline.json>` — 跑 deterministic + 比對 baseline，exit code 1 on regression。

### WP2: Baseline 建立

1. 跑一次 `python cli.py eval --save --format json`，產出 baseline。
2. 將 baseline commit 到 `evals/baseline.json`（這個檔案進 repo，不受 `.gitignore` 影響）。
3. 在 `docs/evaluation.md` 加 baseline 管理流程說明。

### WP3: CI Eval Job

在 `.github/workflows/test.yml` 加 eval step：

1. `python cold_eyes/cli.py eval --eval-mode deterministic` — assert exit 0
2. `python cold_eyes/cli.py eval --regression-check evals/baseline.json` — assert exit 0
3. `python cold_eyes/cli.py eval --eval-mode sweep` — 可選，驗證 F1 ≥ threshold

### WP4: Tests

加到 `tests/test_eval.py`：
- `TestRegressionCheck` — baseline 比自己 → no regression；人造 regression → detected（~2-3 tests）

### WP5: 收尾

1. 版本是否 bump 視變更幅度決定（如果只加 CI config 不改 runtime code，可能不 bump）
2. `HANDOVER.md` 重寫

### 注意事項

- `evals/baseline.json` 應進 repo（它是 regression gate 的 ground truth），與 `evals/results/`（gitignored）不同。
- CI eval step 不需要 model calls — deterministic mode 用 mock responses。
- `regression_check()` 可以重用 `compare_reports()` 的 `cases_changed` 欄位判斷 regression 方向（match true→false = regression）。

## 環境變數

（同 v1.3.1，無變更）

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

v1.4.0 新增的 eval flags：

```bash
python cold_eyes/cli.py eval --save                          # 存 report 到 evals/results/
python cold_eyes/cli.py eval --save --format both            # JSON + markdown
python cold_eyes/cli.py eval --save --compare prev.json      # 比對前版
```

## 已知問題

- （同 v1.3.1，無新增）
