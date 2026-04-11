# Cold Eyes Reviewer — 交接文件

## 現況

- **版本：** v1.3.1（master，`b5b583b`，2026-04-12）
- **分支：** master
- **測試：** 297 passed（coverage 82%，門檻 75%）
- **部署：** `~/.claude/scripts/` 需手動同步（本次未改 runtime 程式碼，不急）
- **版本訊號：** `__init__.py` = 1.3.1 / CHANGELOG = v1.3.1 / About = 289 tests — **注意：test count 已從 289 增到 297，但版本未 bump，訊號暫不更新**
- **CI：** 等 `b5b583b` push 結果

## 架構

同 v1.3.1，無結構變更。

```
cold-review.sh              Stop hook shim
  └→ cold_eyes/cli.py       CLI entry → engine.py → 各模組

evals/                       Evaluation framework（本次主要變更區）
  eval_runner.py             deterministic / benchmark / sweep + validate_manifest()
  manifest.json              24 cases 分類索引（5 categories）
  schema.md                  case file 格式正式定義
  cases/                     24 eval case fixtures
    tp_* (8)                 true_positive — 應 block 的真實問題
    ok_* (4)                 acceptable — 應 pass 的正常變更
    fn_* (3)                 false_negative — 看起來危險但可接受
    stress_* (5)             stress — 邊界條件
    edge_* (4)               edge — CJK、unicode、空回應、config-only

docs/                        文件（本次新增 3 份）
  trust-model.md             能力邊界、信任屬性、已知缺口
  assurance-matrix.md        per-category 偵測能力、FP/FN 方向、scope 限制
  roadmap.md                 重寫為四階段 trust engineering plan
  （其餘 docs 同 v1.3.1）

SECURITY.md                  擴充 trust boundaries（6 小節 + 攻擊面表格）
```

## 本次會話做了什麼（2026-04-12）

### 起點

接手 v1.3.1（`fb6c846`，289 tests）。收到 `cold-eyes-reviewer-trust-roadmap.md`，四階段可信度工程 roadmap。本次執行 Phase 1 材料層。

### 執行

| # | 做了什麼 | 檔案 | 測試變化 | Commit |
|---|---------|------|---------|--------|
| WP1 | 新增 10 eval cases（fn×3, edge×4, tp×2, stress×1） | `evals/cases/` | 0 | `2f72ee3` |
| WP1 | 建立 manifest.json（24 cases, 5 categories） | `evals/manifest.json` | 0 | `2f72ee3` |
| WP1 | 建立 schema.md（case 格式正式定義） | `evals/schema.md` | 0 | `2f72ee3` |
| WP1 | 加 validate_manifest() 到 eval_runner.py | `evals/eval_runner.py` | 0 | `2f72ee3` |
| WP5 | 更新 test 斷言（14→24, 3→5 categories）+ 8 新 tests | `tests/test_eval.py` | +8 | `2f72ee3` |
| WP3 | 建立 trust-model.md | `docs/trust-model.md` | 0 | `b5b583b` |
| WP3 | 擴充 SECURITY.md trust boundaries | `SECURITY.md` | 0 | `b5b583b` |
| WP3 | 重寫 roadmap.md 為四階段 trust plan | `docs/roadmap.md` | 0 | `b5b583b` |
| WP4 | 建立 assurance-matrix.md | `docs/assurance-matrix.md` | 0 | `b5b583b` |

### 驗證結果

- 297 tests passed
- Deterministic eval: 24/24
- Sweep: critical/medium F1=1.0（推薦不變）

---

## 下次 Session 要做什麼

### 目標：完成 Phase 1 工具層 + 收尾，bump v1.4.0

### WP2: Eval Pipeline 強化

修改 `evals/eval_runner.py`，加四個函式：

1. **`_make_report(mode_result)`** — 所有 mode 輸出包 envelope：`cold_eyes_version`、`timestamp`、`eval_schema_version`。套在 `run_deterministic()`（line 130）、`threshold_sweep()`��`run_benchmark()` 的 return 上。

2. **`format_markdown(report)`** — deterministic → case table + category summary；sweep → precision/recall/F1 table。輸出 markdown string。

3. **`save_report(report, output_dir=None)`** — 預設存到 `evals/results/`，產出 `{mode}_{timestamp}.json` + `.md`。

4. **`compare_reports(report_a, report_b)`** — 比對兩份 report：cases added/removed/changed、pass/fail 差異、F1 變化。回傳 dict。

修改 `cold_eyes/cli.py` eval 區塊（line 96-105），加三個 CLI flag：

- `--save` — 存 report 到 `evals/results/`
- `--format json|markdown|both`（default: json）
- `--compare <path>` — 載入前版 report JSON 比對

### WP5 剩餘 Tests

加到 `tests/test_eval.py`：

- `TestReportMetadata` — deterministic/sweep report 含 `cold_eyes_version` + `timestamp`（~2 tests）
- `TestFormatMarkdown` — `format_markdown()` 對 deterministic 和 sweep 產出合理 markdown（~2 tests）
- `TestCompareReports` — 同一份 report 比對自己 → no changes（~1 test）
- `TestSaveReport` — 用 tmp_path 驗證檔案實際存出（~1 test）

### WP6: 訊號一致性 + Version Bump

1. `cold_eyes/__init__.py` — `1.3.1` → `1.4.0`
2. `CHANGELOG.md` — 加 v1.4.0 entry，寫清楚：24 eval cases、5 categories、trust-model.md、assurance-matrix.md、structured pipeline、297+ tests
3. `README.md` — eval section 更新（14→24 cases, 3→5 categories），加 trust-model.md / assurance-matrix.md 交叉引用
4. `docs/evaluation.md` — 更新 case count、category table、加 manifest 說明
5. GitHub About description — 更新 test count
6. `HANDOVER.md` — 重寫
7. git tag `v1.4.0` + push（**CI 全綠後再打 tag**，v1.3.1 教訓）

### 注意事項

- `_make_report()` 會改變 `run_deterministic()` 的回傳結構（多了 `cold_eyes_version`、`timestamp`、`eval_schema_version`），既有 test 中 `report["total"]` 等欄位不受影響（envelope 是 `**` 展開），但要確認無 strict equality assertions
- `evals/results/` 目錄需加到 `.gitignore`（eval 結果是 local artifact，不進 repo）
- Sweep 的 `test_recommended_defaults` assert `rec["f1"] == 1.0`，新 cases 都遵守 critical/medium 邊界，不會改變推薦結果
- 版本 bump 時跑一次六訊號驗證（`__init__`、About、CHANGELOG、pytest count、Release、tag）

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

（同 v1.3.1，下次 session 加 `--save` / `--format` / `--compare` 到 eval）

## 已知問題

- （同 v1.3.1）
- 版本訊號暫時不一致：test count 297 但 About/CHANGELOG 仍寫 289。下次 v1.4.0 bump 時統一更新。
