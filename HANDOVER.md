# Cold Eyes Reviewer — 交接文件

## 現況

- **版本：** v0.7.0
- **分支：** master
- **測試：** 152 passed
- **部署：** `~/.claude/scripts/` 4 個檔案，doctor 全綠

## 架構

Claude Code Stop hook 的零上下文 code reviewer。

```
cold-review.sh              Stop hook 入口（~122 行），只跑 guard checks
  ├→ cold-review-helper.py  Shell-facing utilities（parse-hook、log-state）
  └→ cold_review_engine.py  核心（~620 行）：diff 建構、scope、Claude CLI、policy、history、doctor
cold-review-prompt.txt      系統 prompt 模板，placeholders: {language}
```

engine 是主路徑，shell 是入口，helper 是 shell 呼叫的工具函式。

## 本次會話做了什麼

### 起點

接手 v0.5.2。收到兩份產品化文件：
- `~/Downloads/cold_eyes_productization_roadmap.md` — 完整產品化路線（14 章節）
- `~/Desktop/cold-eyes-phase1-plan.md` — 從路線圖萃取的 Phase 1 計畫

以 Phase 1 計畫的單人開發者優先序為藍圖，一次實作 5 個功能。

### v0.6.0（`7e715c1`）— Phase 1 Alpha

#### 1. `doctor` 命令

`python cold_review_engine.py doctor` — 環境健康檢查。

- 7 項檢查：Python、Git、Claude CLI、deploy files、settings.json hook、git repo、.cold-review-ignore
- 回傳 `{"action": "doctor", "checks": [...], "all_ok": bool}`
- 函式簽名 `run_doctor(scripts_dir=None, settings_path=None, repo_root=None)` — 參數可注入以利測試
- 11 new tests

#### 2. Diff scope 控制

`--scope working|staged|head` + `COLD_REVIEW_SCOPE` env var。

- `working`（預設）：staged + unstaged + untracked（原有行為）
- `staged`：只 `git diff --cached`
- `head`：`git diff HEAD`
- 影響函式：`collect_files(scope)`、`build_diff(..., scope)`、`run(..., scope)`、`log_to_history(..., scope)`
- Shell 加 `SCOPE` 讀取和 `--scope` 傳遞
- History entry 新增 `scope` 欄位
- 8 new tests

#### 3. 策略預設文件化

README 新增 Strategy presets section。5 個預設組合（Conservative / Standard / Strict / Aggressive / Observe）附 env var 範例。零 code 改動。

1 new test（README 含 "Strategy presets"）。

#### 4. `line_hint`

Issue schema 新增 `line_hint` 欄位（如 `"L42"`、`"L42-L50"`、`""`）。

- Prompt 加指示：從 diff hunk header 取行號，不確定就留空
- `parse_review_output()` 加 `issue.setdefault("line_hint", "")`
- `format_block_reason()` 有 line_hint 時顯示 `[CRITICAL] (L42) 檢查：...`
- Helper 同步更新 `parse_review()` 和 `format_block()`
- 7 new tests

#### 5. `schema_version`

Review output 和 history 新增 `schema_version: 1`。

- 模組常數 `SCHEMA_VERSION = 1`
- `parse_review_output()` 成功和失敗都設 `schema_version`
- `_infra_review()` 也帶 `schema_version`
- `log_to_history()` entry 加 `schema_version`
- Prompt 的 output JSON 加 `"schema_version": 1`
- Helper 同步
- 10 new tests

#### README 全面更新

- Output format 加 `schema_version`、`line_hint` 範例和說明
- Install 加 doctor 驗證步驟
- What gets reviewed 加 scope 說明
- 新 Diagnostics section（doctor 7 項檢查表）
- Files table、Building on top、Known limitations 都更新

### v0.7.0 — Phase 1.4 Feedback Loop

#### 1. Override reason tracking

`COLD_REVIEW_OVERRIDE_REASON` env var + `--override-reason` CLI arg。

- `apply_policy()` 加 `override_reason=""` 參數
- Override 時 reason 寫入 outcome，display 加 `[reason]`
- `log_to_history()` 加 `override_reason=""`，非空時寫入 entry
- `run()` 讀 env var，串接到 apply_policy 和 log_to_history
- Shell 加 `OVERRIDE_REASON` 讀取和 `--override-reason` 傳遞
- Helper `log-state`、`log-review` 同步加 override_reason 參數
- 11 new tests

#### 2. Block override hint

Block messages（review block 和 infra block）尾部加：
`To override: COLD_REVIEW_ALLOW_ONCE=1 COLD_REVIEW_OVERRIDE_REASON='<reason>'`

#### 3. `aggregate-overrides` 命令

`python cold_review_engine.py aggregate-overrides` — 讀 history JSONL，回傳：
`{"action": "aggregate-overrides", "total_overrides": N, "reasons": [...], "recent": [...]}`
3 new tests

#### 4. v0.6.0 文件修正

- `.cold-review-ignore`：README 列出 12 個 builtin patterns，說明 per-repo 檔案位置和疊加機制
- `line_hint`：顯示改為 `(~L42)` 表示 approximate，README 加 block mode 行號驗證建議
- `schema_version`：README 加 bump 規則（breaking change = bump，optional field = 不 bump）
- 1 new test

## 部署

```bash
cp cold-review.sh cold-review-helper.py cold_review_engine.py cold-review-prompt.txt ~/.claude/scripts/
python ~/.claude/scripts/cold_review_engine.py doctor   # 驗證
```

## 環境變數

| 變數 | 預設 | 說明 |
|---|---|---|
| `COLD_REVIEW_MODE` | `block` | block / report / off |
| `COLD_REVIEW_MODEL` | `opus` | opus / sonnet / haiku |
| `COLD_REVIEW_MAX_TOKENS` | `12000` | diff 的 token 預算 |
| `COLD_REVIEW_BLOCK_THRESHOLD` | `critical` | 擋的 severity 門檻 |
| `COLD_REVIEW_CONFIDENCE` | `medium` | confidence 硬過濾門檻（high / medium / low） |
| `COLD_REVIEW_LANGUAGE` | `繁體中文（台灣）` | 輸出語言 |
| `COLD_REVIEW_SCOPE` | `working` | diff 範圍：working / staged / head |
| `COLD_REVIEW_ALLOW_ONCE` | 未設 | 設 1 一次性繞過 block |
| `COLD_REVIEW_OVERRIDE_REASON` | 未設 | override 理由（free-text，搭配 ALLOW_ONCE 使用） |

Shell 顯式傳 `--confidence`、`--language`、`--scope`、`--override-reason` 給 engine。engine 內 `os.environ.get()` 保留作為 fallback。

## 後續計畫

產品化路線圖在 `~/Downloads/cold_eyes_productization_roadmap.md`。
Phase 1+ 計畫在 `~/Desktop/cold-eyes-phase1-plan.md`。

### Phase 2（Team Beta）

- CI/PR mode（`--scope pr-diff --base main`，需 Claude API adapter）
- Repo-level policy file（`.cold-review-policy.yml`）
- Team dashboard（先 CLI `cold-eyes stats`，再 web）
- Override governance（override 必須附理由、可稽核）

### Phase 3（商業化）

- Open-core：Free/OSS 本地 runner + Pro/Team 中央 policy + Enterprise SSO/稽核

### 架構演進時機

目前扁平結構（4 檔案 cp 部署）。當 engine 超過 ~800 行或需要 `pip install` 時，轉為 package 結構（`cold_eyes/` 目錄 + `pyproject.toml`）。目前 ~620 行，還有空間。

## 待辦 / 已知問題

- feedback loop（Phase 1.4）未做
- Helper 的 parse-review、filter-files、rank-files 等指令仍有與 engine 重複的常數和邏輯。build-prompt 已去重，其餘未動
- line_hint 的 LLM 幻覺率未實測。prompt 已限制「不確定就留空」，需要真實 diff 驗證
- 產品化路線圖建議的多項重構（模組拆分、adapter 抽象、category-specific threshold、reason code）尚未進行，屬 Phase 2 前的架構準備
