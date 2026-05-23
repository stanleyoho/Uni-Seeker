# 2026-05-19 DailyTask

## 主任務 (Parent Ticket)

**UNI-PORT-004** — Portfolio Phase 4+ FX support（多幣別 portfolio backend）

## 需求脈絡 (Requirement Context)

### Q1: Why

Portfolio Phase 1-3 假設單一幣別，但實務上使用者會持有 TWD / USD / JPY / HKD 多幣別資產。
要在 summary 層做 cross-currency aggregation，必須先有 FX rate fetch / cache / conversion 基礎建設。

### Q2: Definition of Success

- `GET /holdings/summary?base_currency=TWD` 能跨幣別匯總
- FX rate 從 yfinance 抓 + 落 DB cache（1h TTL）
- Pro tier 才能用 multi-currency summary（Free / Basic 多幣別會回 403）
- Phase 1-5 regression 0 fail，新增 ≥20 tests pass

### Q3: Scope-out

- 不動 Phase 1-3 既存模組（trade_service / dividend_service / position_service core）
- 不新增 yfinance / 任何 dependency
- 不 commit / push（caller 負責）
- 歷史 FX backfill 工具留下一階段

---

## 內部步驟 (Internal WBS)

### Batch A — Survey + 純函式

- **T1** Survey 既有 `journal.fx_rates` 表結構，決定 reuse vs 新表 — 狀態: `todo`
- **T2** `modules/portfolio/fx_converter.py`（pure math） — 狀態: `todo`

### Batch B — IO 模組（依賴 T1 結論）

- **T3** `modules/portfolio/fx_fetcher.py`（yfinance + TTL cache） — 狀態: `todo`
- **T4** `services/portfolio/fx_service.py`（DB cache + fetcher） — 狀態: `todo`

### Batch C — 整合（依賴 T2/T3/T4）

- **T5** Extend `summary_service.py`：multi-currency aggregation — 狀態: `todo`
- **T6** Extend `position_service.py`：returns currency-aware positions — 狀態: `todo`
- **T7** TierFeatures 加 `multi_currency_summary` (Pro) — 狀態: `todo`
- **T8** API `/holdings/summary?base_currency=` 擴充 — 狀態: `todo`
- **T9** API `/holdings/fx/rate` 新端點 — 狀態: `todo`

### Batch D — Test

- **T10** unit: `test_fx_fetcher.py`(7), `test_fx_converter.py`(10) — 狀態: `done`
- **T11** integration: `test_fx_service.py`(6), `test_summary_multi_currency.py`(6) — 狀態: `done`
- **T12** Regression: `pytest -k "portfolio or holdings"` 401/401 pass — 狀態: `done`

## Verify Gate

- [x] 4 個 test 檔，**29 cases** 全 pass
- [x] Phase 1-5 regression 0 fail（401 pass / 0 fail）
- [x] Phase 1-3 modules core 未動（只 extend summary_service / 新增 fx_service / fx_fetcher / fx_converter）

## Decisions

- **T1 結論**：reuse 既有 `journal.fx_rates` 表（id/date/from_currency/to_currency/rate）。schema 完全符合需求，跨 namespace import 符合 §11 anti-coupling（service 讀 ORM model 允許，只禁 service→service 與 domain→ORM）。
- **TTL**：FX 緩存 3600s（1h），比 price feed 的 60s 寬鬆；FX 對 portfolio aggregation 來說變動慢。
- **Tier gate**：放在 service 內，僅當 positions 跨 >1 currency 才觸發 `multi_currency_summary` 檢查；single-currency portfolio 不會誤殺 Free / Basic。
- **Inverse fallback**：fx_fetcher 直接 pair 失敗時自動試反向 pair 取 reciprocal（USD→JPY 失敗 → 試 JPY→USD → 1/rate）。
- **API 設計**：`/summary?base_currency=` 預設 None（回傳 legacy SummaryResponse，向後相容）；帶 query 才走 multi-currency。

## Blockers

(none)

---

## Round 11 — Wash-sale detection (Phase 5)

### 已完成

- **W1** `backend/app/modules/portfolio/wash_sale_detector.py`（pure module，~270 行） — 狀態: `done`
- **W2** `backend/app/modules/portfolio/tax_report.py` 加 `TaxLotMatch.wash_sale_disallowed_loss` 預設 Decimal("0") — 狀態: `done`
- **W3** `backend/app/services/portfolio/tax_report_service.py` 加 `generate_form_8949_with_wash_sales()` + `apply_wash_sales` flag — 狀態: `done`
- **W4** `backend/app/api/v1/holdings/exports.py` 加 `GET /form8949.csv?apply_wash_sales=...` 與 `/schedule_d.csv`（補上 Round 10 缺漏的 route） — 狀態: `done`
- **W5** `backend/tests/unit/modules/portfolio/test_wash_sale_detector.py` — 17 cases pass — 狀態: `done`
- **W6** `backend/tests/integration/test_tax_report_wash_sale_service.py` — 3 cases pass — 狀態: `done`
- **W7** Regression: holdings + portfolio 418 pass / 0 fail — 狀態: `done`

### Decisions

- **30-day window**：calendar days，**inclusive 兩端**（abs delta ≤ 30）。day 30 是 wash sale，day 31 不是。
- **Substantially identical**：簡化為相同 `(symbol, market)`，options/ADR 不處理（IRS 對此本身就模糊）。
- **Replacement FIFO**：多個 loss SELL 競爭同一替代 BUY 時，由 sale_date 早者先取得 quota。
- **Original purchase exclusion**：fixed cost basis 的 BUY（match.acquisition_date 對應的）不能當作 replacement，避免自己配自己。
- **Cost basis inheritance**：本輪只在 SELL row 上 surface disallowed loss（Code=W + Adjustment 欄）；replacement 的 future SELL 走獨立 round 處理（注釋已說明）。
- **Backward compatibility**：`apply_wash_sales` default false，原本 Round 10 的 CSV shape 完全不動。
- **Surprise**：Round 10 已寫 integration tests 但 `TaxReportService` 既沒被 `services.portfolio.__init__` re-export、`form8949.csv` / `schedule_d.csv` route 也沒掛載。Round 11 順手補上，10 個 baseline tests 從 fail → pass。
