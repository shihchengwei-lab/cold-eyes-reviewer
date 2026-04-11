# Cold Eyes Reviewer — 交接文件

## 現況

- **版本：** v1.3.0（master，`271aa4a`，2026-04-11）
- **分支：** master
- **測試：** 288 passed（coverage 80%，門檻 75%）
- **部署：** `~/.claude/scripts/` 已同步
- **GitHub Release：** v1.3.0 已建立（release workflow 自動建），v1.2.0、v1.1.0 也有
- **版本訊號：** `__init__.py` = 1.3.0 / CHANGELOG = v1.3.0 (288 tests) / README badge / GitHub Release ✓ 一致
- **CI：** Tests workflow（3 OS × 2 Python + coverage + ruff + shellcheck）全綠

## 架構

Claude Code Stop hook 的零上下文 code reviewer。

```
cold-review.sh              Stop hook shim（~142 行），guard + fail-closed parser
  └→ cold_eyes/cli.py       CLI entry → engine.py → 各模組

cold-review-prompt.txt      系統 prompt 模板，placeholders: {language}
.cold-review-policy.yml     Per-repo 配置（optional，放 project root）
pyproject.toml              Package metadata + CLI entry point + ruff + pytest/coverage config

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
  doctor.py                  run_doctor（11 checks，fail 訊息含 Fix: 指引）, verify_install, run_doctor_fix, run_init
  engine.py                  run()（file_count==0 skip + coverage visibility）, _resolve(), _skip(), _infra_review()
  cli.py                     11 subcommands + --version
  __init__.py                __version__ = "1.3.0"

evals/                       Evaluation framework
  eval_runner.py             deterministic / benchmark / sweep
  cases/                     14 eval case fixtures（6 true_positive, 4 acceptable, 4 stress）

docs/                        11 份文件 + 5 份 sample + 1 legacy
  architecture.md            三層架構、data flow、模組職責、設計決策
  failure-modes.md           六種狀態、infra failure 分類、truncation 分析、false positive 處理
  troubleshooting.md         8 個問題/解法對
  release-checklist.md       Release process checklist（含 coverage gate + release workflow）
  evaluation.md              Eval system + threshold sweep results + 預設值理由
  scope-strategy.md          4 種 scope 的適用場景 + truncation 交互
  history-schema.md          JSONL v2 全 field 規格 + 6 種 state 範例 + v1→v2 migration
  tuning.md                  調參 playbook（diagnostic workflow + 何時改什麼）
  agent-setup.md             5 步 agent 安裝指南 + troubleshooting
  version-policy.md          SemVer 規則 + 四處版本訊號定義
  support-policy.md          Python/OS/Shell 支援矩陣 + CI 測試範圍
  roadmap.md                 當前優先、可能方向、明確不做
  samples/                   pass_outcome, block_outcome, history_entry, quality_report, stats_output
  alpha-scope.md             (legacy) v0.2.0 scope document

治理文件（根目錄）
  CONTRIBUTING.md            開發設定、code style、commit 慣例、部署模型
  SECURITY.md                漏洞揭露、範圍、信任邊界
  LICENSE                    MIT

GitHub 模板
  .github/workflows/test.yml      3 OS × 2 Python + ruff + shellcheck + coverage
  .github/workflows/release.yml   tag 推送 → test → 驗 tag==__version__ → 自動建 GitHub Release
  .github/ISSUE_TEMPLATE/          bug_report.yml, feature_request.yml
  .github/PULL_REQUEST_TEMPLATE.md PR checklist

tests/                       288 tests
  test_engine.py             184 tests — engine pipeline, scope, mock adapter
  test_shell_smoke.py        26 tests — shell shim, fail-closed parser
  test_eval.py               24 tests — case loading, deterministic, sweep, single case
  test_risk_controls.py      30 tests — truncation policy, config, state reachability, zero-file skip, CLI --version, doctor Fix:
  test_schema.py             16 tests — validate_review, parser regressions
  test_override.py           8 tests — arm/consume override token
```

## 本次會話做了什麼

### 起點

接手 v1.2.0（`7a6d2c8`，283 tests）。
收到 `cold-eyes-reviewer-92plus-self-controlled-plan.md`，評分 72/100，目標推到 92+。
核心論點：功能已到位，差在**治理骨架空白、品質證據不可驗、邊界揭露不完整**。

### 執行

| # | 做了什麼 | 新增測試 | Commit |
|---|---------|---------|--------|
| Phase A | CONTRIBUTING.md + SECURITY.md + issue/PR templates + version-policy + support-policy + roadmap | 0 | `3405e1b` |
| Phase B | CLI `--version` + doctor 9 處 fail 訊息加 `Fix:` 指引 | +4 | `3405e1b` |
| Phase C | pyproject.toml pytest/coverage 設定 + test.yml 加 coverage + release.yml | 0 | `3405e1b` |
| Phase D | architecture.md + failure-modes.md + troubleshooting.md + release-checklist 更新 | 0 | `3405e1b` |
| Phase D | README badge + 新 docs 連結 + Contributing/Security 段 | 0 | `3405e1b` |
| Phase D | `__init__` 1.2.0→1.3.0 + CHANGELOG v1.3.0 + HANDOVER 更新 | 0 | `3405e1b` |
| fix | engine.py: `file_count==0` 時 skip（防空 diff 觸發 infra_failed block） | +1 | `036b47c` |
| docs | CHANGELOG/HANDOVER test count 287→288 對齊 | 0 | `9ff8c86` |
| docs | HANDOVER 重寫（完整 v1.3.0 交接） | 0 | `db64776` |
| fix | shell test: 隔離 HOME 防 CI lock 衝突（flaky test 修復） | 0 | `271aa4a` |

### 教訓

1. **Bugfix 後必須重新驗訊號**：v1.3.0 commit 寫 287 tests，隨後 bugfix 加了 1 test 變 288，CHANGELOG 和 HANDOVER 沒同步更新就 push 了。規則：任何改變 test count 的 commit → push 前 grep 舊數字。

2. **空 diff 的 infra_failed**：部署後 Stop hook 立刻觸發 block。原因：commit 後 working tree 乾淨，所有檔案 diff 為空字串，`file_count=0`，但 truncation notice 讓 `diff_text` 非空，engine 繼續呼叫 Claude，拿到空回應 → parse error → infra_failed → block。修法：engine.py 加 `file_count == 0` skip 條件。

3. **Ruff E402 in tests**：test 檔案有 `sys.path` manipulation 導致 import 在前面，加 E402 到 pyproject.toml 的 per-file-ignores。

4. **Doctor detail 行過長**：加了 Fix: 指引後有 3 行超過 130 字元限制，用中間變數拆行修正。

5. **CI flaky test**：`test_skips_outside_git` 在 CI 上穩定失敗。原因：Tests workflow 和 Release workflow 平行跑，共用 `$HOME/.claude/.cold-review-lock.d/`，一個 workflow 的 shell test 佔住 lock，另一個拿到 "another review in progress"。修法：測試用隔離的 `HOME`（tmpdir + `.claude/` 預建）。第一次修只清 lock（不夠），第二次改用獨立 HOME 才真正解決。

### 本次新增的核心能力

1. **治理骨架** — CONTRIBUTING、SECURITY、issue/PR templates、version/support policy、roadmap 全部到位
2. **CI coverage gate** — pytest-cov 75% 門檻（實際 80%），每次 push 都跑 coverage
3. **Release workflow** — tag 推送自動跑 test + 驗 tag==__version__ + 建 GitHub Release
4. **CLI `--version`** — `python cli.py --version` → `cold-eyes-reviewer 1.3.0`
5. **Actionable doctor** — 所有 fail 訊息含 `Fix:` 修復指引
6. **Architecture doc** — 三層架構、data flow、15 模組職責、設計決策
7. **Failure modes doc** — 六種狀態完整分析、infra failure 分類、truncation 策略比較
8. **Troubleshooting** — 8 個常見問題的診斷/修復對
9. **Zero-file skip** — engine 在 `file_count==0` 時直接 skip，不呼叫 Claude

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
| `--version` | 印出版本（`cold-eyes-reviewer 1.3.0`） |
| `run` | 執行 review（加 `--truncation-policy` 可指定截斷策略） |
| `doctor` | 環境健康檢查（fail 訊息含 Fix: 指引；加 `--fix` 自動修復） |
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

- 更多 eval cases — 目前 14 個是最小可行集，隨實際使用擴充
- Benchmark mode 實測 — `eval --eval-mode benchmark --model opus` 用真實 model 量化 accuracy
- `line_hint` 幻覺率 — 可在 eval framework 加案例測量
- `pip install -e .` — pyproject.toml 已就位，但部署模型是 `cp -r`，不建議改（評估過，見下方）

### 不建議做的

- **改部署模型** — 評估過 `pip install -e .`，結論：拿 4 行 sys.path hack 換來 Python 環境耦合 + repo 目錄綁定 + Windows 脆弱性，不值得。Stop hook 需要蠢但堅固的部署。
- 商業化 — 個人用工具不需要
- GUI / dashboard — 底層 eval 和 risk policy 才剛建好，先累積資料
- Daemon / 常駐服務 — hook 架構已夠用
- 更花俏的 prompt — 這階段上限不在 prompt

## 已知問題

- `cli.py` 頂部有 `sys.path` manipulation — 部署模型所需，不是 bug（見「不建議做的」）
- Windows Git Bash 的 `mkdir` lock 和 `kill -0` stale detection 不如原生 Unix 可靠
- 舊 history 條目仍有 `state: "failed"`（v0.11.0 前），stats 查詢時注意
- `line_hint` 是 LLM 估計值，block 顯示加了 `~` 前綴，幻覺率未實測
- Token 估算仍為 len÷4 粗估
- Eval benchmark mode 需要 Claude CLI 可用，CI 環境跑不了
- v1.3.0 tag 被刪除重建過兩次（第一次指向 pre-bugfix commit，第二次因 CI flaky test 失敗）。最終 tag 指向 `271aa4a`，release workflow 全綠，GitHub Release 已建立。
