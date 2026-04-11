# Cold Eyes Reviewer — 交接文件

## 現況

- **版本：** v1.3.1（master，`31cf81f`，2026-04-12）
- **分支：** master
- **測試：** 289 passed（coverage 82%，門檻 75%）
- **部署：** `~/.claude/scripts/` 已同步
- **GitHub Release：** v1.3.1 等 CI 全綠後自動建；v1.3.0、v1.2.0、v1.1.0 已有
- **版本訊號：** `__init__.py` = 1.3.1 / CHANGELOG = v1.3.1 (289 tests) / README badge / GitHub Release ✓ 一致
- **CI：** Tests workflow（3 OS × 2 Python + coverage + ruff + shellcheck）等最新 push 結果

## 架構

Claude Code Stop hook 的零上下文 code reviewer。

```
cold-review.sh              Stop hook shim（~158 行），guard + python resolve + fail-closed parser
  └→ cold_eyes/cli.py       CLI entry → engine.py → 各模組

cold-review-prompt.txt      系統 prompt 模板，placeholders: {language}
.cold-review-policy.yml     Per-repo 配置（optional，放 project root）
pyproject.toml              Package metadata + CLI entry point + ruff + pytest/coverage config

cold_eyes/                   Package（15 模組）
  constants.py               共用常數（SCHEMA_VERSION, SEVERITY_ORDER, STATE_*, DEPLOY_FILES）
  config.py                  Policy file loader（flat YAML，無 PyYAML 依賴，9 valid keys，50 content-line 上限）
  git.py                     git_cmd（encoding="utf-8"）, collect_files, is_binary, build_diff（UTF-8 byte÷4 token 估算）
  filter.py                  filter_file_list, rank_file_list
  prompt.py                  build_prompt_text
  claude.py                  ModelAdapter base, ClaudeCliAdapter（encoding="utf-8"）, MockAdapter, ReviewInvocation
  review.py                  parse_review_output（含 validate_review 整合）
  schema.py                  review output schema 定義 + validate_review()
  policy.py                  apply_policy（truncation_policy: warn/soft-pass/fail-closed）, filter_by_confidence, format_block_reason
  history.py                 log_to_history, aggregate_overrides, compute_stats, quality_report, prune（content hash dedup）, archive
  override.py                arm_override, consume_override
  doctor.py                  run_doctor（11 checks，fail 訊息含 Fix: 指引）, verify_install, run_doctor_fix, run_init
  engine.py                  run()（file_count==0 skip + coverage visibility）, _resolve(), _skip(), _infra_review()
  cli.py                     11 subcommands + --version
  __init__.py                __version__ = "1.3.1"

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
  .github/workflows/release.yml   tag 推送 → test + ruff + shellcheck → 驗 tag==__version__ → 自動建 GitHub Release
  .github/ISSUE_TEMPLATE/          bug_report.yml, feature_request.yml
  .github/PULL_REQUEST_TEMPLATE.md PR checklist

tests/                       289 tests
  test_engine.py             183 tests — engine pipeline, scope, mock adapter
  test_shell_smoke.py        28 tests — shell shim, fail-closed parser, interpreter missing, WSL detection
  test_eval.py               24 tests — case loading, deterministic, sweep, single case
  test_risk_controls.py      30 tests — truncation policy, config, state reachability, zero-file skip, CLI --version, doctor Fix:
  test_schema.py             16 tests — validate_review, parser regressions
  test_override.py           8 tests — arm/consume override token
```

## 本次會話做了什麼（2026-04-12）

### 起點

接手 v1.3.0（`d28c8bd`，288 tests）。
收到 `cold-eyes-reviewer-phase-report.md`（三階段第三方複核），綜合 9.6/10「高度可信」。
報告列出 5 個觀察點（F-1～F-5）和 3 個邊界缺口，加上 9 項改進建議。

### 執行

| # | 做了什麼 | 檔案 | 測試變化 | Commit |
|---|---------|------|---------|--------|
| P0-3 | Token 估算 `len÷4` → `len(encode("utf-8"))÷4`，中文 diff 不再低估 | `git.py:117` | 0 | `4ca6f48` |
| P0-1 | Shell 加 python interpreter 偵測，缺失時 fail-closed | `cold-review.sh` | +2 | `4ca6f48` |
| P1-4 | history prune dedup 從 `id()` 改為 `json.dumps` content hash | `history.py:325` | 0 | `4ca6f48` |
| P1-5 | config parser 加 50 行上限（只計非空白非註解行），超限 stderr warning | `config.py` | 0 | `4ca6f48` |
| P1-6 | 移除 `call_claude()` 保留函式 + 清理引用 | `claude.py`, `test_engine.py`, `architecture.md` | -1 | `4ca6f48` |
| P1-5 | release.yml 補齊 ruff + shellcheck（與 test.yml 一致） | `release.yml` | 0 | `4ca6f48` |
| P1-3 | README 修正「all states logged」→「engine-level exits logged」 | `README.md` | 0 | `4ca6f48` |
| review-fix | shell python 偵測移到 off-mode guard 之後 | `cold-review.sh` | 0 | `4ca6f48` |
| review-fix | `$PYTHON_CMD` 三處加雙引號 | `cold-review.sh` | 0 | `4ca6f48` |
| review-fix | config parser 超限改 warn+break（保留已解析條目） | `config.py` | 0 | `4ca6f48` |
| CI-fix | Ubuntu: bash 隔離到臨時 bin 目錄（防 `/usr/bin` 共存 python） | `test_shell_smoke.py` | 0 | `734efbe` |
| CI-fix | Windows: `bash --version` 驗證可用性（防 WSL bash 無 distro） | `test_shell_smoke.py` | 0 | `31cf81f` |
| release | `__init__` 1.3.0→1.3.1 + CHANGELOG v1.3.1 + tag | 版本訊號 | 0 | `ebe3f13` |

### 教訓

1. **防禦上限要計對東西**：config parser 第一版上限計全部行數（含空白和註解），Cold Eyes 自己抓到「合法 policy 含大量註解會被靜默丟棄」。改為只計有效內容行。

2. **新增的 guard 要放對位置**：python interpreter 偵測放在 off-mode guard 前面，導致 off mode 也被 python 缺失攔住。Cold Eyes 抓到後移到 guard 之後。

3. **Shell 變數要引號**：`$PYTHON_CMD` 不加引號在路徑含空白時會 word split，且加了 shellcheck CI step 就會報錯。

4. **Linux `/usr/bin` 共存問題**：限制 PATH 到 `bash_dir` 想排除 python，但 Linux 上 bash 和 python3 都在 `/usr/bin/`。修法：建臨時 bin 目錄只放 bash symlink。

5. **Windows CI 的 WSL bash 陷阱**：`shutil.which("bash")` 在 `windows-latest` 找到 WSL bash，但無 Linux distro 時所有 bash 執行都 exit 1。修法：`bash --version` 驗證可用性，不可用時 skip shell tests。

6. **v1.3.1 tag 移動兩次**：第一次 CI 失敗（Ubuntu `/usr/bin` 問題），第二次又失敗（Windows WSL 問題），tag 從 `ebe3f13` → `734efbe` → `31cf81f`。教訓同 v1.3.0：CI 全綠前不要急著打 tag。

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
| `--version` | 印出版本（`cold-eyes-reviewer 1.3.1`） |
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
- Token 估算為 `len(encode("utf-8"))÷4`（比舊版 `len÷4` 對中文準確，但仍為近似值）
- Eval benchmark mode 需要 Claude CLI 可用，CI 環境跑不了
- v1.3.1 tag 被移動兩次（CI 修正）。最終 tag 指向 `31cf81f`。
- `windows-latest` CI 上 shell smoke tests 會被 skip（WSL bash 無 distro），Windows 覆蓋靠本機 Git Bash 環境
