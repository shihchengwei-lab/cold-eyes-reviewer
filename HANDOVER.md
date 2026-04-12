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

### 目標：性價比極限版 — 階段 1「先砍浪費」

依 `cold-eyes-reviewer_cost_effective_roadmap_extreme.md` 的五階段計畫，下一輪做階段 1：Skip / Shallow / Deep 三段式分流 + 風險分類 + 檔案角色。核心效果：不值得審的 diff 不進 model call，降低 token 成本 + latency + 誤報量。

### WP1: 風險分類 + 檔案角色常數

在 `cold_eyes/constants.py` 擴充：

1. **風險類別**（risk categories）— 取代現有單一 `RISK_PATTERN`：
   - `auth_permission` — auth, permission, guard, middleware, policy, ownership
   - `state_invariant` — state, status, transition, workflow, FSM
   - `migration_schema` — migration, schema, DDL, ALTER
   - `persistence` — db, database, repository, ORM, query
   - `public_api` — api, endpoint, route, handler, controller
   - `async_concurrency` — async, await, thread, lock, mutex, queue, worker
   - `secrets_privacy` — secret, credential, token, password, key, env
   - `cache_retry` — cache, retry, timeout, circuit-breaker

2. **檔案角色**（file roles）：
   - `test` — tests/, test_, _test.py, spec/
   - `docs` — *.md, docs/, README, CHANGELOG
   - `config` — *.yml, *.yaml, *.toml, *.json (root-level), .env*
   - `generated` — *.min.js, *.min.css, *.pb.go, *_generated.*, dist/
   - `migration` — migrations/, alembic/, **/migrate/**
   - `source` — everything else

### WP2: 分流模組 `cold_eyes/triage.py`

新增模組，兩個函式：

**`classify_file_role(path) → str`**
- 用路徑 + 副檔名判斷角色
- 回傳：`test` / `docs` / `config` / `generated` / `migration` / `source`

**`classify_depth(files, diff_meta) → dict`**
- 輸入：ranked file list + diff metadata（size, file roles, touched keywords）
- 輸出：`{"review_depth": "skip|shallow|deep", "why_depth_selected": "...", "risk_types": [...]}`
- 規則（rule-based，不用 model）：
  - **Skip**：所有檔案角色 = docs / generated / config-only（無 secrets 關鍵字）
  - **Shallow**：所有檔案角色 = test / 非關鍵模組小 diff（< 50 行）且無 risk category 命中
  - **Deep**：任何檔案命中 risk category，或 diff > 閾值，或包含 migration / source 的非小改動

### WP3: Engine 整合

修改 `cold_eyes/engine.py` 的 `run()` 流程：

```
collect → filter → rank → **triage** → build_diff → prompt → model → parse → policy
```

- `review_depth=skip` → 直接回傳 skip 結果（不 build diff、不 call model）
- `review_depth=shallow` → 目前先走 deep 流程（留 hook 給未來 shallow prompt / lighter model）
- `review_depth=deep` → 現有完整流程
- 在 outcome 加 `review_depth` 和 `why_depth_selected` 欄位
- History 紀錄 `review_depth`

### WP4: Tests

在 `tests/test_triage.py`（新檔案）：

- `TestClassifyFileRole` — 每種角色至少 2 個路徑（~12 tests）
- `TestClassifyDepth` — skip / shallow / deep 各 2-3 個場景（~8 tests）
- `TestEngineTriageIntegration` — engine skip path 不 call model（~2 tests）

### WP5: Eval + 收尾

1. 現有 24 eval cases 應全部走 deep（它們都有 mock_response，triage 不影響）
2. 如果 triage 改變了 engine 行為，需要確認 regression check 仍然 pass
3. 版本 bump（1.4.1 → 1.5.0，因為是 feature addition）
4. 更新 `docs/roadmap.md` — 標記階段 1 完成
5. `HANDOVER.md` 重寫

### 注意事項

- 分流是 engine 層的改動，會影響 runtime hook 行為。部署到 `~/.claude/scripts/` 後 skip 分流立即生效。
- eval deterministic mode 直接呼叫 `_evaluate_case()`，不經過 `engine.run()`，所以 triage 不會影響 eval 結果。
- `classify_depth()` 只看檔案清單 + diff metadata，不讀檔案內容（成本為零）。
- Shallow 層目前 = deep（佔位），未來階段 2 加 context retrieval 時才會分化。
- 性價比計畫全文見 `C:\Users\kk789\Downloads\cold-eyes-reviewer_cost_effective_roadmap_extreme.md`。

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
