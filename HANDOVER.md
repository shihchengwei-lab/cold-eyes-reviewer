# Cold Eyes Reviewer — 交接文件

## 現況

- **版本：** v1.6.0（master，`dfd7ccb`，2026-04-12）
- **分支：** master
- **測試：** 382 passed（coverage 82%，門檻 75%）
- **部署：** `~/.claude/scripts/` 已同步（context.py + prompt-shallow.txt + 全部更新）
- **版本訊號：** 六訊號對齊
  - `__init__.py` = 1.6.0
  - CHANGELOG = v1.6.0
  - About = 382 tests
  - pytest = 382 passed
  - tag = v1.6.0
  - Release = v1.6.0（CI ✓）
- **CI：** Tests ✓ + Release ✓
- **Lint：** ruff clean
- **Eval：** 24/24 deterministic，regression check pass（baseline v1.4.1 相容）

## 架構

v1.6.0 新增 shallow 分化 + context retrieval。

```
cold-review.sh              Stop hook shim
  └→ cold_eyes/cli.py       CLI entry → engine.py → 各模組

cold_eyes/
  context.py                 NEW — build_context() from git log + co-changed files
  prompt.py                  UPDATED — build_prompt_text(depth=) selects template
  constants.py               UPDATED — PROMPT_TEMPLATE_SHALLOW, DEPLOY_FILES +context/prompt
  engine.py                  UPDATED — shallow model/prompt, context injection for deep
  config.py                  UPDATED — shallow_model, context_tokens in policy keys
  cli.py                     UPDATED — --shallow-model, --context-tokens flags
  history.py                 UPDATED — by_review_depth in quality_report()
  triage.py                  （同 v1.5.0，無變更）
  （其餘模組同 v1.5.0）

cold-review-prompt-shallow.txt  NEW — critical-only 輕量 prompt

evals/                       （同 v1.5.0，無變更）
  baseline.json              canonical baseline (24/24 pass, critical/medium)

docs/
  roadmap.md                 UPDATED — v1.6.0 section added
```

### Engine pipeline 流程

```
collect → filter → rank → triage → build_diff → [context] → prompt → model → parse → policy
                          ^^^^^^^^   ^^^^^^^^^^
                          skip/shallow/deep    deep 加 context injection
```

- `review_depth=skip` → 直接回傳 skip（不 build diff、不 call model）
- `review_depth=shallow` → shallow prompt + shallow_model（default: sonnet）
- `review_depth=deep` → full prompt + main model + context injection

## 本次會話做了什麼（2026-04-12）

### 起點

接手 v1.5.0（`5ebd884`，346 tests）。HANDOVER 指定：性價比階段 2「Shallow 分化 + Context Retrieval」。

### 執行

| # | 做了什麼 | 檔案 | 測試變化 |
|---|---------|------|---------|
| WP1 | 新增 `cold-review-prompt-shallow.txt`（critical-only prompt）| `cold-review-prompt-shallow.txt` | 0 |
| WP1 | `build_prompt_text(depth=)` 支援 shallow/deep 選擇 | `cold_eyes/prompt.py` | 0 |
| WP1 | `PROMPT_TEMPLATE_SHALLOW` 常數 + DEPLOY_FILES 更新 | `cold_eyes/constants.py` | 0 |
| WP1 | Engine shallow 走不同 model + prompt（不再 fallthrough）| `cold_eyes/engine.py` | 0 |
| WP1 | `shallow_model` policy key + `COLD_REVIEW_SHALLOW_MODEL` env var | `cold_eyes/config.py`, `engine.py` | 0 |
| WP1 | CLI `--shallow-model` flag | `cold_eyes/cli.py` | 0 |
| WP1 | 13 tests：shallow prompt (10) + engine model selection (3) | `tests/test_shallow_and_context.py` | +13 |
| WP2 | 新增 `cold_eyes/context.py`（recent commits + co-changed files）| `cold_eyes/context.py` | 0 |
| WP2 | Engine deep path context injection（prepend to diff）| `cold_eyes/engine.py` | 0 |
| WP2 | `context_tokens` policy key + `COLD_REVIEW_CONTEXT_TOKENS` env var | `cold_eyes/config.py`, `engine.py` | 0 |
| WP2 | CLI `--context-tokens` flag | `cold_eyes/cli.py` | 0 |
| WP2 | 12 tests：context retrieval (9) + engine integration (3) | `tests/test_shallow_and_context.py` | +12 |
| WP3 | `by_review_depth` 加入 quality_report() | `cold_eyes/history.py` | 0 |
| WP3 | 11 tests：triage safety (9) + quality-report triage (2) | `tests/test_triage.py`, `test_engine.py` | +11 |
| WP4 | `__init__.py` 1.5.0 → 1.6.0 | `cold_eyes/__init__.py` | 0 |
| WP4 | CHANGELOG 加 v1.6.0 entry | `CHANGELOG.md` | 0 |
| WP4 | `docs/roadmap.md` v1.6.0 section added | `docs/roadmap.md` | 0 |

### 驗證結果

- 382 tests passed
- Deterministic eval: 24/24
- Regression check vs baseline: no regression, exit 0
- Lint (ruff): clean

---

## 下次 Session 要做什麼

### 目標：性價比階段 3「Evidence-Bound Claim Schema」

依 `cold-eyes-reviewer_cost_effective_roadmap_extreme.md` 階段 3。核心效果：把 reviewer 輸出從「講評論」變成「提出可檢查 claim」。

### WP1: Evidence-bound issue schema

每個 issue 加上可驗證的 evidence chain：

1. **Schema 擴充** — issue 新增 `evidence`（list of strings）、`what_would_falsify_this`、`suggested_validation` 欄位。
2. **Prompt 更新** — deep prompt 要求 evidence chain。issue 沒有 evidence 應降權或不輸出。
3. **Parse 更新** — `parse_review_output()` 接受新欄位（optional，向下相容）。
4. **Policy 整合** — 沒有 evidence 的 high-confidence issue 降為 medium。
5. **測試** — schema validation、parse、policy 降權。

### WP2: Abstain / falsifier calibration

讓 reviewer 明確表達不確定性：

1. **Abstain condition** — issue 加 `abstain_condition` 欄位（什麼情況下這個 claim 不成立）。
2. **Prompt 更新** — 「需要假設隱藏 context 才成立的 claim，應降低 confidence」。
3. **Policy 整合** — 有 abstain_condition 的 issue 自動 -1 confidence level。
4. **測試** — abstain calibration。

### WP3: Eval 擴充

1. 加 evidence-bound eval cases（issue 有/無 evidence 的 ground truth）。
2. 更新 baseline。

### WP4: 收尾

1. Eval regression check
2. 版本 bump（1.6.0 → 1.7.0）
3. HANDOVER 重寫

### 注意事項

- Evidence schema 是 prompt 層改動。現有 eval cases 的 mock_response 不含新欄位，向下相容靠 parse 的 optional handling。
- Abstain calibration 會改 policy.py 的 confidence 邏輯，需仔細測試不影響現有 eval 結果。
- 性價比計畫全文見 `C:\Users\kk789\Downloads\cold-eyes-reviewer_cost_effective_roadmap_extreme.md`。

## 環境變數

| 變數 | 預設 | 說明 |
|---|---|---|
| `COLD_REVIEW_MODE` | `block` | block / report / off |
| `COLD_REVIEW_MODEL` | `opus` | deep review 的 model |
| `COLD_REVIEW_SHALLOW_MODEL` | `sonnet` | **NEW** — shallow review 的 model |
| `COLD_REVIEW_MAX_TOKENS` | `12000` | diff 的 token 預算 |
| `COLD_REVIEW_CONTEXT_TOKENS` | `2000` | **NEW** — context section 的 token 預算（0=停用）|
| `COLD_REVIEW_BLOCK_THRESHOLD` | `critical` | 擋的 severity 門檻 |
| `COLD_REVIEW_CONFIDENCE` | `medium` | confidence 硬過濾門檻 |
| `COLD_REVIEW_LANGUAGE` | `繁體中文（台灣）` | 輸出語言 |
| `COLD_REVIEW_SCOPE` | `working` | diff 範圍 |
| `COLD_REVIEW_BASE` | 未設 | pr-diff scope 的 base branch |
| `COLD_REVIEW_TRUNCATION_POLICY` | `warn` | warn / soft-pass / fail-closed |

## CLI 命令

新增 flags：
- `--shallow-model <model>` — shallow review 用的 model
- `--context-tokens <int>` — context 的 token 預算

## 已知問題

- （同 v1.5.0，無新增）
