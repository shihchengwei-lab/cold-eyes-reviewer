# Cold Eyes Reviewer — 交接文件

## 現況

- **版本：** v1.11.6（master `300327a`，已 push，tag 已打）
- **分支：** master
- **測試：** 776 passed / 0 failed
- **CI：** `300327a` 全矩陣綠（ubuntu/macos/windows × py 3.10/3.12）
- **部署：** `~/.claude/scripts/cold_eyes/{context.py, review.py, __init__.py}` 已同步
- **版本訊號：**
  - `__init__.py` = `1.11.6`
  - CHANGELOG 最新條目 = `v1.11.6 — fix: tolerate claude CLI multi-object JSON stdout`
  - pyproject description = `"Diff-centered second-pass review gate for Claude Code"`
  - GitHub About = §1.2 定位句（239 字元，已套用）
  - GitHub topics = 7 項（`claude-code` / `review-gate` / `git-hooks` / `code-quality` / `llm-guardrails` / `developer-tools` / `second-pass-review`）
  - README badges = Tests + Stop-hook + diff-centered + not full review
  - tag `v1.11.4` / `v1.11.5` / `v1.11.6` = 都已打、已推
  - release v1.11.4 = https://github.com/shihchengwei-lab/cold-eyes-reviewer/releases/tag/v1.11.4
  - release v1.11.5 = https://github.com/shihchengwei-lab/cold-eyes-reviewer/releases/tag/v1.11.5
  - release v1.11.6 = https://github.com/shihchengwei-lab/cold-eyes-reviewer/releases/tag/v1.11.6

## 本次會話做了什麼（2026-04-18，Session 8 — 補完 v1.11.6 release）

### 起點

外部（另一個 project 的）agent 已在本 repo 提交 v1.11.6 runtime fix，但 **沒打 tag、沒發 release、沒更新 HANDOVER**。git log 呈現 revert→reapply 鋸齒：

```
300327a Reapply "fix: tolerate claude CLI multi-object JSON stdout (v1.11.6)"
29ba4ea Revert "fix: tolerate claude CLI multi-object JSON stdout (v1.11.6)"
66a4e4d fix: tolerate claude CLI multi-object JSON stdout (v1.11.6)
```

接手時狀態：`__init__.py` = `1.11.6`、CHANGELOG 已有 v1.11.6 條目、CI 全綠（三個 commit 都 success）、deploy 目錄 `~/.claude/scripts/cold_eyes/{context.py, review.py, __init__.py}` 與 repo `diff -q` 無差異。缺的只是 tag + release + HANDOVER 同步。

### v1.11.6 修法摘要

`cold_eyes/review.py` 的 `parse_review_output()` 原本對 `claude --output-format json` stdout 直接 `json.loads()`。CLI 有時會先吐 `{"type":"system","subtype":"init",...}` preamble 再吐 `{"type":"result",...}` payload，`json.loads()` raise `Extra data: line 3 column 1 (char N)` → 被分類為 parse error → `infra_failed`，block 模式下卡 Stop hook。新 helper `_extract_result_object()` 用 `json.JSONDecoder.raw_decode()` 走 top-level objects，挑 `type=="result"`（或帶 `result` 欄位）的那個，fallback 到最後一個。單 JSON 路徑不動。

檔案：`cold_eyes/review.py` +30/-1、`tests/test_engine.py` +31（新增 2 test case：multi-object preamble + single JSON 兼容）、`cold_eyes/__init__.py` 1.11.5→1.11.6、CHANGELOG v1.11.6 條目。

### Commits 表

| # | Hash | 主題 | Session |
|---|---|---|---|
| 1 | `66a4e4d` | fix: v1.11.6 初版 | 外部 agent |
| 2 | `29ba4ea` | Revert v1.11.6 | 外部 agent |
| 3 | `300327a` | Reapply v1.11.6 | 外部 agent |
| 4 | （無 commit）| tag `v1.11.6` @ `300327a` + push + GH release | 本 session |

### 驗收

- pytest 776 passed（v1.11.5 = 774 → +2 新 test）
- `python -c "import cold_eyes; print(cold_eyes.__version__)"` → `1.11.6`
- `gh release list` top = `v1.11.6 (Latest)`
- `git ls-remote --tags origin | grep v1.11.6` → `300327a...refs/tags/v1.11.6`
- CI 三個 v1.11.6 相關 run（fix / Revert / Reapply）全 success

### 教訓（寫給下手者）

外部 agent 在本 repo 動 runtime + push 時，只落 code 不落 release 訊號是常見遺留。接手 session 第一件事應該：`git log HEAD ^$(git describe --tags --abbrev=0)` 對照 `__init__.py` 版號與 `gh release list`，如果 code 版本超前 release，就補完 tag/release/HANDOVER。

---

## 過往會話（2026-04-17，Session 7 — Narrow-positioning pass + context truncation fix）

### 起點

接手 v1.11.3（`c4c0bac`）。外部輸入 `C:\Users\kk789\Downloads\agent_roadmap_narrow_positioning.md`，目標將對外定位收斂成「Claude Code 的 diff-centered second-pass gate」，不否認 v2 與 deep-path 的 bounded context。

### 兩階段交付

**階段 A — 窄定位 docs pass（v1.11.4）**，6 commits 全 docs/metadata，無 runtime 改動。
**階段 B — CI flake hotfix（v1.11.5）**，2 commits 含 runtime 改動（`cold_eyes/context.py`），解 v1.11.4 push 時暴露的 `test_build_context_token_budget_enforced` 間歇失敗。

### Commits 表

| # | Hash | 主題 | 階段 |
|---|---|---|---|
| 1 | `a6a2191` | 新增 `docs/positioning_audit.md` + `docs/positioning_consistency_checklist.md` | A |
| 2 | `4f2ddef` | 核心字串對齊 + README 前段重寫（加入 `What it is / What it is not / When it works best / When not to use / Review paths overview / Why deeper paths exist`）。檔案：`pyproject.toml` / `cold_eyes/__init__.py` / `cold_eyes/prompt.py` fallback / `tests/test_shallow_and_context.py` 斷言 / `README.md` | A |
| 3 | `a6da9ab` | 新增 `docs/disclosure_matrix.md` + `docs/repo_page_reveal_recommendations.md` + `docs/release_note_template.md` | A |
| 4 | `f9d56d0` | 殘留清理 + v1.11.4 bump：`docs/trust-model.md:7` / `docs/assurance-matrix.md:14,49` / `__init__.py` 1.11.3→1.11.4 / CHANGELOG v1.11.4 / HANDOVER 同步 | A |
| 5 | `0d8b16b` | `docs/repo_page_reveal_recommendations.md §6` 前兩項標 applied | A |
| 6 | `c29c7ba` | 3 個 shields.io positioning badges（Stop-hook / diff-centered / not full review）；checklist §6 全數 applied | A |
| 7 | `6e2eb4a` | Session 7 第一次 handover finalize | A |
| 8 | `9965c2a` | **hotfix v1.11.5**：`cold_eyes/context.py` 截斷邏輯預留 notice space；`tests/test_shallow_and_context.py` 斷言收緊至 `<= max_budget`；CHANGELOG v1.11.5 條目；`__init__.py` 1.11.4→1.11.5 | B |
| 9 | `5866656` | v1.11.5 handover update | B |

### GitHub 頁面操作（非 commit）

- **About description** — 248 字元功能堆疊式 → §1.2 定位句（239 字元）
- **Topics** — 從空 → 7 項（見現況訊號）
- **Tags** — `v1.11.4` 於 `c29c7ba`、`v1.11.5` 於 `9965c2a`
- **Releases** — 兩版皆依 `docs/release_note_template.md` §4 七段 checklist 發佈

### v1.11.5 hotfix 詳情

v1.11.4 push 後 `ubuntu-latest, 3.10` 間歇失敗：`test_build_context_token_budget_enforced - assert 16 <= 15`。

**根因**：`cold_eyes/context.py` 截斷邏輯按 ratio 切字元到 `max_tokens`，之後 append `\n[context truncated]\n`（~6 tokens ASCII）而沒有重新 trim。Session 6 R9#97 在 `git.py` 已經修過同一模式，但 `context.py` 沒連動。

**修法**：`body_budget = max_tokens - notice_tokens` 後才算 `char_limit`，再加 belt-and-suspenders 二次 trim 處理 ASCII rounding overshoot。實測從「overshoot 5–6 tokens」收斂到「strict `<= max_tokens`」。

### 驗收

- pytest 774 passed（本地 + CI 全矩陣）
- `python -c "import cold_eyes; print(cold_eyes.__version__)"` → `1.11.5`
- `rg -i "zero-context|diff-only|only reads the diff"` 剩餘匹配全為預期位置：`CHANGELOG.md`（歷史 L183 + v1.11.4 details）、`docs/positioning_audit.md`（審計）、`docs/positioning_consistency_checklist.md`（rewrite 清單）、`HANDOVER.md`（本會話紀錄）
- README 首 ~700 字可在 2 分鐘內回答「是什麼 / 不是什麼 / 何時用 / 何時別用」
- GitHub About / topics / badges / tag / release 全部對齊

### 對外文案定位鎖定點

> Cold Eyes is a diff-centered, second-pass review gate for Claude Code. It reads the working-tree diff as primary input. On the deep path it also pulls limited, structured supporting context (recent commits, co-changed files) + regex-based detector hints. It is **not** a full code review, **not** intent-aware. `--v2` is an opt-in deeper verification mode with multi-gate + retry, not the product headline.

此句為 `docs/positioning_audit.md §6` 的 target。後續任何 PR 若動到下列任一位置，須對照 `docs/positioning_consistency_checklist.md` 檢查：

- `README.md` 首屏
- `pyproject.toml` description
- `cold_eyes/__init__.py` docstring
- `cold_eyes/prompt.py` fallback 字串
- `docs/trust-model.md` L5-L9
- `docs/assurance-matrix.md`

### 不得再出現的表述

`diff-only` / `only reads the diff` / `zero-context` / `no context` / `reviews code changes without context` / `complete review framework` / `full verification platform` / `comprehensive code understanding`。這些在 `docs/positioning_audit.md §1` 和 `§6` 有對應替換詞。

## 過往會話（2026-04-13，Session 6 — Bug Fix Final + Deploy）

### 起點

接手 v1.11.2（`1a63896`），101 bugs 中 53 已修，48 remaining（1 major + 47 minor）。

### 完成內容

#### A. Bug Fix — v1.11.3（48 bugs fixed）

5 個平行 agent 分組修 bug（core v1、v2 modules、CLI+infra、tests、shell+evals+docs），再修最後 4 個收尾。

**Major（1）：**

| # | 檔案 | 修法摘要 |
|---|------|----------|
| #59 | `override.py` | TOCTOU race → `os.rename` 原子搶佔（concurrent review 不再雙 pass）|

**Minor — Production（25）：**

| # | 檔案 | 修法摘要 |
|---|------|----------|
| #14 | `session_runner.py` | post-loop dead code（`gates_running` → `retrying`）|
| #15 | `session_runner.py` | `_all_gates_passing` True → 走 passed 而非 failed_terminal |
| #31 | `retry/translator.py` | 移除 dead `fix_scope` 變數 |
| #34 | `retry/signal_parser.py` | traceback signals 依 file path 去重 |
| #47 | `context.py` | CJK 截斷改依 ASCII/non-ASCII 比例加權 |
| #48 | `config.py` | YAML `12_000` strip underscore 正確解析 |
| #49 | `risk_classifier.py` + `generator.py` | 逐檔 regex match（不再 join 跨路徑）|
| #50 | `orchestrator.py` | parser 只讀 stdout（不混 stderr）|
| #60 | `cli.py` | `--v2` 配非 run 子命令時 stderr 警告 |
| #61 | `cli.py` | `--regression-check` + `--save` 並用時警告 |
| #62 | `schema.py` | `pass=True` + critical/major issues → 修正為 False |
| #64 | `triage.py` | conftest/fixtures/mocks 歸類 `test_support` |
| #68 | `engine.py` | diff 截斷用 `min(max_tokens, max_input_tokens)` |
| #76 | `doctor.py` | `git_repo` 移出 critical_checks → env_warnings |
| #77 | `calibration.py` | 移除未使用的 `session_context` 參數 |
| #78 | `strategy.py` | abort threshold 統一為 `retry_count >= 3` |
| #86 | `claude.py` | 文件記錄 Windows orphan grandchild 限制 |
| #90 | `git.py` | pr-diff base 未 fetch 時顯示 hint |
| #91 | `type_defs.py` | `now_iso()` 改 `Z` 尾綴（與 v1 一致）|
| #92 | `engine.py` | `run()` 接受 `history_path` 參數 |
| #94 | `calibration.py` | per-finding try/except fallback |
| #99 | `engine.py` | input 組裝順序改為 diff→context→hints |
| #100 | `session/schema.py` | `add_event` 複製 data dict |
| R9#97 | `git.py` | truncation notice 預留空間 |

**Minor — Shell（5）：**

| # | 修法摘要 |
|---|----------|
| #17 | env var 展開統一用 `${VAR:-}` |
| #19 | PID write 加 error check |
| #46 | stdin 加 1MB size cap |
| #81 | JSON parser 加 extraction fallback |
| #93 | `stop_hook_active` 改 strict boolean check |

**Minor — Tests（7）：**

| # | 修法摘要 |
|---|----------|
| #20 | mock lambda 改 optional 第二參數 |
| #21 | mock review_status `"clean"` → `"completed"` |
| #35 | 加 `validate_brief()` 驗證 |
| #37 | 移除 dead outer patch |
| #84 | assert 改為 specific `"passed"` |
| #85 | gate count assert 改 `== len(list_gates())` |
| #101 | test mocks 加 `{"result":"..."}` wrapper |

**Minor — Evals & Docs（10）：**

| # | 修法摘要 |
|---|----------|
| #32 | severity check bare pass 加說明 |
| #36 | benchmark response 改 `.txt` 副檔名 |
| #79 | sweep 加 `"minor"` threshold（9 組合）|
| #80 | baseline.json 重生為 33 cases |
| #83 | SECURITY.md TTL 修正為 10 分鐘 |
| #95 | quality_report.json 欄位對齊實際輸出 |
| #96 | evaluation.md case 數更新為 33 |
| R9#98 | stress cases category 改 `"correctness"` |

**修改的檔案（38 files）：**

```
22 production + 7 test + 3 eval + 2 doc + 1 shell + 1 security doc
38 files changed, 409 insertions(+), 156 deletions(-)
```

#### B. Deploy 同步

`cp` repo → `~/.claude/scripts/`。清除舊殘留：
- `cold_eyes/cold_eyes/`（巢狀複製）
- `cold_eyes/__pycache__/`
- `cold_review_engine.py`（v1.0 遺物）

#### C. Repo 頁面對齊

- GitHub description：773 → 774 tests
- README：built-in ignore 加 `*.map`
- README：verify-install 改為 2 critical checks（git_repo 移至 env_warnings）

#### D. Push

3 commits 推送（`fce961c..c4c0bac`）：

```
3a73862 fix: 48 bug fixes — 101/101 complete (v1.11.3)
2d15876 docs(handover): update for Session 6
c4c0bac docs(readme): align with v1.11.3
```

---

## 累計修復統計

| 版本 | Commit | Bugs fixed | Tests |
|------|--------|-----------|-------|
| v1.11.1 | `5571e90` | 29（2 critical, 15 major, 12 minor）| 773 |
| v1.11.2 | `1a63896` | 24（12 major, 12 minor）| 774 |
| v1.11.3 | `3a73862` | 48（1 major, 47 minor）| 774 |
| **合計** | | **101 / 101** | |

---

## 架構

### v2 pipeline 流程

```
run_session(task, files)
  ├─ create_session()
  ├─ generate_contracts()          ← contract/generator.py
  ├─ check_quality()               ← contract/quality_checker.py
  ├─ classify_risk()               ← gates/risk_classifier.py
  ├─ build_gate_plan()             ← gates/selection.py
  │
  ├─ LOOP (max_retries):
  │   ├─ run_gates()               ← gates/orchestrator.py
  │   │   ├─ llm_review → engine.run() (v1 pipeline)
  │   │   └─ test_runner / lint_checker / ... (subprocess)
  │   │
  │   ├─ merge_duplicates()        ← noise/dedup.py
  │   ├─ suppress_seen()           ← noise/retry_suppression.py
  │   ├─ calibrate()               ← noise/calibration.py
  │   │
  │   ├─ if all gates passed → return "passed"
  │   ├─ if no results → return "failed_terminal"
  │   │
  │   ├─ translate()               ← retry/translator.py
  │   ├─ should_stop()             ← retry/stop.py
  │   ├─ select_strategy()         ← retry/strategy.py
  │   ├─ apply re_run_gates filter ← strategy output
  │   └─ if stop/abort → return "failed_terminal"
  │
  └─ return SessionRecord
```

### Session 狀態機

```
created → contract_generated → gates_planned → gates_running
                                                   ↓
                                     passed    gates_failed
                                                   ↓
                                              retrying → gates_running (loop)
                                                   ↓
                                              failed_terminal

任何非 terminal 狀態 → aborted
```

### 目錄結構（v2 新增）

```
cold_eyes/
  type_defs.py                    共用 TypedDict + helpers (generate_id, now_iso)
  session/
    schema.py                    SessionRecord create/validate
    store.py                     JSONL-based SessionStore（原子寫入）
    state_machine.py             VALID_TRANSITIONS + transition()
  contract/
    schema.py                    CorrectnessContract create/validate
    generator.py                 rule-based contract generation（逐檔 regex match）
    quality_checker.py           quality score + warnings
  gates/
    risk_classifier.py           session-level risk aggregation（逐檔 regex match）
    catalog.py                   gate registry (5 builtin gates)
    selection.py                 contract-driven + risk-escalation gate selection（llm_review 保證）
    orchestrator.py              sequential gate execution, wraps engine.run()（只讀 stdout）
    result.py                    gate-specific output parsers (pytest, ruff, llm_review)
  retry/
    taxonomy.py                  failure classification (11 categories)
    brief.py                     RetryBrief create/validate
    signal_parser.py             extract actionable signals from gate output（traceback 去重）
    translator.py                gate failures → retry brief
    strategy.py                  8 retry strategies + escalation logic（abort >=3 統一）
    stop.py                      5 stop conditions（stride-based progress check）
  noise/
    dedup.py                     (type, file, check) deduplication
    grouping.py                  anchor-based proximity + same-check clustering
    retry_suppression.py         suppress previously-seen findings（cumulative）
    fp_memory.py                 wraps v1 memory.py for v2 findings
    calibration.py               wraps v1 policy.calibrate_evidence() for v2（per-finding try/except）
  runner/
    session_runner.py            top-level run_session() entry point
    metrics.py                   collect_metrics() + aggregate_metrics()（aborted 排除分母）
```

---

## v1.11.1–v1.11.3 行為變化（下手者需注意）

| 改動 | 舊行為 | 新行為 |
|------|--------|--------|
| `max_retries` 語義 | `>=` check：3 → 3 total | `>` check：3 → 4 total（initial + 3 retries）|
| pass 判定 | noise 清空 + soft fail → pass | 只有 all gates pass 才 pass |
| 空 gates | `all([])=True` → pass | → `failed_terminal` |
| 未知 threshold | 預設 3（只擋 critical）| 預設 0（全擋）|
| 未知 confidence | 預設 2（medium）| 預設 0（最嚴格）|
| `fail-closed` + override | override 繞過 | 永不繞過 |
| `_parse_llm_review` | 讀 `outcome["review"]` → 0 findings | 讀 `outcome["issues"]` |
| `estimate_tokens` | `ascii // 4`（1-3 chars → 0）| `(ascii+3) // 4`（ceiling，≥1）|
| gate selection | `llm_review` 只在空 list 時 fallback | `llm_review` 永遠加入（若 available）|
| `input_remaining` 負數 | 靜默 skip context/hints | stderr 警告 |
| `review.py` 解析 | 只接受 `{"result":"..."}` wrapper | 同時接受 wrapped/unwrapped |
| `{"result": null}` | 靜默 pass | `pass: False` |
| history prune/archive | 直接 `open("w")` 覆寫 | write-to-temp-then-rename |
| `keep_entries=0` | 清空歷史 | raise ValueError |
| v2 session | 不寫 v1 history | 寫入 v1 history（model="v2-session"）|
| `pass_rate` 分母 | 含 aborted | 只含 passed + failed_terminal |
| `ttl_minutes ≤ 0` | 創建已過期 token | raise ValueError |
| `*.map` 檔案 | 送入 review | BUILTIN_IGNORE 排除 |
| override consume | read→delete TOCTOU race | `os.rename` 原子搶佔 |
| context 截斷 | `max_tokens * 2`（CJK 2x 過量）| ASCII/non-ASCII 加權比例 |
| diff 截斷上限 | 只看 `max_tokens` | `min(max_tokens, max_input_tokens)` |
| input 組裝順序 | hints→context→diff | diff→context→hints（符合 prompt）|
| `now_iso()` 格式 | `+00:00` | `Z`（與 v1 一致）|
| schema validation | `pass=True` + critical issues 通過 | 自動修正為 `False` |
| `_all_gates_passing` | stop → failed_terminal | stop → passed |
| orchestrator parser | stdout + stderr | 只讀 stdout |
| risk_classifier | `" ".join(files)` → 跨路徑匹配 | 逐檔 match |
| abort threshold | translator `>=3`、strategy `>3` | 統一 `>=3` |
| truncation notice | 不計 token | 預留空間 |
| triage fallback | conftest/fixtures → `"source"` | → `"test_support"` |
| verify-install | 3 critical checks（含 git_repo）| 2 critical checks（git_repo 移至 env_warnings）|

---

## 下次 Session 要做的事

### Bug 修復已完成

101/101 bugs from `cold-eyes-report.md` 已全部修復。

### 原有待辦（仍有效）

1. **E2E 驗證** — 在��實 repo 跑 `python cli.py run --v2`
2. **shell hook 啟用** — `cold-review.sh` 加 `--v2` flag
3. **補測試覆蓋** — `available_gate_ids=None` auto-detection、`engine_adapter` 實際使用
4. **部署已完成** — ~~`cp` 至 `~/.claude/scripts/`~~（Session 6 已同步）

---

## 環境變數

（v2 新增模組不引入新的環境變數，全部沿用 v1）

| 變數 | 預設 | 說明 |
|---|---|---|
| `COLD_REVIEW_MODE` | `block` | block / report / off（自動 lowercase）|
| `COLD_REVIEW_MODEL` | `opus` | deep review 的 model |
| `COLD_REVIEW_SHALLOW_MODEL` | `sonnet` | shallow review 的 model |
| `COLD_REVIEW_MAX_TOKENS` | `12000` | diff 的 token 預算 |
| `COLD_REVIEW_CONTEXT_TOKENS` | `2000` | context section 的 token 預算（0=停用）|
| `COLD_REVIEW_MAX_INPUT_TOKENS` | `max_tokens+context_tokens+1000` | 總 token 上限（0 或負數 ��� 用預設；負數時 stderr 警告）|
| `COLD_REVIEW_BLOCK_THRESHOLD` | `critical` | severity 門檻（自動 lowercase；未知值 → 全擋）|
| `COLD_REVIEW_CONFIDENCE` | `medium` | confidence 門檻（未知值 → 最嚴格）|
| `COLD_REVIEW_LANGUAGE` | `繁體中文（台灣）` | 輸出語言（sanitize：50 字上限）|
| `COLD_REVIEW_SCOPE` | `working` | diff 範圍（自動 lowercase）|
| `COLD_REVIEW_BASE` | 未設 | pr-diff scope 的 base branch |
| `COLD_REVIEW_TRUNCATION_POLICY` | `warn` | warn / soft-pass / fail-closed（自動 lowercase）|

## 長期事項（不可自行移除，需 user 確認）

- **v2 E2E 驗證未完成** — user 需在真實 repo 跑 `python cli.py run --v2`，然後檢查 `~/.claude/cold-review-sessions/sessions.jsonl` 確認 session 流程正確。每次 session 開頭應提醒 user 此事，直到 user 明確說測完、決定是否切為預設後才可移除本項。

## 注意事項

- v1 pipeline 有修改（engine.py 加了 `outcome["issues"]`、`.lower()`、cast、input_remaining 警告、`history_path` 參數等），但 `engine.run()` ���對外 contract 向後相容 — 新參數皆有預設值。
- v2 純 stdlib，無新增依賴。`pyproject.toml` 的 `include = ["cold_eyes*"]` 已自動涵蓋 sub-packages。
- Session store 用 JSONL（同 v1 history），路徑 `~/.claude/cold-review-sessions/sessions.jsonl`。原子寫入。
- history.py 的 prune/archive 現在都用 write-to-temp-then-rename（防 crash 資料遺失，但不防 concurrent write）。
- override.py 的 `consume_override` 現在用 `os.rename` 原子搶佔（防 concurrent review 雙 pass）。
- Gate catalog 目前 5 個 builtin gates，`llm_review` 永遠加入（若 available）。其餘 4 個 external gates 靠 subprocess（只讀 stdout，不混 stderr）。
- `max_retries` 語義 = actual retries after initial attempt。`max_retries=3` → 4 total runs。
- v2 session 結果現在寫入 v1 history（`model="v2-session"`），v1 stats/quality-report 可見。
- review.py 同時支援 Claude CLI wrapped `{"result":"..."}` 和 unwrapped 格式。
- Bug report 在 `C:\Users\kk789\Desktop\cold-eyes-report.md`（13 輪，101 bugs，**101 fixed**）。
- v2 task breakdown 原始文件在 `C:\Users\kk789\Downloads\cold-eyes-reviewer_v2_task_breakdown.md`。
- Deploy 目錄 `~/.claude/scripts/` 已於 Session 6 同步，清除了舊殘留（巢狀 cold_eyes、pycache、cold_review_engine.py）。
