# Cold Eyes Reviewer — 交接文件

## 現況

- **版本：** v1.5.0（master，`5ebd884`，2026-04-12）
- **分支：** master
- **測試：** 346 passed（coverage 82%，門檻 75%）
- **部署：** `~/.claude/scripts/` 已同步（triage.py + constants/engine/history/__init__ 全部更新）
- **版本訊號：** 六訊號對齊
  - `__init__.py` = 1.5.0
  - CHANGELOG = v1.5.0
  - About = 346 tests
  - pytest = 346 passed
  - tag = v1.5.0
  - Release = v1.5.0（CI ✓）
- **CI：** Tests ✓ + Release ✓

## 架構

v1.5.0 新增 triage 層。

```
cold-review.sh              Stop hook shim
  └→ cold_eyes/cli.py       CLI entry → engine.py → 各模組

cold_eyes/
  triage.py                  NEW — classify_file_role() + classify_depth()
  constants.py               UPDATED — RISK_CATEGORIES (8 categories), DEPLOY_FILES +triage
  engine.py                  UPDATED — triage step between rank and build_diff
  history.py                 UPDATED — review_depth field in log entries
  （其餘模組同 v1.4.1）

evals/                       Evaluation framework（同 v1.4.1，無變更）
  eval_runner.py             deterministic / benchmark / sweep + regression_check()
  baseline.json              canonical baseline (24/24 pass, critical/medium)
  manifest.json              24 cases 分類索引（5 categories）
  cases/                     24 eval case fixtures

.github/workflows/test.yml  CI: pytest + deterministic eval + regression check

docs/
  roadmap.md                 UPDATED — Phase 1 marked complete, triage section added
  （其餘 docs 同 v1.4.1）
```

### Engine pipeline 流程

```
collect → filter → rank → triage → build_diff → prompt → model → parse → policy
                          ^^^^^^^^
                          NEW: skip/shallow/deep 三段式分流
```

- `review_depth=skip` → 直接回傳 skip（不 build diff、不 call model）
- `review_depth=shallow` → 目前走 deep 流程（佔位，留 hook 給未來 lighter model）
- `review_depth=deep` → 現有完整流程

## 本次會話做了什麼（2026-04-12）

### 起點

接手 v1.4.1（`77bb65b`，306 tests）。HANDOVER 指定：性價比階段 1「先砍浪費」— skip/shallow/deep 三段式分流。

### 執行

| # | 做了什麼 | 檔案 | 測試變化 | Commit |
|---|---------|------|---------|--------|
| WP1 | 加 `RISK_CATEGORIES`（8 structured risk categories）| `cold_eyes/constants.py` | 0 | `5ebd884` |
| WP1 | `DEPLOY_FILES` 加 `triage.py` | `cold_eyes/constants.py` | 0 | `5ebd884` |
| WP2 | 新增 `classify_file_role(path)` — 6 roles（test/docs/config/generated/migration/source）| `cold_eyes/triage.py` | 0 | `5ebd884` |
| WP2 | 新增 `classify_depth(files)` — rule-based skip/shallow/deep | `cold_eyes/triage.py` | 0 | `5ebd884` |
| WP3 | engine `run()` 加 triage step，skip 不進 model call | `cold_eyes/engine.py` | 0 | `5ebd884` |
| WP3 | outcome 加 `review_depth` + `why_depth_selected` 欄位 | `cold_eyes/engine.py` | 0 | `5ebd884` |
| WP3 | `log_to_history()` 加 `review_depth` 參數 + entry 欄位 | `cold_eyes/history.py` | 0 | `5ebd884` |
| WP4 | 新增 40 tests：file role (23), depth (15), engine integration (2) | `tests/test_triage.py` | +40 | `5ebd884` |
| WP5 | `__init__.py` 1.4.1 → 1.5.0 | `cold_eyes/__init__.py` | 0 | `5ebd884` |
| WP5 | CHANGELOG 加 v1.5.0 entry | `CHANGELOG.md` | 0 | `5ebd884` |
| WP5 | `docs/roadmap.md` Phase 1 marked complete + triage section | `docs/roadmap.md` | 0 | `5ebd884` |
| — | tag `v1.5.0` + push | — | 0 | tag |
| — | GitHub About 更新（346 tests, skip/shallow/deep triage）| — | 0 | — |
| — | 部署到 `~/.claude/scripts/` | — | 0 | — |

### 驗證結果

- 346 tests passed
- Deterministic eval: 24/24
- Regression check vs baseline: no regression, exit 0
- Lint (ruff): clean
- CI: Tests ✓, Release ✓

---

## 下次 Session 要做什麼

### 目標：性價比階段 2「Shallow 分化 + Context Retrieval」

依 `cold-eyes-reviewer_cost_effective_roadmap_extreme.md` 階段 2。核心效果：shallow 層用更短 prompt 或更輕 model（haiku），加 context retrieval 讓 deep 更精準。

### WP1: Shallow prompt / lighter model

讓 `review_depth=shallow` 走不同於 deep 的審查流程：

1. **Shallow prompt** — 新增 `cold-review-prompt-shallow.txt`（或 prompt.py 加 shallow variant）。精簡版，只看明顯問題（critical only），不做深度分析。
2. **Model 降級** — shallow 用 `haiku` 或 `sonnet`（可 config），deep 用現有 model。
3. **Engine 整合** — `review_depth=shallow` 走 shallow prompt + lighter model path。
4. **測試** — shallow path 用不同 prompt/model 的 integration test。

### WP2: Context retrieval for deep

為 deep 路徑加 context（提升精準度，減少 FP）：

1. **`cold_eyes/context.py`** — 新模組，從 git blame / recent commits / related files 提取上下文。
2. **Prompt 加 context section** — deep prompt 注入 context（最近修改者、相關檔案、commit message）。
3. **Token budget 分配** — diff + context 共用 token budget，context 佔比可設定。
4. **測試** — context extraction unit tests。

### WP3: 分流統計 + 調整

1. **Triage stats** — `quality-report` 加 triage 分布統計（skip/shallow/deep 比例）。
2. **閾值調整** — 根據實際 skip 率調整 classify_depth 規則。
3. **Eval 擴充** — 加 triage-specific eval cases（確認 skip 不漏掉真問題）。

### WP4: 收尾

1. Eval regression check
2. 版本 bump（1.5.0 → 1.6.0）
3. 更新 baseline（如果 eval 有變化）
4. HANDOVER 重寫

### 注意事項

- Shallow 分化是 engine 層改動，會影響 runtime hook 行為。部署後 shallow diff 會走不同 model。
- Context retrieval 會增加每次 deep review 的 git 呼叫量（blame + log），需注意效能。
- eval deterministic mode 直接呼叫 `_evaluate_case()`，不經過 `engine.run()`，所以 triage 不影響 eval 結果。
- 性價比計畫全文見 `C:\Users\kk789\Downloads\cold-eyes-reviewer_cost_effective_roadmap_extreme.md`。

## 環境變數

（同 v1.4.1，無變更）

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

（同 v1.4.1，無新增 CLI 命令。triage 是 engine 內部行為，不需 CLI flag。）

## 已知問題

- （同 v1.4.1，無新增）
