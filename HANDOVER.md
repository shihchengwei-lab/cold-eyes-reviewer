# Cold Eyes Reviewer — 交接文件

## 現況

- **版本：** v1.0.0（master，2026-04-11）
- **分支：** master
- **測試：** 197 passed
- **部署：** `~/.claude/scripts/` 需同步

## 架構

Claude Code Stop hook 的零上下文 code reviewer。

```
cold-review.sh              Stop hook 入口（shim，~100 行）
  └→ cold_eyes/cli.py       CLI entry → engine.py → 各模組

cold-review-prompt.txt      系統 prompt 模板，placeholders: {language}
.cold-review-policy.yml     Per-repo 配置（optional，放 project root）

cold_eyes/                   Package（14 模組）
  constants.py               共用常數（SCHEMA_VERSION, SEVERITY_ORDER, BUILTIN_IGNORE, DEPLOY_FILES）
  config.py                  Policy file loader（flat YAML subset parser，無 PyYAML 依賴）
  git.py                     git_cmd（失敗 raise GitCommandError）, collect_files, is_binary, build_diff（回傳 dict）
  filter.py                  filter_file_list, rank_file_list
  prompt.py                  build_prompt_text
  claude.py                  ModelAdapter base, ClaudeCliAdapter, MockAdapter, ReviewInvocation
  review.py                  parse_review_output
  policy.py                  apply_policy, filter_by_confidence, format_block_reason（language-aware）
  history.py                 log_to_history（含 failure_kind, stderr_excerpt）, aggregate_overrides, compute_stats
  override.py                arm_override, consume_override（一次性 token）
  doctor.py                  run_doctor（11 checks，含 legacy detection）
  engine.py                  run() 主管線、_resolve()、_skip()、_infra_review()
  cli.py                     argparse + dispatch（run / doctor / aggregate-overrides / stats / arm-override）
  __init__.py
```

Import 依賴圖無循環：constants 是 leaf，git 定義 GitCommandError/ConfigError，engine 依賴全部含 override，cli 依賴 engine/doctor/history/override。

## 本次會話做了什麼

### 起點

接手 v0.10.0（`6dfc272`）。Phase 1+2 全部完成。162 tests。

### v0.11.0 — Personal Hardening（9 patches）

**PATCH 4: Typed git failures（+5 tests）**

`git.py` — `GitCommandError(RuntimeError)` + `ConfigError(RuntimeError)`：
- `git_cmd()` 非零 exit 直接 raise，不再回空字串
- `collect_files("pr-diff")` 無 base → `ConfigError`
- `engine.py` 用 `try/except` 包 `collect_files()` + `build_diff()`，映射到 `infra_failed`

**PATCH 6: ReviewInvocation + stderr（+7 tests）**

`claude.py` — `ReviewInvocation` class（stdout, stderr, exit_code, failure_kind）：
- `ClaudeCliAdapter._call()` 捕獲 stderr
- failure_kind: `None`/`timeout`/`cli_not_found`/`cli_error`/`empty_output`
- `MockAdapter` 同步更新，支援 stderr/failure_kind 參數
- `__iter__` 保持向後相容 tuple 解構

`history.py` — 新增 `failure_kind` + `stderr_excerpt` 欄位

**PATCH 3: One-time override token（+8 tests）**

新模組 `override.py`：
- `arm_override(repo_root, reason, ttl_minutes=10)` → `~/.claude/cold-review-overrides/<hash>.json`
- `consume_override(repo_root)` → 讀取、驗證（repo match + 未過期）、刪除、回傳 `(True, reason)`
- Token 僅能使用一次，過期自動清除

`cli.py` — `arm-override` 子命令（`--reason`, `--ttl`）
`engine.py` — `consume_override()` 優先於 legacy `ALLOW_ONCE`（deprecated with warning）

**PATCH 5: Rich diff metadata（+5 tests）**

`git.py` — `build_diff()` 回傳 dict：
- `partial_files`（切半）、`skipped_budget`（預算）、`skipped_binary`、`skipped_unreadable`
- `truncated = bool(any of above non-empty)` — 修復最後一個檔案被切半但無後續 skipped 的 bug

**PATCH 7: Policy/state machine fixes（+7 tests）**

`policy.py`：
- report mode infra failure state: `"failed"` → `"infra_failed"`（與 block mode 一致）
- `effective_pass = len(filtered_issues) == 0`（取代 model 原始 `pass` 值）
- `format_block_reason()` 加 `language` 參數，中/英文標籤切換
- Issue 顯示 `file` + `line_hint`：`[CRITICAL] auth.py (~L42)`
- Override 指引改為 `arm-override`

**PATCH 2+1: Shell shim rewrite**

`cold-review.sh` — 完全重寫（~100 行）：
- 移除 helper.py 依賴、`log_state()` 函式、`MAX_LINES` 轉換
- `parse-hook` 改用 inline python one-liner
- Lock 改為 `mkdir` atomic（TOCTOU race 修復），stale detection + 單次重試
- Engine 空輸出不再 log（engine 自己處理）

**PATCH 8: Doctor/deploy cleanup**

`doctor.py` — 3 新 checks：
- `legacy_helper`：偵測 `cold-review-helper.py`（split-brain）
- `shell_version`：偵測 shell 中的 legacy patterns
- `legacy_env`：偵測 `COLD_REVIEW_MAX_LINES`

`constants.py` — `DEPLOY_FILES` 從 5 筆更新為 16 筆（完整 package）

**PATCH 9: Final test sweep（+4 shell smoke tests）**

- `test_no_helper_references`、`test_no_direct_claude_call`、`test_no_max_lines`、`test_uses_mkdir_lock`
- Doctor: `test_legacy_helper_detected`、`test_clean_shell_ok`、`test_shell_with_legacy_patterns_detected`

**README 更新**

- `ALLOW_ONCE` 標記 deprecated，新增 `arm-override` 段落
- Failure modes 表重寫（`infra_failed` + `failure_kind`）
- Diagnostics 表從 8 → 11 checks
- Known limitations 更新（truncation 有分類、infra 可診斷）
- Files 表移除硬編模組數

202 tests（engine 155 + helper 5 + shell smoke 14 + override 8 + misc 20）。

## 部署

```bash
cp -r cold_eyes/ cold-review.sh cold-review-prompt.txt ~/.claude/scripts/
python ~/.claude/scripts/cold_eyes/cli.py doctor   # 驗證
```

## 環境變數

| 變數 | 預設 | 說明 |
|---|---|---|
| `COLD_REVIEW_MODE` | `block` | block / report / off |
| `COLD_REVIEW_MODEL` | `opus` | opus / sonnet / haiku |
| `COLD_REVIEW_MAX_TOKENS` | `12000` | diff 的 token 預算 |
| `COLD_REVIEW_BLOCK_THRESHOLD` | `critical` | 擋的 severity 門檻 |
| `COLD_REVIEW_CONFIDENCE` | `medium` | confidence 硬過濾門檻（high / medium / low） |
| `COLD_REVIEW_LANGUAGE` | `繁體中文（台灣）` | 輸出語言（影響 block labels） |
| `COLD_REVIEW_SCOPE` | `working` | diff 範圍：working / staged / head / pr-diff |
| `COLD_REVIEW_BASE` | 未設 | pr-diff scope 的 base branch（如 main） |
| `COLD_REVIEW_ALLOW_ONCE` | 未設 | **Deprecated.** 設 1 繞過 block（無法真正消耗，會 emit warning） |
| `COLD_REVIEW_OVERRIDE_REASON` | 未設 | override 理由（free-text） |

解析優先級：CLI arg > env var > `.cold-review-policy.yml` > hardcoded default。

### 新的 override 流程

```bash
# 取代 ALLOW_ONCE — 真的只能用一次
python ~/.claude/scripts/cold_eyes/cli.py arm-override --reason false_positive
# 下一次 block 會被放行，token 自動消耗刪除
```

## 後續計畫

產品化路線圖在 `~/Downloads/cold_eyes_productization_roadmap.md`。
Phase 1 計畫在 `~/Desktop/cold-eyes-phase1-plan.md`。

Phase 1 全部完成。Phase 2 全部完成。v0.11.0 hardening 完成。

### Phase 3（商業化）

- Open-core：Free/OSS 本地 runner + Pro/Team 中央 policy + Enterprise SSO/稽核

### 架構演進時機

Package 轉型已完成。下一步：需要 `pip install` 時加 `pyproject.toml`（預計引入外部依賴時）。
Policy file 目前用 flat YAML subset parser；引入 PyYAML 後可無縫升級支援巢狀結構。

## 待辦 / 已知問題

- `line_hint` 的 LLM 幻覺率未實測。prompt 已限制「不確定就留空」，block 顯示加了 `~` 前綴
- `cli.py` 和 `helper.py` 頂部有 `sys.path` manipulation 以支援直接 `python cold_eyes/cli.py` 呼叫。改為 `pip install -e .` 後可移除
- 舊的 history 條目仍有 `state: "failed"`（v0.11.0 前的 report-mode infra failure），stats 查詢時要注意
