# Cold Eyes Reviewer — 交接文件

## 現況

- **版本：** v1.2.0（master，`69b1bfd`，2026-04-11）
- **分支：** master
- **測試：** 283 passed
- **部署：** `~/.claude/scripts/` 已同步
- **GitHub Release：** v1.1.0 已建立；v1.2.0 尚未打 tag / Release
- **版本訊號：** `__init__.py` = 1.2.0 / About = 283 tests / CHANGELOG = v1.2.0 ✓ 一致

## 架構

Claude Code Stop hook 的零上下文 code reviewer。

```
cold-review.sh              Stop hook shim（~142 行），guard + fail-closed parser
  └→ cold_eyes/cli.py       CLI entry → engine.py → 各模組

cold-review-prompt.txt      系統 prompt 模板，placeholders: {language}
.cold-review-policy.yml     Per-repo 配置（optional，放 project root）
pyproject.toml              Package metadata + CLI entry point + ruff config

cold_eyes/                   Package（15 模組）
  constants.py               共用常數（SCHEMA_VERSION, SEVERITY_ORDER, STATE_*, DEPLOY_FILES）
  config.py                  Policy file loader（flat YAML，無 PyYAML 依賴，9 valid keys 含 truncation_policy）
  git.py                     git_cmd（encoding="utf-8"）, collect_files, is_binary, build_diff
  filter.py                  filter_file_list, rank_file_list
  prompt.py                  build_prompt_text
  claude.py                  ModelAdapter base, ClaudeCliAdapter（encoding="utf-8"）, MockAdapter, ReviewInvocation
  review.py                  parse_review_output（含 validate_review 整合）
  schema.py                  review output schema 定義 + validate_review()
  policy.py                  apply_policy（truncation_policy: warn/soft-pass/fail-closed）, filter_by_confidence, format_block_reason
  history.py                 log_to_history, aggregate_overrides, compute_stats, quality_report, prune, archive
  override.py                arm_override, consume_override
  doctor.py                  run_doctor（11 checks）, verify_install（3 critical checks）, run_doctor_fix, run_init
  engine.py                  run()（coverage visibility: reviewed_files/total_files/coverage_pct）, _resolve(), _skip(), _infra_review()
  cli.py                     11 subcommands: run, doctor, verify-install, init, eval, stats, quality-report, aggregate-overrides, arm-override, history-prune, history-archive
  __init__.py                __version__ = "1.2.0"

evals/                       Evaluation framework
  eval_runner.py             deterministic / benchmark / sweep — 測 parse_review_output → apply_policy 的 decision boundary
  cases/                     14 eval case fixtures（6 true_positive, 4 acceptable, 4 stress）

docs/                        6 份文件 + 5 份 sample + 1 legacy
  release-checklist.md       Release process checklist（7 步）
  evaluation.md              Eval system + threshold sweep results + 預設值理由
  scope-strategy.md          4 種 scope 的適用場景 + truncation 交互
  history-schema.md          JSONL v2 全 field 規格 + 6 種 state 範例 + v1→v2 migration
  tuning.md                  調參 playbook（diagnostic workflow + 何時改什麼）
  agent-setup.md             5 步 agent 安裝指南 + troubleshooting
  samples/                   pass_outcome, block_outcome, history_entry, quality_report, stats_output
  alpha-scope.md             (legacy) v0.2.0 scope document

tests/                       283 tests
  test_engine.py             184 tests — engine pipeline, scope, mock adapter
  test_shell_smoke.py        26 tests — shell shim, fail-closed parser
  test_eval.py               24 tests — case loading, deterministic, sweep, single case
  test_risk_controls.py      25 tests — truncation policy (warn/soft-pass/fail-closed), config, coverage, state reachability
  test_schema.py             16 tests — validate_review, parser regressions
  test_override.py           8 tests — arm/consume override token
```

## 本次會話做了什麼

### 起點

接手 v1.1.0（`f3db917`，234 tests）。
收到 `cold-eyes-reviewer-95-plan-agent-native.md`，目標從 ~89 推到 95/100。
核心論點：差的不是功能，而是**可信度**（eval 證據、truncation 可控性、治理文件）。

### 執行

| Phase | 做了什麼 | 新增測試 | Commit |
|-------|---------|---------|--------|
| 1 Release discipline | GitHub Release v1.1.0 + `docs/release-checklist.md` | 0 | `bf55b17` |
| 2 Evaluation pack | 14 eval cases + `evals/eval_runner.py` + CLI `eval` + `docs/evaluation.md` | +24 | `bf55b17` |
| 3 Risk controls | `truncation_policy` (warn/soft-pass/fail-closed) + coverage visibility + `docs/scope-strategy.md` | +25 | `bf55b17` |
| 4 Governance docs | `docs/history-schema.md` + `docs/tuning.md` + 5 sample JSON | 0 | `bf55b17` |
| 5 Agent-native polish | `verify-install` command + `docs/agent-setup.md` | 0 | `bf55b17` |
| fix | `__init__` 1.1.0→1.2.0, About 234→283 tests, CHANGELOG 去掉 unreleased | 0 | `0dffa33` |
| fix | `git.py` subprocess 加 `encoding="utf-8"`（Windows GBK 崩潰） | 0 | `189d948` |
| fix | `claude.py` subprocess 加 `encoding="utf-8"`（同上，stdin 寫入端） | 0 | `69b1bfd` |

### 教訓

1. **版本訊號一致性**：第一次 push 時 `__init__.py` 仍是 1.1.0、About 仍顯示 234 tests。每次 push 前必須驗四個訊號：`__version__`、About、CHANGELOG、test count。

2. **Windows subprocess encoding**：Python 在 Windows 上 `subprocess.run(text=True)` 預設用系統編碼（中文 Windows = GBK）。所有 subprocess 都必須顯式指定 `encoding="utf-8"`，否則任何非 GBK 字元（中文 docs 裡的 ✓、UTF-8 中文等）會導致 engine 崩潰，觸發 fail-closed 擋住每一次 commit。修了兩處：`git.py:git_cmd()` 和 `claude.py:ClaudeCliAdapter._call()`。

### 新增的核心能力

1. **Eval framework** — `python cli.py eval --eval-mode deterministic` 跑 14 cases，驗證 decision boundary
2. **Threshold sweep** — `--eval-mode sweep` 產出 6 組合的 precision/recall/F1，資料支持 critical/medium (F1=1.0)
3. **Truncation policy** — `truncation_policy: fail-closed` 大 diff 無條件 block；`soft-pass` truncated + no issues 不 block
4. **Coverage visibility** — outcome 含 `reviewed_files`, `total_files`, `coverage_pct`
5. **verify-install** — machine-readable 3-check install verification

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
| `COLD_REVIEW_TRUNCATION_POLICY` | `warn` | warn / soft-pass / fail-closed |

## CLI 命令

| 命令 | 說明 |
|---|---|
| `run` | 執行 review（加 `--truncation-policy` 可指定截斷策略） |
| `doctor` | 環境健康檢查（加 `--fix` 自動修復） |
| `verify-install` | Machine-readable 安裝驗證（3 critical checks） |
| `init` | 在 repo 建立預設 policy + ignore |
| `eval` | 跑 eval（`--eval-mode deterministic/benchmark/sweep`） |
| `stats` | 歷史統計（`--last`, `--by-reason`, `--by-path`） |
| `quality-report` | 品質報告（rates, noisy paths, categories） |
| `aggregate-overrides` | Override 模式摘要 |
| `arm-override` | 建立一次性 override token |
| `history-prune` | 清理舊 history（`--keep-days`, `--keep-entries`） |
| `history-archive` | 歸檔指定日期前的 history（`--before`） |

## 後續方向

### 可能的下一步

- Git tag v1.2.0 + GitHub Release — 版本訊號已對齊，可以打
- 更多 eval cases — 目前 14 個是最小可行集，隨實際使用擴充
- Benchmark mode 實測 — `eval --eval-mode benchmark --model opus` 用真實 model 量化 accuracy
- `line_hint` 幻覺率 — 可在 eval framework 加案例測量
- Coverage gate — CI 加 `pytest --cov` threshold
- `pip install -e .` — pyproject.toml 已就位，裝完可移除 `cli.py` 頂部 sys.path hack

### 不建議做的

- 商業化 — 個人用工具不需要
- GUI / dashboard — 底層 eval 和 risk policy 才剛建好，先累積資料
- Daemon / 常駐服務 — hook 架構已夠用
- 更花俏的 prompt — 這階段上限不在 prompt

## 已知問題

- `cli.py` 頂部有 `sys.path` manipulation，`pip install -e .` 後可移除
- Windows Git Bash 的 `mkdir` lock 和 `kill -0` stale detection 不如原生 Unix 可靠
- 舊 history 條目仍有 `state: "failed"`（v0.11.0 前），stats 查詢時注意
- `line_hint` 是 LLM 估計值，block 顯示加了 `~` 前綴，幻覺率未實測
- Token 估算仍為 len÷4 粗估
- Eval benchmark mode 需要 Claude CLI 可用，CI 環境跑不了
