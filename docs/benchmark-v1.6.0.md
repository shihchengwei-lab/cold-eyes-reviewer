# Benchmark v1.6.0 — Opus Deep vs Sonnet Shallow

> **注意：這是單次測試數據，不是統計顯著結果。**
> LLM 的輸出具有隨機性，同樣的 case 再跑一次可能產生不同結果。
> 此數據用於建立初始觀察，不應作為準確性保證的依據。

## 測試條件

- 日期：2026-04-12
- 版本：v1.6.0
- Eval cases：24（8 true_positive, 4 acceptable, 3 false_negative, 5 stress, 4 edge）
- 門檻：threshold=critical, confidence=medium
- 每個 case 呼叫真實 model 一次（非 mock）

| 組合 | Model | Prompt | 用途 |
|---|---|---|---|
| A | opus | deep（461 tokens，6 類檢查）| source / auth / migration 的 review |
| B | sonnet | shallow（315 tokens，只看 critical）| test-only commit 的 review |

## 結果

| 組合 | Passed | Failed | 正確率 |
|---|---|---|---|
| A: opus + deep | 22/24 | 2 | 91.7% |
| B: sonnet + shallow | 21/24 | 3 | 87.5% |

## True Positive 檢出（最重要的指標）

8 個 true_positive cases（SQL injection, hardcoded secret, XSS, resource leak, missing error handling, dangling import, path traversal, eval injection）：

| 組合 | 檢出 | 漏掉 |
|---|---|---|
| A: opus + deep | 8/8 | 0 |
| B: sonnet + shallow | 8/8 | 0 |

**兩種組合都 100% 正確攔截了所有 critical 安全/正確性問題。**

## 差異分析

差異全部出在 false positive（不該 block 但 block 了）：

| Case | 類別 | 預期 | Opus Deep | Sonnet Shallow | 說明 |
|---|---|---|---|---|---|
| edge-empty-mock-response | edge | pass | **block** | **block** | 空 diff，兩個 model 都產生了不該有的 issue |
| stress-all-minor | stress | pass | **block** | pass | Opus 把 minor issue 升級為 critical |
| fn-env-var-not-secret | false_negative | pass | pass | **block** | Sonnet 把非 secret 的 env var 誤判為安全問題 |
| fn-intentional-shell-true | false_negative | pass | pass | **block** | Sonnet 把故意的 shell=True 誤判為安全問題 |

### 觀察

1. **Opus 的 FP 模式**：過度嚴格 — 把 minor issue 升級為 critical（stress-all-minor）。
2. **Sonnet 的 FP 模式**：判斷力不足 — 在 false_negative 類別（看起來危險但其實安全的 case）上誤判。shallow prompt 只看 critical，但 sonnet 對「什麼算 critical」的邊界抓得比 opus 鬆。
3. **兩者共同 FP**：edge-empty-mock-response 是 model 對空輸入的行為問題，與 prompt 無關。

## 對實際使用的意義

- **Shallow 路徑（sonnet + shallow）用在 test-only commit**。test-only commit 不會出現 fn-env-var-not-secret 或 fn-intentional-shell-true 這類 case（那些是 source code pattern），所以 sonnet 在實際 shallow 使用場景中的 FP 風險比 benchmark 數字顯示的更低。
- **Deep 路徑（opus + deep）用在 source / auth / migration commit**。opus 的 FP（stress-all-minor）是邊界 case — 全部 minor 的 diff 走 deep 路徑的機率本身就低。
- **兩者都抓到了全部 8 個真問題**。降成本的代價沒有落在最重要的指標上。

## 原始數據

- `docs/benchmark-data/opus_deep_20260412.json` — opus + deep（完整 report）
- `docs/benchmark-data/sonnet_shallow_20260412.json` — sonnet + shallow（完整 report）
- `evals/responses/opus_deep/` — 每個 case 的 opus raw response（gitignored，本地保留）
- `evals/responses/sonnet_shallow/` — 每個 case 的 sonnet raw response（gitignored，本地保留）

## 限制

1. **單次執行**：LLM 輸出非確定性。重跑可能產生不同結果。
2. **Eval cases 非真實 commit**：case 的 diff 是人工構造的，不代表真實 codebase 的 diff 分布。
3. **無 context injection 測試**：benchmark 不經過 engine pipeline，所以沒有測試 context retrieval 對 deep path 準確性的影響。測試 context 效果需要設計新的 eval 方法。
4. **24 cases 樣本量小**：不足以計算統計顯著的 precision/recall 差異。
