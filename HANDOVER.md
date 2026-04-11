# Cold Eyes Reviewer — 交接文件

## 現況

- **版本：** v0.9.0（master，2026-04-11）
- **分支：** master
- **測試：** 150 passed
- **部署：** `~/.claude/scripts/` 需同步（新增 `config.py`）

## 架構

Claude Code Stop hook 的零上下文 code reviewer。

```
cold-review.sh              Stop hook 入口（~125 行），只跑 guard checks
  ├→ cold_eyes/helper.py    Shell-facing（parse-hook、log-state）
  └→ cold_eyes/cli.py       CLI entry → engine.py → 各模組
cold-review-prompt.txt      系統 prompt 模板，placeholders: {language}
.cold-review-policy.yml     Per-repo 配置（optional，放 project root）

cold_eyes/                   Package（13 模組）
  constants.py               共用常數（SCHEMA_VERSION, SEVERITY_ORDER, BUILTIN_IGNORE 等）
  config.py                  Policy file loader（flat YAML subset parser，無 PyYAML 依賴）
  git.py                     git_cmd, collect_files, is_binary, build_diff
  filter.py                  filter_file_list, rank_file_list
  prompt.py                  build_prompt_text
  claude.py                  call_claude
  review.py                  parse_review_output
  policy.py                  apply_policy, filter_by_confidence, format_block_reason
  history.py                 log_to_history, aggregate_overrides, compute_stats
  doctor.py                  run_doctor（8 checks，含 policy_file）
  engine.py                  run() 主管線、_resolve()、_skip()、_infra_review()
  cli.py                     argparse + dispatch（run / doctor / aggregate-overrides / stats）
  helper.py                  parse_hook, log_state_from_shell
```

Import 依賴圖無循環：constants 是 leaf，config 依賴 constants（無），git/filter/review 依賴 constants，policy/history 依賴 constants，engine 依賴全部含 config，cli 依賴 engine/doctor/history。

## 本次會話做了什麼

### 起點

接手 v0.8.0（`a11c706`）。Phase 1 全部完成，package restructure 已完成。110 tests。

### v0.9.0 — Phase 2.1 stats CLI + Phase 2.2 policy file

**Phase 2.1: stats CLI（+13 tests）**

`compute_stats()` in `history.py`：
- 各 state 計數（passed/blocked/overridden/skipped/infra_failed/failed/reported）
- `--last 7d|24h|2w` 時間過濾（支援 d/h/w 單位）
- `--by-reason` override 理由分群，按次數降序
- `--by-path` per-cwd 統計（total/blocked/overridden），按 blocked 降序

CLI: `python cold_eyes/cli.py stats [--last 7d] [--by-reason] [--by-path]`

**Phase 2.2: policy file（+27 tests）**

新模組 `config.py`：
- `.cold-review-policy.yml` flat YAML subset parser（無外部依賴，forward-compatible with full YAML）
- 支援 keys: `mode`, `model`, `max_tokens`, `block_threshold`/`threshold`, `confidence`, `language`, `scope`
- Unknown keys silently ignored, invalid integers dropped

`engine.py` — `_resolve()` 統一解析鏈：
- **CLI arg > env var > policy file > hardcoded default**
- `run()` 簽名改為全部 `=None`，向後相容
- `mode: off` 在 engine 層也能正確處理

`cold-review.sh` — 只在 env var 明確設定時才傳 CLI arg（`${VAR+x}` 測試），讓 engine 有機會讀 policy file

`doctor.py` — 新增第 8 項 `policy_file` 檢查（info level）

150 tests（engine 135 + helper 5 + smoke 10）。

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
| `COLD_REVIEW_LANGUAGE` | `繁體中文（台灣）` | 輸出語言 |
| `COLD_REVIEW_SCOPE` | `working` | diff 範圍：working / staged / head |
| `COLD_REVIEW_ALLOW_ONCE` | 未設 | 設 1 一次性繞過 block |
| `COLD_REVIEW_OVERRIDE_REASON` | 未設 | override 理由（free-text，搭配 ALLOW_ONCE 使用） |

解析優先級：CLI arg > env var > `.cold-review-policy.yml` > hardcoded default。

## 後續計畫

產品化路線圖在 `~/Downloads/cold_eyes_productization_roadmap.md`。
Phase 1 計畫在 `~/Desktop/cold-eyes-phase1-plan.md`。

Phase 1 全部完成。Phase 2.1（stats）和 2.2（policy file）已完成。

### Phase 2 剩餘項目

3. **model adapter** — 抽象 `claude.py` 為 adapter pattern（CLI adapter + API adapter），為 CI mode 鋪路。
4. **CI/PR mode** — `--scope pr-diff --base main`，GitHub Action wrapper，需要 adapter 先行。

### Phase 3（商業化）

- Open-core：Free/OSS 本地 runner + Pro/Team 中央 policy + Enterprise SSO/稽核

### 架構演進時機

Package 轉型已完成。下一步：需要 `pip install` 時加 `pyproject.toml`（預計 model adapter 引入外部依賴時）。
Policy file 目前用 flat YAML subset parser；引入 PyYAML 後可無縫升級支援巢狀結構。

## 待辦 / 已知問題

- line_hint 的 LLM 幻覺率未實測。prompt 已限制「不確定就留空」，block 顯示加了 `~` 前綴，需要真實 diff 驗證
- `cli.py` 和 `helper.py` 頂部有 `sys.path` manipulation 以支援直接 `python cold_eyes/cli.py` 呼叫。改為 `pip install -e .` 後可移除
- 產品化路線圖建議的 adapter 抽象、category-specific threshold、reason code 屬 Phase 2 剩餘
