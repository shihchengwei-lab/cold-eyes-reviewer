# Cold Eyes Reviewer — 交接文件

## 現況

- **版本：** v1.0.0（master `f92685b`，2026-04-11）
- **分支：** master
- **測試：** 197 passed
- **部署：** `~/.claude/scripts/` 已同步，`doctor` all_ok

## 架構

Claude Code Stop hook 的零上下文 code reviewer。

```
cold-review.sh              Stop hook shim（~100 行），只做 guard + 呼叫 CLI
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
收到一份「個人用修補方案」patchset 文件（9 patches），指出 7 個根本問題。

### v0.10.0 → v0.11.0：9-patch hardening

| Patch | 改了什麼 | 測試 |
|---|---|---|
| 4 | `git_cmd()` 失敗 raise `GitCommandError`，不再回空字串 | +5 |
| 6 | `ReviewInvocation` 捕獲 stderr + failure_kind | +7 |
| 3 | `arm-override` 一次性 token，`ALLOW_ONCE` deprecated | +8 |
| 5 | `build_diff()` 回傳 dict，partial/binary/unreadable/budget 分開追蹤 | +5 |
| 7 | `infra_failed` 一致、`effective_pass` 取代 model `pass`、language-aware labels | +7 |
| 2+1 | Shell 重寫：`mkdir` atomic lock、移除 helper 依賴、移除 MAX_LINES | — |
| 8 | Doctor 加 3 checks（legacy_helper/shell_version/legacy_env），DEPLOY_FILES 完整 | +4 |
| 9 | Shell smoke：no_helper、no_claude_direct、no_max_lines、mkdir_lock | +4 |

202 tests。

### v0.11.0 → v1.0.0：清殘渣 + API 穩定宣告

- 刪除 `cold_eyes/helper.py`（shell 不再使用，deprecated since v0.11.0）
- 刪除 `tests/test_helper.py`（5 tests）
- `DEPLOY_FILES` 15 筆
- 修 shell `2>&2`（no-op）→ `2>/dev/null`
- README 加 token 成本估算表、Windows lock caveat
- GitHub repo description 更新

197 tests。API stable。

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

### Override 流程

```bash
# 一次性放行（token 10 分鐘後過期，用完即刪）
python ~/.claude/scripts/cold_eyes/cli.py arm-override --reason false_positive
```

## 後續方向

產品化路線圖在 `~/Downloads/cold_eyes_productization_roadmap.md`。

### 可能的下一步

- `pyproject.toml` — 需要 `pip install` 時加（目前用 `sys.path` hack，`cli.py` 頂部）
- History rotation — append-only JSONL 會無限成長，可加 `--rotate` 子命令
- `line_hint` 實測 — 幻覺率未量化，prompt 已限制但未驗證
- PyYAML 升級 — flat parser 夠用，但巢狀結構需要時可無縫切換

### 不建議做的

- Phase 3 商業化 — 對個人用工具是過度設計
- Daemon / 常駐服務 — hook 架構已夠用
- 複雜權限模型 — 單人使用無需

## 已知問題

- `cli.py` 頂部有 `sys.path` manipulation，改為 `pip install -e .` 後可移除
- Windows Git Bash 的 `mkdir` lock 和 `kill -0` stale detection 不如原生 Unix 可靠
- 舊 history 條目仍有 `state: "failed"`（v0.11.0 前的 report-mode infra failure），stats 查詢時注意
- `line_hint` 是 LLM 估計值，block 顯示加了 `~` 前綴，但幻覺率未實測
