# Cold Eyes Reviewer — 交接文件

## 現況

- **版本：** v1.7.0（master，pending commit，2026-04-12）
- **分支：** master
- **測試：** 421 passed（coverage TBD，門檻 75%）
- **部署：** 待同步（prompt + policy.py + constants.py + context.py + git.py + cold-review.sh + 全部更新）
- **版本訊號：** 待對齊
  - `__init__.py` = 1.7.0
  - CHANGELOG = v1.7.0
  - About = 待更新
  - pytest = 421 passed
  - tag = 待建
  - Release = 待建
- **CI：** 待跑
- **Lint：** ruff clean
- **Eval：** 27/27 deterministic，regression check pass（baseline v1.4.1 相容）

## 架構

v1.7.0 新增 evidence-bound claim schema + 四項 bugfix。

```
cold-review.sh              UPDATED — engine guard 改為 emit block JSON
  └→ cold_eyes/cli.py       CLI entry → engine.py → 各模組

cold_eyes/
  schema.py                  UPDATED — evidence/abstain 欄位 type validation
  review.py                  UPDATED — parse 設定 evidence 欄位 defaults
  policy.py                  UPDATED — calibrate_evidence() + 接入 apply_policy
  constants.py               UPDATED — regex narrowing（secrets_privacy, async_concurrency）
  git.py                     UPDATED — estimate_tokens()（CJK-aware），取代 UTF-8//4
  context.py                 UPDATED — 改用 estimate_tokens()
  prompt.py                  （同 v1.6.0，無變更）
  engine.py                  （同 v1.6.0，無變更）
  config.py                  （同 v1.6.0，無變更）
  triage.py                  （同 v1.6.0，無變更）
  （其餘模組同 v1.6.0）

cold-review-prompt.txt       UPDATED — evidence 原則 + 新欄位 schema
cold-review-prompt-shallow.txt （同 v1.6.0，無變更）

evals/
  cases/                     +3 evidence cases（27 total）
  manifest.json              UPDATED — evidence category + counts
  baseline.json              （v1.4.1 baseline，仍相容）

docs/
  roadmap.md                 UPDATED — v1.7.0 section added
```

### Engine pipeline 流程

```
collect → filter → rank → triage → build_diff → [context] → prompt → model → parse → calibrate → filter → policy
                          ^^^^^^^^                                             ^^^^^^^^^  ^^^^^^^^
                          skip/shallow/deep                                    evidence   confidence
                                                                               downgrade  hard gate
```

- `calibrate_evidence()` 在 confidence filter 之前執行
- Rule 1: `confidence=high` + 無 evidence → 降為 `medium`
- Rule 2: 有 `abstain_condition` → confidence -1 level

## 本次會話做了什麼（2026-04-12）

### 起點

接手 v1.6.0（`ea5205d`，382 tests → 修 bugfix 後 400 tests）。HANDOVER 指定：性價比階段 3「Evidence-Bound Claim Schema」。

### 前置修復

| # | 做了什麼 | 檔案 | 測試變化 |
|---|---------|------|---------|
| BF1 | Regex narrowing: `token(?!iz)`, `key(?!board\|…)`, `env(?!iron)`, `(?<!service[-_])worker` | `constants.py` | +12 |
| BF2 | `estimate_tokens()` ASCII//4 + CJK×1 | `git.py`, `context.py` | +6 |
| BF3 | README env var 表加 `SHALLOW_MODEL`, `CONTEXT_TOKENS` | `README.md` | 0 |
| BF4 | Engine guard emit block JSON（與 Python guard 一致）| `cold-review.sh` | 0 |

### Phase 3 執行

| # | 做了什麼 | 檔案 | 測試變化 |
|---|---------|------|---------|
| WP1 | Schema: evidence/falsify/validation/abstain type validation | `schema.py` | 0 |
| WP1 | Parse: 四欄位 defaults | `review.py` | 0 |
| WP1 | Deep prompt: evidence 原則 + output schema 擴充 | `cold-review-prompt.txt` | 0 |
| WP2 | `calibrate_evidence()`: no-evidence downgrade + abstain -1 | `policy.py` | 0 |
| WP2 | Wire into `apply_policy()` before confidence filter | `policy.py` | 0 |
| WP1+2 | Tests: schema (6) + parse (2) + calibrate (9) + policy integration (4) | `tests/test_evidence.py` | +21 |
| WP3 | 3 eval cases: evidence-with-chain, evidence-abstain-demotes, evidence-backward-compat | `evals/cases/` | 0 |
| WP3 | Manifest updated (27 cases, evidence category) | `evals/manifest.json` | 0 |
| WP3 | Existing test fixes: eval counts (24→27), category set, engine confidence test add evidence | `tests/test_eval.py`, `tests/test_engine.py` | 0 |
| WP4 | `__init__.py` 1.6.0 → 1.7.0 | `cold_eyes/__init__.py` | 0 |
| WP4 | CHANGELOG v1.7.0 entry | `CHANGELOG.md` | 0 |
| WP4 | `docs/roadmap.md` v1.7.0 section | `docs/roadmap.md` | 0 |

### 驗證結果

- 421 tests passed（+39 from v1.6.0 的 382）
- Deterministic eval: 27/27
- Regression check vs baseline: no regression, exit 0
- Lint (ruff): clean

---

## 下次 Session 要做什麼

### 收尾：六訊號對齊 + 部署

1. Coverage check（目標 ≥ 75%）
2. Tag `v1.7.0` + push
3. CI 確認 Tests ✓ + Release ✓
4. 部署到 `~/.claude/scripts/`
5. GitHub About 更新（421 tests, evidence-bound claims）
6. 六訊號對齊確認

### 目標：性價比階段 4「State / Invariant Detector」

依 `cold-eyes-reviewer_cost_effective_roadmap_extreme.md` 階段 4。核心效果：小規模專門化 — 針對 state 和 invariant 類別做特定偵測。

### WP1: State transition detector

1. 定義 state-related pattern（FSM、status enum、state machine）
2. Prompt 擴充：state transition consistency checks
3. Tests

### WP2: Repo-specific detector

1. 從 git history 學習 repo 的常見模式
2. 與 context.py 整合
3. Tests

### WP3: Eval 擴充

1. 加 state/invariant eval cases
2. 更新 baseline

### WP4: 收尾

1. Eval regression check
2. 版本 bump（1.7.0 → 1.8.0）
3. HANDOVER 重寫

### 注意事項

- Evidence calibration 已改變 confidence 語義：old-format responses（無 evidence）的 high confidence 會被降為 medium。這是設計行為，不是 regression。
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

（同 v1.6.0，無新增 flags）

## 已知問題

- Evidence calibration 對 old-format model output 的影響：high confidence 無 evidence → 降為 medium。這在 default confidence=medium 設定下不影響 block 行為，但 confidence=high 設定下會過濾掉這些 issues。這是設計行為。
