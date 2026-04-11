# Alpha Scope — v0.2.0

本輪目標：把 Cold Eyes Reviewer 從「可跑的原型」推到「可信的 alpha」。

## 本輪要做的事

1. **review 失敗可見** — 所有 exit path 寫入 history，標記 state（skipped / failed / passed / blocked）
2. **block 分級化** — severity（critical / major / minor）+ 可調 threshold，不再一刀切
3. **排除低價值檔案** — `.cold-review-ignore` + 內建預設，lockfile / generated / minified 不進 review
4. **風險排序 diff** — 高風險路徑優先進 token 預算，不再只用 `head -n`
5. **override 機制** — `COLD_REVIEW_ALLOW_ONCE=1` 單次放行，`report` 模式降級，override 留紀錄
6. **正規化 schema** — issue 加 severity / confidence / category / file 欄位，history 加 version / state / diff_stats
7. **fixture tests + CI** — pytest 測試骨架，GitHub Actions workflow，核心行為有回歸基線
8. **精簡 prompt** — policy 由 code 撐住，prompt 回歸輔助角色
9. **重寫 README** — 承諾與實際行為對齊，補故障模式說明與 adoption path

## 本輪不做的事

- 不做 dashboard
- 不做多 reviewer 編排
- 不做複雜 UI
- 不做跨 session attribution
- 不做真正靜態分析器
- 不做 history 自動 rotation
- 不做 `docs/schema.md` 或 `docs/false-positive-playbook.md`
- 不做更細的人格系統

## 成功標準

回答以下五題，全部為「是」才算完成：

1. reviewer 沒跑成功時，使用者能不能明確知道？
2. 小問題還會不會亂 block？
3. 大型垃圾 diff 還會不會吃掉 token 預算？
4. 使用者能不能排除固定誤報來源？
5. 改 prompt 時能不能用測試知道有沒有退化？
