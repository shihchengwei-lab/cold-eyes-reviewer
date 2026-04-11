# Cold Eyes Reviewer — 交接文件

## 現況

- **版本：** v1.1.0（master，2026-04-11）
- **分支：** master
- **測試：** 225 passed
- **部署：** `~/.claude/scripts/` 需重新同步，`doctor` all_ok

## 架構

Claude Code Stop hook 的零上下文 code reviewer。

```
cold-review.sh              Stop hook shim（~130 行），guard + fail-closed parser
  └→ cold_eyes/cli.py       CLI entry → engine.py → 各模組

cold-review-prompt.txt      系統 prompt 模板，placeholders: {language}
.cold-review-policy.yml     Per-repo 配置（optional，放 project root）
pyproject.toml              Package metadata + CLI entry point + ruff config

cold_eyes/                   Package（15 模組）
  constants.py               共用常數（SCHEMA_VERSION, SEVERITY_ORDER, STATE_*, DEPLOY_FILES）
  config.py                  Policy file loader（flat YAML subset parser，無 PyYAML 依賴）
  git.py                     git_cmd（失敗 raise GitCommandError）, collect_files, is_binary, build_diff
  filter.py                  filter_file_list, rank_file_list
  prompt.py                  build_prompt_text
  claude.py                  ModelAdapter base, ClaudeCliAdapter, MockAdapter, ReviewInvocation
  review.py                  parse_review_output（含 validate_review 整合）
  schema.py                  review output schema 定義 + validate_review()
  policy.py                  apply_policy, filter_by_confidence, format_block_reason（language-aware）
  history.py                 log_to_history, aggregate_overrides, compute_stats, quality_report, prune_history, archive_history
  override.py                arm_override, consume_override（一次性 token）
  doctor.py                  run_doctor（11 checks）, run_doctor_fix, run_init
  engine.py                  run() 主管線、_resolve()、_skip()、_infra_review()
  cli.py                     argparse + dispatch（run / doctor / init / stats / quality-report / arm-override / history-prune / history-archive / aggregate-overrides）
  __init__.py
```

## 本次會話做了什麼

### 起點

接手 v1.0.0（`6cdfa9a`，197 tests，API stable）。
收到 10-patch 品質推進計畫，目標從 8.0-8.5 推到 9.5/10。

### v1.0.0 → v1.1.0：9-patch quality push

Patch 3（helper 清除）已在 v1.0.0 完成，本次執行剩餘 9 個 patch。

| 優先級 | Patch | 改了什麼 | 測試變化 |
|---|---|---|---|
| P0 | 2 State constants | 6 個 STATE_* 常數 → constants.py，policy/engine/history/tests 全改用 | 0 |
| P0 | 1 Shell fail-closed | 修 3 個靜默放行漏洞（空輸出/壞JSON/缺action），加 infra_fail handler | 0 |
| P0 | 4 Integration tests | 12 個 shell parser 測試（extract + run with controlled input） | +12 |
| P1 | 5 Release/install | pyproject.toml, install.sh, uninstall.sh, cli.py main(), version 1.1.0 | 0 |
| P1 | 6 Init/doctor --fix | `init` subcommand, `doctor --fix` auto-repair | 0 |
| P1 | 7 CI 強化 | 6-matrix (3 OS x 2 Python) + ruff lint + shellcheck | 0 |
| P2 | 8 History retention | `history-prune` (keep-days/keep-entries), `history-archive` (before date) | 0 |
| P2 | 9 Schema contract | schema.py validate_review(), parser 整合, 16 regression tests | +16 |
| P2 | 10 Quality report | `quality-report` — rates + top noisy paths + issue categories | 0 |

234 tests。

## 部署

```bash
# Option A: install script
bash install.sh

# Option B: manual
cp -r cold_eyes/ cold-review.sh cold-review-prompt.txt ~/.claude/scripts/
python ~/.claude/scripts/cold_eyes/cli.py doctor
```

## 環境變數

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
| `COLD_REVIEW_ALLOW_ONCE` | 未設 | **Deprecated.** |

## CLI 命令

| 命令 | 說明 |
|---|---|
| `run` | 執行 review（shell 呼叫） |
| `doctor` | 環境健康檢查（加 `--fix` 自動修復） |
| `init` | 在 repo 建立預設 policy + ignore 檔案 |
| `stats` | 歷史統計（`--last`, `--by-reason`, `--by-path`） |
| `quality-report` | 品質報告（rates, noisy paths, categories） |
| `aggregate-overrides` | Override 模式摘要 |
| `arm-override` | 建立一次性 override token |
| `history-prune` | 清理舊 history（`--keep-days`, `--keep-entries`） |
| `history-archive` | 歸檔指定日期前的 history（`--before`） |

## 後續方向

### 可能的下一步

- Git tag v1.1.0 — 尚未打 tag
- `pip install -e .` — pyproject.toml 已就位，可移除 cli.py 頂部 sys.path hack
- History rotation daemon — 目前 prune/archive 是手動，可加 cron 建議
- `line_hint` 實測 — 幻覺率未量化
- Coverage report — CI 已有 pytest，可加 coverage gate

### 不建議做的

- Phase 3 商業化 — 對個人用工具是過度設計
- Daemon / 常駐服務 — hook 架構已夠用
- 複雜權限模型 — 單人使用無需

## 已知問題

- `cli.py` 頂部有 `sys.path` manipulation，`pip install -e .` 後可移除
- Windows Git Bash 的 `mkdir` lock 和 `kill -0` stale detection 不如原生 Unix 可靠
- 舊 history 條目仍有 `state: "failed"`（v0.11.0 前），stats 查詢時注意
- `line_hint` 是 LLM 估計值，block 顯示加了 `~` 前綴，幻覺率未實測
