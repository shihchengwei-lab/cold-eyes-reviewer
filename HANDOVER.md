# Cold Eyes Reviewer — 交接文件

## 現況

- **版本：** v1.2.0-dev（master，2026-04-11）
- **分支：** master
- **測試：** 283 passed
- **部署：** `~/.claude/scripts/` 需重新同步，`doctor` all_ok
- **GitHub Release：** v1.1.0 已建立

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
  config.py                  Policy file loader（flat YAML subset parser，無 PyYAML 依賴）
  git.py                     git_cmd, collect_files, is_binary, build_diff
  filter.py                  filter_file_list, rank_file_list
  prompt.py                  build_prompt_text
  claude.py                  ModelAdapter base, ClaudeCliAdapter, MockAdapter, ReviewInvocation
  review.py                  parse_review_output（含 validate_review 整合）
  schema.py                  review output schema 定義 + validate_review()
  policy.py                  apply_policy（含 truncation_policy）, filter_by_confidence, format_block_reason
  history.py                 log_to_history, aggregate_overrides, compute_stats, quality_report, prune, archive
  override.py                arm_override, consume_override
  doctor.py                  run_doctor（11 checks）, verify_install, run_doctor_fix, run_init
  engine.py                  run()（含 coverage visibility）、_resolve()、_skip()、_infra_review()
  cli.py                     11 subcommands（+eval, +verify-install）
  __init__.py

evals/                       Evaluation framework
  eval_runner.py             deterministic / benchmark / sweep modes
  cases/                     14 eval case fixtures (6 TP, 4 OK, 4 stress)

docs/                        Documentation
  release-checklist.md       Release process checklist
  evaluation.md              Eval system + threshold sweep results
  scope-strategy.md          Scope selection guide + truncation interactions
  history-schema.md          JSONL v2 field reference + migration notes
  tuning.md                  Tuning playbook (diagnostic workflow)
  agent-setup.md             5-step agent installation guide
  samples/                   5 sample output JSON files
  alpha-scope.md             (legacy) v0.2.0 scope document

tests/                       283 tests
  test_engine.py             184 tests
  test_shell_smoke.py        26 tests
  test_eval.py               24 tests
  test_risk_controls.py      25 tests
  test_schema.py             16 tests
  test_override.py           8 tests
```

## 本次會話做了什麼

### 起點

接手 v1.1.0（`f3db917`，234 tests）。
收到 95-plan（agent-native 版），目標從 ~89 推到 95/100。

### v1.1.0 → 95-plan：5 Phase 執行

| Phase | 做了什麼 | 測試變化 |
|-------|---------|---------|
| 1 Release discipline | GitHub Release v1.1.0 + release checklist | 0 |
| 2 Evaluation pack | 14 eval cases + eval_runner (deterministic/benchmark/sweep) + CLI eval + docs/evaluation.md | +24 |
| 3 Risk controls | truncation_policy (warn/soft-pass/fail-closed) + coverage visibility + scope strategy doc | +25 |
| 4 Governance docs | history-schema.md + tuning.md + 5 sample JSON | 0 |
| 5 Agent-native polish | verify-install command + agent-setup.md | 0 |

283 tests。

### 新增的核心能力

1. **Eval framework** — `python cli.py eval --eval-mode deterministic` 跑 14 cases 驗證 decision boundary
2. **Threshold sweep** — `--eval-mode sweep` 產出 precision/recall/F1 for 6 combinations，資料支持預設值 critical/medium (F1=1.0)
3. **Truncation policy** — `truncation_policy: fail-closed` 可讓大 diff 無條件 block；`soft-pass` 可讓 truncated + no issues 不 block
4. **Coverage visibility** — outcome 包含 `reviewed_files`, `total_files`, `coverage_pct`
5. **verify-install** — machine-readable install check for agents

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
| `run` | 執行 review |
| `doctor` | 環境健康檢查（加 `--fix` 自動修復） |
| `verify-install` | Machine-readable 安裝驗證（3 critical checks） |
| `init` | 在 repo 建立預設 policy + ignore |
| `eval` | 跑 eval（`--eval-mode deterministic/benchmark/sweep`） |
| `stats` | 歷史統計 |
| `quality-report` | 品質報告 |
| `aggregate-overrides` | Override 模式摘要 |
| `arm-override` | 建立一次性 override token |
| `history-prune` | 清理舊 history |
| `history-archive` | 歸檔 history |

## 後續方向

### 可能的下一步

- Git tag v1.2.0 — 打 tag 並建 Release
- 更多 eval cases — 目前 14 個是最小可行集
- Benchmark mode 實測 — 用真實 model 跑 eval，量化 model-specific accuracy
- `line_hint` 幻覺率量化 — 可加入 eval framework
- Coverage gate — CI 可加 `pytest --cov` threshold

### 不建議做的

- Phase 3 商業化 — 個人用工具不需要
- GUI / dashboard — 底層 eval 和 risk policy 才剛建好
- Daemon / 常駐服務 — hook 架構已夠用

## 已知問題

- `cli.py` 頂部有 `sys.path` manipulation，`pip install -e .` 後可移除
- Windows Git Bash 的 `mkdir` lock 和 `kill -0` stale detection 不如原生 Unix 可靠
- 舊 history 條目仍有 `state: "failed"`（v0.11.0 前），stats 查詢時注意
- `line_hint` 是 LLM 估計值，block 顯示加了 `~` 前綴，幻覺率未實測
- Token 估算仍為 len÷4 粗估
