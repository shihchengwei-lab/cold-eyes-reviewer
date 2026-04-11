# Cold Eyes Reviewer — 交接文件

## 現況

- **版本：** v0.6.0（Phase 1 Alpha，2026-04-11）
- **分支：** master
- **測試：** 135 passed
- **部署：** `~/.claude/scripts/` 需同步，4 個檔案

## 架構

Claude Code Stop hook 的零上下文 code reviewer。

```
cold-review.sh              Stop hook 入口（~120 行），只跑 guard checks
  ├→ cold-review-helper.py  Shell-facing utilities（parse-hook、log-state）
  └→ cold_review_engine.py  核心：diff 建構、Claude CLI 呼叫、policy、confidence 過濾、history
cold-review-prompt.txt      系統 prompt 模板，唯一 placeholder 是 {language}
```

engine 是主路徑，shell 是入口，helper 是 shell 呼叫的工具函式。

## 本次會話做了什麼

### 起點

收到 `cold-eyes-reviewer-product-plan.md`（基於 v0.3.0 反饋撰寫的產品計畫書），以此為藍圖進行產品迭代。

### v0.5.0（`adf19cf`）— Phase 0 收尾

計畫書 Phase 0 大部分已由 v0.4.0 完成。v0.5.0 關閉剩餘缺口：

1. **Truncation 警告寫進 block message** — `apply_policy()` 接收 truncated 狀態，block 時顯示 `⚠ 審查不完整：diff 超過 token 預算，N 個檔案未審查`。FinalOutcome 新增 `truncated` + `skipped_count`。
2. **CHANGELOG 補齊** — 補寫 v0.3.0 和 v0.4.0。
3. **History log 補 min_confidence** — 每筆 history entry 記錄 confidence 門檻。
4. **Helper build-prompt 去重** — 改為呼叫 engine 的 `build_prompt_text()`，失敗時 fallback 本地邏輯。
5. **Engine CLI 加 --confidence / --language** — shell 顯式傳入，不再只靠 env var 隱式繼承。
6. **8 new tests** — truncation visibility、history confidence、helper dedup。

### v0.5.1（`ecd0bd7`）— README 架構澄清

被反饋「README 讓 engine 看起來像配角」。修正：
- 流程圖拆成兩層，標出 shell（guard checks only）和 engine（all review logic）
- Files 表 engine 排第一，標 "Core"

### v0.5.2（`c2fcf69`）— CHANGELOG 補齊 + helper 描述修正

- CHANGELOG 補 v0.5.0 和 v0.5.1
- Helper 從 "Legacy shell interface" 改為 "Shell-facing utilities"（它每次跑都被呼叫，不是 legacy）

## 部署

```bash
cp cold-review.sh cold-review-helper.py cold_review_engine.py cold-review-prompt.txt ~/.claude/scripts/
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

Shell 顯式傳 `--confidence`、`--language`、`--scope` 給 engine。engine 內 `os.environ.get()` 保留作為 fallback。

## 後續計畫

Phase 1+ 計畫在 `~/Desktop/cold-eyes-phase1-plan.md`：

- **Phase 1（Alpha）已完成：** doctor 命令、staged scope、line_hint、schema_version、策略預設文件化
- **Phase 1 未做：** feedback loop（override_reason）
- **Phase 2（Team Beta）：** CI/PR mode、repo policy、dashboard、override governance
- **Phase 3（商業化）：** open-core 模式

## 待辦 / 已知問題

- feedback loop（Phase 1.4）未做：override_reason 欄位、聚合 false-positive 資料
- Helper 的 parse-review、filter-files、rank-files 等指令仍有與 engine 重複的常數和邏輯。build-prompt 已去重，其餘未動。兩者共存但 engine 是主路徑。
- line_hint 的 LLM 幻覺率未實測。prompt 已限制「不確定就留空」，但需要真實 diff 驗證。
- HANDOVER.md 未納入 git（untracked）。
