# Uni-Seeker Claude 工作規範

## 任務清單規則

**開始執行前：**
- 所有任務必須用 `TaskCreate` 工具新增到任務清單
- 每個任務開始執行時標記為 `in_progress`
- 完成後立即標記 `completed`，有新發現的子任務也要補上

**自我驗證要求：**
- 每個任務完成後，必須規劃並執行自我驗證（見下方格式）
- 驗證全部通過才算任務完成
- 驗證失敗要修復後重新驗證

**自我驗證格式（每個任務都要）：**
```
驗證清單：
- [ ] TypeScript build 無錯誤 (cd frontend && npx tsc --noEmit)
- [ ] 相關頁面在瀏覽器可正常載入（截圖確認）
- [ ] API 呼叫回傳正確資料（console 無 error）
- [ ] 功能邏輯正確（視任務而定）
```

## 語言規範
- 所有討論使用繁體中文

## 風格規範
- UI 採用 STRATOS 暗黑奢華交易終端風格
- 使用 `GlassPanel`, `ClippedButton`, `KpiCard`, `AmbientBackground` 等 STRATOS primitives
- CSS 變數：`var(--background)`, `var(--glass-bg)`, `var(--stock-up)`, `var(--stock-down)`, `var(--accent-cyan)`, `var(--text-muted)`

## 開發規範
- 模組化開發、低耦合、計算與 I/O 分離
- Decimal-as-string：後端數字欄位型別為 `string`，運算前呼叫 `Number()`
- 並行 agent：無依賴關係的任務必須並行執行
