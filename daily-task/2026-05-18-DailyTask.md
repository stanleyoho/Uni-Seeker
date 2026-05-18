# 2026-05-18 DailyTask

## 主任務 (Parent Ticket)

**UNI-FIN-001/002** — 財報自動同步架構 handoff 紀錄（本日為進度快照，供下次繼續）

## 需求脈絡 (Requirement Context)

### Q1: Why

台股美股財報是判斷公司體質的核心，需要自動化抓取官方申報數字、存 DB、並在財報頁顯示。

### Q2: Definition of Success

行事曆監控 → 新財報發布後自動觸發 FinMind 抓取 → 存 `financial_statements` DB → 前端財報頁讀 DB 顯示（不再每次打 FinMind live）。

### Q3: Scope-out

本階段只做台股；美股 SEC EDGAR 已有 live provider，DB 同步留下一階段。

---

## 當前狀態快照（2026-05-18）

### 分支：`feat/stratos-migration`

最新 commit：`8edd331 feat(obs): Uni-Seeker Prometheus business metrics + /metrics`

**本 session（5/8）完成並合入分支的工作：**

| commit | 內容 |
|--------|------|
| `fe5382b` | TW financials DB-first read + earnings calendar |
| `c4aa7b8` | SEC EDGAR & FinMind providers + API routing |
| `ffd4b83` | Financials page STRATOS migration（4-tab layout） |

**5/8 之後其他人的提交（已在分支上）：**

| commit | 內容 |
|--------|------|
| `8edd331` | Prometheus business metrics / /metrics endpoint |
| `c8c119a` | Sentry SDK init |
| `10c7168` | trace_id ContextVar + FastAPI middleware |
| `4137c52` | structlog logging config |
| `6b53127` | Watchlist CRUD API（Free tier 10-stock limit） |
| `f60e208` | Industry aggregates module |

---

## 任務列表 (Task List)

### 已完成 `done`

#### UNI-FIN-001

- [x] `SECEdgarFinancialProvider` — 美股 10-K/10-Q XBRL，GOOGL Q1 2026 四項指標 100% 吻合官方申報
- [x] `FinMindTWFinancialProvider` — 台股 MOPS 三表，台積電毛利率 62.3% 驗證正常
- [x] `financials.py` API 路由（純數字 → FinMind，英文 → EDGAR）
- [x] 財報資料來源全面評估報告（`docs/financial-data-sources-analysis.md`）
- [x] User-scope `~/.claude/CLAUDE.md` 工作規範建立

#### UNI-FIN-002

- [x] `tw_db_reader.py` — 讀 `financial_statements` DB，FinMind type code → 顯示名對應
- [x] `earnings_calendar.py` — 台股法定截止日計算（Q1→5/15, Q2→8/14, Q3→11/14, Q4→3/31）
- [x] `financials.py` DB-first 策略（TW 股先讀 DB，miss 才 fallback FinMind live）
- [x] `GET /api/v1/financials/{symbol}/calendar` 端點

### 待議 / 下次繼續 `todo`

- [ ] **UNI-FIN-002 驗證**：實際啟動後端，對 2330 呼叫 `/financials/2330`，確認日誌無 FinMind request（DB 有資料才算過） `pending` — 等 DB 有同步資料
- [ ] **FinancialsSyncTask 實際跑一次**：手動觸發或等每日 17:30 自動執行，確認 DB 有台股季報資料
- [ ] **FMP 整合**（美股三表標準化 + 計算指標 FCF/EBITDA） `todo`
- [ ] **TWSE OpenAPI 交叉驗證工具**（台股數據品質保障） `todo`
- [ ] **美股財報 DB 同步**（SEC EDGAR → `financial_statements`，類似 FinancialsSyncTask） `todo`

---

## 已完成 (Completed)

- [x] **UNI-FIN-001 完整財報架構** `done`
  - 真實資料來源：台股 FinMind（MOPS），美股 SEC EDGAR（10-K/10-Q XBRL）
  - 評估報告含可行性比較、費用、穩定性分析
  - 財報頁面 STRATOS 遷移（4 tab: 總覽/損益表/資產負債表/現金流量表）

- [x] **UNI-FIN-002 DB-first 架構** `done`
  - 台股財報自動同步已有基礎建設（`FinancialsSyncTask` 每天 17:30 自動執行）
  - API 已改為 DB-first + live fallback
  - 行事曆 service 可計算各股下次截止日

---

## Blockers

- `UNI-FIN-002 驗證` 需要 DB 實際有同步資料才能驗證 API 讀 DB 路徑，需等 `FinancialsSyncTask` 自動跑或手動觸發一次

---

## Decisions

- **美股主來源：SEC EDGAR**（免費、官方、零誤差）
- **台股主來源：FinMind**（MOPS 來源，600次/小時免費額度足夠）
- **FMP 暫不整合**：留待業務成長再評估（$22/月起）
- **TWSE OpenAPI**：只作驗證工具，不作主來源（僅最新季 ~68 家）
- **DB-first 策略**：台股 API 優先讀 DB，DB miss 才 live fetch，確保使用者看到穩定快取資料

---

## 下次 session 建議起點

1. 確認 `FinancialsSyncTask` 是否已自動執行（查 `SyncState` 表或 Telegram 通知）
2. 若 DB 已有資料 → 驗證 `GET /financials/2330` 日誌確認走 DB 路徑
3. 決定下一個優先項目：FMP 整合 or 美股 DB 同步 or 其他功能
