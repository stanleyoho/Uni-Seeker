# 2026-05-08 DailyTask

## 主任務 (Parent Ticket)

**UNI-FIN-001** — 財報頁面串接真實官方財報資料源，並建立資料來源評估報告
**UNI-FIN-002** — 台股財報自動同步：行事曆驅動 + API 讀 DB

## 需求脈絡 (Requirement Context)

### Q1: Why

現有財報頁面使用 yfinance 抓數據，屬非官方來源，資料不穩定且欄位定義不一致。需要改用官方申報數字：台股走 MOPS（透過 FinMind），美股走 SEC EDGAR（10-K/10-Q XBRL）。同時需要釐清未來可擴充的資料來源選項，以便做技術選型決策。

### Q2: Definition of Success

- 台股輸入股票代號（如 2330）→ 回傳 FinMind MOPS 來源三表真實數據
- 美股輸入代號（如 AAPL）→ 回傳 SEC EDGAR 官方 XBRL 三表數據
- ratios 計算結果合理（毛利率、淨利率等有意義的數值）
- 產出財報資料來源全面比較報告，含真實性驗證結果
- User-scope 工作規範寫入 `~/.claude/CLAUDE.md`

### Q3: Scope-out

- 暫不整合 FMP（付費方案，留待後續評估）
- TWSE OpenAPI 僅作驗證用，不作主要資料源
- 不做前端財報頁面的進一步 UI 改動（本次只動後端 provider）
- 不整合 TEJ（費用過高）

## 團隊單 (Team Subtasks)

### #1 [UNI-FIN-001][subtask] 美股財報 provider — SEC EDGAR

- 狀態: `done`
- DoD:
  - [x] `SECEdgarFinancialProvider` 可抓 10-K/10-Q XBRL 三表
  - [x] XBRL concept → yfinance 相容欄位名對應正確
  - [x] AAPL 實測毛利率、淨利率數值合理
  - [x] GOOGL Q1 2026 四項指標與官方申報完全吻合

### #2 [UNI-FIN-001][subtask] 台股財報 provider — FinMind

- 狀態: `done`
- DoD:
  - [x] `FinMindTWFinancialProvider` 並行抓三個 FinMind dataset
  - [x] Chinese `origin_name` → 英文欄位名對應正確
  - [x] 台積電 (2330) 實測毛利率、YoY 成長有意義數值
  - [x] ratios 計算可正常運作

### #3 [UNI-FIN-001][subtask] API 路由依台/美股自動選 provider

- 狀態: `done`
- DoD:
  - [x] 純數字代碼 → FinMindTWFinancialProvider
  - [x] 英文代碼 → SECEdgarFinancialProvider
  - [x] `/ratios` 端點同步更新

### #4 [UNI-FIN-001][subtask] 財報資料來源全面評估報告

- 狀態: `done`
- DoD:
  - [x] 調查 7 個美股來源、5 個台股來源
  - [x] 以 GOOGL Q1 2026 官方申報建立真實性驗證基準（4 項指標 100% 吻合）
  - [x] 完成綜合比較表格（真實性、覆蓋率、費用、穩定性、複雜度）
  - [x] 推薦方案含工作量估計
  - [x] 報告存至 `docs/financial-data-sources-analysis.md`

### #5 [UNI-FIN-001][subtask] 建立工作規範與 daily-task 工作流

- 狀態: `done`
- DoD:
  - [x] User-scope `~/.claude/CLAUDE.md` 建立（語言規範、五狀態、Verify Gate、並行分析）
  - [x] `daily-task/_TEMPLATE.md` 更新為新版格式
  - [x] `daily-task/2026-05-08-DailyTask.md` 建立

## 內部步驟 (Internal WBS)

### Batch A — 實作兩個 provider（平行）

- **T1.1** 實作 `SECEdgarFinancialProvider` — 狀態: `done`
  - 依賴: 無
  - 產出: `backend/app/modules/financial_analysis/sec_edgar_provider.py`

- **T1.2** 實作 `FinMindTWFinancialProvider` — 狀態: `done`
  - 依賴: 無
  - 產出: `backend/app/modules/financial_analysis/finmind_tw_provider.py`

### Batch B — 整合路由（依賴 Batch A）

- **T2.1** 更新 `financials.py` 加入 `_is_tw_stock()` 路由邏輯 — 狀態: `done`
  - 依賴: T1.1, T1.2
  - 產出: `backend/app/api/v1/financials.py`

### Batch C — 研究與規範（平行於 Batch A/B）

- **T3.1** 財報資料來源全面調查與比較報告 — 狀態: `done`
  - 依賴: 無
  - 產出: `docs/financial-data-sources-analysis.md`

- **T3.2** 建立 User-scope CLAUDE.md 與 daily-task 工作流 — 狀態: `done`
  - 依賴: 無
  - 產出: `~/.claude/CLAUDE.md`, `daily-task/_TEMPLATE.md`, `daily-task/2026-05-08-DailyTask.md`

## Layer Mapping (Team subtask ↔ Internal steps)

| 團隊單 | 內部步驟 |
|--------|----------|
| #1 美股 SEC EDGAR provider | T1.1 |
| #2 台股 FinMind provider | T1.2 |
| #3 API 路由 | T2.1 |
| #4 資料來源評估報告 | T3.1 |
| #5 工作規範與 daily-task | T3.2 |
| #6 API 改讀 DB | FA-T1.1 |
| #7 行事曆 Service | FA-T2.1 |
| #8 /calendar 端點 | FA-T3.1 |

---

## UNI-FIN-002 台股財報自動同步

### 團隊單

#### #6 [UNI-FIN-002][subtask] financials API 改讀 DB
- 狀態: `todo`
- DoD:
  - [ ] `GET /api/v1/financials/2330` 資料來自 `financial_statements` DB 表
  - [ ] 日誌不出現 FinMind request log
  - [ ] ratios 計算結果與直接呼叫 FinMind 相同

#### #7 [UNI-FIN-002][subtask] 台股行事曆 Service
- 狀態: `todo`
- DoD:
  - [ ] `EarningsCalendarService` 依法定截止日計算各股下次預計發布日
  - [ ] 回傳 DB 是否已有該季資料
  - [ ] Q1 截止 5/15 計算正確

#### #8 [UNI-FIN-002][subtask] 新增 /calendar 端點
- 狀態: `todo`
- DoD:
  - [ ] `GET /api/v1/financials/{symbol}/calendar` 正確回傳行事曆資料
  - [ ] 欄位包含：下次截止日、最近已有資料的季別、距截止日天數

### 內部步驟 (Internal WBS)

#### Batch A（平行）
- **FA-T1.1** `financials.py` 改讀 `financial_statements` DB — 狀態: `todo`
  - 依賴: 無
  - 產出: 更新 `backend/app/api/v1/financials.py`

- **FA-T2.1** `EarningsCalendarService` — 狀態: `todo`
  - 依賴: 無
  - 產出: `backend/app/modules/financial_analysis/earnings_calendar.py`

#### Batch B（依賴 Batch A）
- **FA-T3.1** `GET /api/v1/financials/{symbol}/calendar` 端點 — 狀態: `todo`
  - 依賴: FA-T2.1
  - 產出: 更新 `backend/app/api/v1/financials.py`

### 驗證清單（Verify Gate）
- [ ] `GET /api/v1/financials/2330` 資料來自 DB，日誌無 FinMind request
- [ ] `/calendar` 回傳正確截止日（今日 5/8，Q1 截止 5/15）
- [ ] `FinancialsSyncTask` 手動觸發後 DB 新增資料，API 可讀到

## 已完成 (Completed)

- [x] **T1.1 SECEdgarFinancialProvider** `done`
  - 驗證：AAPL 20 期三表正常；GOOGL Q1 2026 Revenue/NetIncome/Assets/OperatingIncome 完全吻合官方申報

- [x] **T1.2 FinMindTWFinancialProvider** `done`
  - 驗證：台積電 (2330) 三表各 20 期；毛利率 62.3%、YoY 成長 20.5% 數值合理

- [x] **T2.1 financials.py 路由更新** `done`
  - 驗證：`2330` → FinMind；`AAPL` → EDGAR；兩端點均正常

- [x] **T3.1 財報資料來源評估報告** `done`
  - 驗證：報告存至 `docs/financial-data-sources-analysis.md`，含真實性驗證表格與推薦方案

- [x] **T3.2 工作規範建立** `done`
  - 驗證：`~/.claude/CLAUDE.md` 建立；`_TEMPLATE.md` 更新為新版格式

## Blockers

(none)

## Decisions

- **SEC EDGAR 作美股主來源**：完全免費、官方原始資料、驗證誤差為零。yfinance 廢棄。
- **FinMind 作台股主來源**：MOPS 來源可信度等同官方、免費額度足夠（600次/小時）。
- **FMP 暫不整合**：功能上是 EDGAR 的便利包裝，待業務需求提升再評估（$22/月起）。
- **TWSE OpenAPI 列為驗證工具**：僅最新季、~68 家，無法作主來源，但可交叉比對。

---

## Task 狀態定義

- `todo` — 計畫中、尚未開始或極早期
- `processing` — 進行中
- `pending` — 卡住，等外部條件（必須註明卡什麼）
- `verify` — 實作完，驗證中
- `done` — 全部驗證通過

## Verify Gate

- 任何 task 必須先 → `verify` → `done`
- **不可**從 `processing` 直接跳 `done`
- 驗證失敗 → 退回 `processing`
