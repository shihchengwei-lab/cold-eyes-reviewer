# Cold Eyes Reviewer — 交接文件

## 現況

- **版本：** v1.8.0（master，pending commit，2026-04-12）
- **分支：** master
- **測試：** 469 passed（coverage ≥75%，門檻 75%）
- **部署：** 待同步（detector.py + engine.py + constants.py 更新）
- **版本訊號：** 待對齊
  - `__init__.py` = 1.8.0
  - CHANGELOG = v1.8.0
  - About = 待更新
  - pytest = 469 passed
  - tag = 待建
  - Release = 待建
- **CI：** 待跑
- **Lint：** 待跑
- **Eval：** 30/30 deterministic（待驗證）

## 架構

v1.8.0 新增 detector module（state/invariant + repo-specific），接入 deep review path。

```
cold-review.sh              （同 v1.7.0，無變更）
  └→ cold_eyes/cli.py       CLI entry → engine.py → 各模組

cold_eyes/
  detector.py                NEW — state signal detection + repo-type classifier + hint builder
  engine.py                  UPDATED — deep path 加入 detector hints（context 之後、prompt 之前）
  constants.py               UPDATED — DEPLOY_FILES 加入 detector.py
  schema.py                  （同 v1.7.0，無變更）
  review.py                  （同 v1.7.0，無變更）
  policy.py                  （同 v1.7.0，無變更）
  prompt.py                  （同 v1.7.0，無變更）
  triage.py                  （同 v1.7.0，無變更）
  context.py                 （同 v1.7.0，無變更）
  git.py                     （同 v1.7.0，無變更）
  （其餘模組同 v1.7.0）

cold-review-prompt.txt       （同 v1.7.0，無變更）
cold-review-prompt-shallow.txt （同 v1.6.0，無變更）

evals/
  cases/                     +3 state/invariant cases（30 total）
  manifest.json              UPDATED — counts + new cases
  baseline.json              （v1.4.1 baseline，仍相容）

docs/
  roadmap.md                 UPDATED — v1.8.0 section added
```

### Engine pipeline 流程

```
collect → filter → rank → triage → build_diff → [context] → [detector] → prompt → model → parse → calibrate → filter → policy
                          ^^^^^^^^                            ^^^^^^^^^^
                          skip/shallow/deep                   state signals
                                                              + repo-specific
                                                              focus hints
```

- `build_detector_hints()` 在 deep path 中 context 之後、prompt 之前執行
- State signals: 5 patterns — state_check, transition_call, fsm_pattern, rollback_pattern, state_assignment
- Repo classifier: 5 types — web_backend, sdk_library, db_data, infra_async, general
- 每種 repo type 有對應的 focus profile（3 targeted checks）
- Hints 是 regex-based pre-model analysis，不增加 model 成本

## 本次會話做了什麼（2026-04-12）

### 起點

接手 v1.7.0（`b67532b`，421 tests）。收尾 v1.7.0（commit + tag + push + deploy），然後執行性價比階段 4「State / Invariant Detector」。

### v1.7.0 收尾

| # | 做了什麼 | 結果 |
|---|---------|------|
| 1 | Tests + coverage | 421 passed, 85% coverage |
| 2 | Commit + tag `v1.7.0` | `b67532b` |
| 3 | Push to remote | master + tag |
| 4 | Deploy to `~/.claude/scripts/` | 驗證 version = 1.7.0 |

### Phase 4 執行

| # | 做了什麼 | 檔案 | 測試變化 |
|---|---------|------|---------|
| WP1 | State signal detector: 5 patterns, first-match ordering | `detector.py` | 0 |
| WP2 | Repo-type classifier: 5 types, score-based | `detector.py` | 0 |
| WP2 | 4 focus profiles: auth, contract, migration, concurrency | `detector.py` | 0 |
| WP1+2 | `build_detector_hints()`: combines state + repo hints | `detector.py` | 0 |
| WP1+2 | Engine wiring: deep path, between context and prompt | `engine.py` | 0 |
| WP1+2 | Outcome fields: repo_type, focus, signal_count | `engine.py` | 0 |
| WP1+2 | DEPLOY_FILES updated | `constants.py` | 0 |
| WP1+2 | Tests: signals (22) + repo (11) + focus (6) + integration (9) | `tests/test_detector.py` | +48 |
| WP3 | 3 eval cases: state-missing-precheck, partial-state-update, legitimate-state-change | `evals/cases/` | 0 |
| WP3 | Manifest updated (30 cases, TP=10, FN=4) | `evals/manifest.json` | 0 |
| WP3 | Eval test counts updated (27→30, TP 8→10, FN 3→4) | `tests/test_eval.py` | 0 |
| WP4 | `__init__.py` 1.7.0 → 1.8.0 | `cold_eyes/__init__.py` | 0 |
| WP4 | CHANGELOG v1.8.0 entry | `CHANGELOG.md` | 0 |
| WP4 | `docs/roadmap.md` v1.8.0 section | `docs/roadmap.md` | 0 |

### 驗證結果

- 469 tests passed（+48 from v1.7.0 的 421）
- Eval: 待 final run（30/30 expected）
- Lint: 待跑

---

## 下次 Session 要做什麼

### 收尾：六訊號對齊 + 部署

1. Coverage check（目標 ≥ 75%）
2. Lint (ruff)
3. Commit + Tag `v1.8.0` + push
4. CI 確認 Tests ✓ + Release ✓
5. 部署到 `~/.claude/scripts/`
6. GitHub About 更新（469 tests, state/invariant + repo-specific detectors）
7. 六訊號對齊確認

### 目標：性價比階段 5「False-Positive Memory」

依 `cold-eyes-reviewer_cost_effective_roadmap_extreme.md` 階段 5。核心效果：打掉體感噪音 — 記住被否決的誤報模式。

### WP1: Override pattern extraction

1. 從 history 中提取 `state: overridden` 的 pattern（path, category, claim 類型）
2. 實作 `extract_fp_patterns()` in new module
3. Tests

### WP2: FP memory integration

1. 把 FP patterns 注入 prompt（或 confidence calibration）
2. 與 calibrate_evidence() 整合
3. Tests

### WP3: Confidence / Abstain calibration enhancement

1. 對高誤報 pattern 提高 abstain 傾向
2. Per-detector confidence 基準
3. Tests

### WP4: Eval + 收尾

1. FP memory eval cases
2. Eval regression check
3. 版本 bump（1.8.0 → 1.9.0）
4. HANDOVER 重寫

### 注意事項

- Detector hints 不改 prompt 本體，而是在 diff 前面插入 hint blocks。這是設計選擇 — prompt 保持穩定，hints 按需出現。
- Repo-type classification 是 heuristic（regex on file paths），不是 ML。在 mixed-type repos 中可能不準確，但成本為零。
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

（同 v1.7.0，無新增 flags。Detector 自動在 deep path 啟用。）

## 已知問題

- Repo-type classification 是 file-path heuristic。混合型 repo（例如同時有 routes/ 和 models/）會取最高分的 type，可能不完美。
- Evidence calibration 對 old-format model output 的影響：high confidence 無 evidence → 降為 medium。這在 default confidence=medium 設定下不影響 block 行為，但 confidence=high 設定下會過濾掉這些 issues。這是設計行為。
