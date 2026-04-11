# Cold Eyes Reviewer — 交接文件

## 現況

- **版本：** v1.4.0（master，pending commit）
- **分支：** master
- **測試：** 303 passed（coverage 82%，門檻 75%）
- **部署：** `~/.claude/scripts/` 需手動同步（eval pipeline 是開發工具，不影響 runtime hook）
- **版本訊號：** `__init__.py` = 1.4.0 / CHANGELOG = v1.4.0 / 303 tests — 待 commit 後對齊 About + tag
- **CI：** 待 push 後確認

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
  evaluation.md              eval system 文件（已更新 24 cases + pipeline）
  （其餘 docs 同 v1.3.1）

SECURITY.md                  擴充 trust boundaries（6 小節 + 攻擊面表格）
```

## 本次會話做了什麼（2026-04-12）

### 起點

接手 v1.3.1（`70bc98b`，297 tests）。執行 HANDOVER 指定的 Phase 1 工具層 + v1.4.0 bump。

### 執行

| # | 做了什麼 | 檔案 | 測試變化 |
|---|---------|------|---------|
| WP2 | 加 `_make_report()` — 所有 mode 輸出包 envelope（version, timestamp, schema_version） | `evals/eval_runner.py` | 0 |
| WP2 | 加 `format_markdown()` — deterministic/sweep/benchmark → markdown table | `evals/eval_runner.py` | 0 |
| WP2 | 加 `save_report()` — 存 JSON + markdown 到 `evals/results/` | `evals/eval_runner.py` | 0 |
| WP2 | 加 `compare_reports()` — 比對兩份 report 差異 | `evals/eval_runner.py` | 0 |
| WP2 | CLI 加 `--save` / `--format` / `--compare` 三個 eval flag | `cold_eyes/cli.py` | 0 |
| WP5 | 加 6 tests：report metadata (2), markdown (2), compare (1), save (1) | `tests/test_eval.py` | +6 |
| WP6 | `__init__.py` 1.3.1 → 1.4.0 | `cold_eyes/__init__.py` | 0 |
| WP6 | CHANGELOG 加 v1.4.0 entry | `CHANGELOG.md` | 0 |
| WP6 | README eval section 更新（14→24, 加 --save/--compare 範例） | `README.md` | 0 |
| WP6 | docs/evaluation.md 更新（case count, categories, pipeline, trust-model 交叉引用） | `docs/evaluation.md` | 0 |
| — | `evals/results/` 加到 `.gitignore` | `.gitignore` | 0 |
| — | 修 `datetime.utcnow()` deprecation warning | `evals/eval_runner.py` | 0 |

### 驗證結果

- 303 tests passed（+6 from 297）
- Deterministic eval: 24/24
- Sweep: critical/medium F1=1.0

---

## 下次 Session 要做什麼

### 目標：Phase 2 — Regression Gate + CI Integration

### WP1: Regression Gate

在 `evals/eval_runner.py` 加：

1. **`regression_check(baseline_path, cases_dir)`** — 載入 baseline report，跑 deterministic，比對。如果有 regression（previously passing case now fails），回傳 `{"regressed": True, "details": [...]}`。
2. 整合到 CLI：`python cli.py eval --regression-check <baseline.json>` — exit code 1 on regression。

### WP2: CI Eval Job

在 `.github/workflows/test.yml` 加 eval step：

1. `python cold_eyes/cli.py eval --eval-mode deterministic` — 跑 deterministic eval，assert exit 0
2. `python cold_eyes/cli.py eval --eval-mode sweep` — 跑 sweep，驗證 F1 ≥ 0.95

### WP3: Baseline Management

1. 產出一份 baseline report，commit 到 `evals/baseline.json`
2. CI 跑 `--regression-check evals/baseline.json`
3. 文件化 baseline 更新流程（何時更新、如何更新）

### WP4: 收尾

1. GitHub About description — 更新 test count（303）
2. git tag `v1.4.0` + push（**CI 全綠後再打 tag**）
3. `HANDOVER.md` — 重寫

### 注意事項

- v1.4.0 tag 尚未打。本次 session commit + push 後等 CI 綠燈，再決定是否打 tag 或留給下次。
- `evals/results/` 已在 `.gitignore`，但 `evals/baseline.json` 應該進 repo（它是 regression gate 的 ground truth）。
- About description 需要手動在 GitHub web UI 更新（CLI `gh repo edit --description` 也行）。

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

eval 新增三個 flag：

```bash
python cold_eyes/cli.py eval --save                          # 存 report 到 evals/results/
python cold_eyes/cli.py eval --save --format both            # JSON + markdown
python cold_eyes/cli.py eval --save --compare prev.json      # 比對前版
```

## 已知問題

- （同 v1.3.1）
- v1.4.0 tag 尚未打，等 CI 全綠。
