# 2026-06-06 DailyTask

## 主任務 (Parent Ticket)

**UNI-B4P-001** — twstock「四大買賣點」(Best Four Buy/Sell Points) feature：在 Uni-Seeker 既有基礎設施上忠實重現 twstock BestFourPoint heuristic（後端 API + 排程全市場掃描 + 前端 TW-only scanner card）。

## 需求脈絡 (Requirement Context)

### Q1: Why
使用者要一個 TW 股票技術訊號掃描器，提供「四大買點 / 四大賣點」每日訊號。twstock 套件本身維護不佳且會自行抓資料（與 app 既有資料不一致），所以決定在 Uni-Seeker 既有 infra（FinMind 資料 + K8 TA-Lib indicators）上重新實作演算法。

### Q2: Definition of Success
- 後端：pure function 計算 8 個點（4 買 4 賣）+ verdict，service 跑全 TW universe 並 persist，排程每日掃描，API 讀 cached 結果，StrictModel response。
- 前端：TW-only scanner card 顯示今日買/賣訊號（symbol / verdict / reasons），STRATOS 風格。
- 全部 local 驗證通過（ruff / mypy / pytest / lint-imports / tsc），PR 5 個 CI check 全綠（但不 merge）。

### Q3: Scope-out
- 不 `pip install twstock`。
- 不做 live per-request 全市場掃描（1500+ symbols）。
- 不做 US 股（TW-only）。
- 不做歷史回測 UI、不做個股詳情頁整合（只做 scanner card）。

## 團隊單 (Team Subtasks)

### #1 [UNI-B4P-001][subtask] Backend pure compute module + tests
- 狀態: `todo`
- DoD:
  - [ ] `app/modules/best_four_point/` pure function over OHLCV series
  - [ ] 8 點 trigger/non-trigger + verdict 全有 unit test

### #2 [UNI-B4P-001][subtask] Service (universe scan + persist) + model + migration
- 狀態: `todo`
- DoD:
  - [ ] service 讀全 TW universe、計算、persist 今日結果
  - [ ] reuse `SignalScanRecord` 或新 model；alembic migration single-head

### #3 [UNI-B4P-001][subtask] Scheduled job + API endpoint
- 狀態: `todo`
- DoD:
  - [ ] auto_scheduler 註冊 job (max_instances=1)
  - [ ] `GET /api/v1/scanner/best-four-point` StrictModel response，讀 cache

### #4 [UNI-B4P-001][subtask] Frontend TW-only scanner card + schema regen
- 狀態: `todo`
- DoD:
  - [ ] card 顯示買/賣訊號，STRATOS 風格，wire 進 research 頁
  - [ ] regenerate schema.d.ts，tsc 通過

### #5 [UNI-B4P-001][subtask] Verify + PR
- 狀態: `todo`
- DoD:
  - [ ] ruff/mypy/pytest/lint-imports/tsc 全通過
  - [ ] self-review 6-dim PASS
  - [ ] PR 開好、5 CI checks 全綠（不 merge）

## 內部步驟 (Internal WBS)

### Batch A — Backend core (sequential, 互相依賴)
- **T1** pure compute module `app/modules/best_four_point/calculator.py` — 狀態: `todo`
- **T2** model（reuse `SignalScanRecord`，scan_date+symbol+signals_json）+ migration — 狀態: `todo`
  - 依賴: 無（可與 T1 並行，但同屬 backend）
- **T3** service `app/services/best_four_point/scan_service.py`（universe scan + persist）— 狀態: `todo`
  - 依賴: T1, T2
- **T4** schema (StrictModel) + API endpoint `app/api/v1` — 狀態: `todo`
  - 依賴: T2, T3
- **T5** scheduled job 註冊 auto_scheduler — 狀態: `todo`
  - 依賴: T3
- **T6** unit + integration tests — 狀態: `todo`
  - 依賴: T1-T5

### Batch B — Frontend (依賴 Batch A 的 API/schema)
- **T7** regenerate schema.d.ts（offline openapi dump）— 狀態: `todo`
  - 依賴: T4
- **T8** TW-only scanner card component + wire into research page — 狀態: `todo`
  - 依賴: T7
- **T9** tsc --noEmit — 狀態: `todo`
  - 依賴: T8

### Batch C — Land
- **T10** self-review + commit + PR + watch CI — 狀態: `todo`
  - 依賴: 全部

## Decisions
- Reuse `SignalScanRecord` (signal_scans table: symbol + scan_date + signals_json JSON) 作為 persistence target — 它的 docstring 正是「snapshot of scan output for a symbol on a given date」，完全符合需求，避免新增冗餘 table。用 `signals_json` 存 best-four-point payload（triggered buy/sell points + verdict + reasons）。
- Pure compute 放 `app.modules.best_four_point`（business core，可 import models 但不可 import api — 符合 import-linter）。
- Service 放 `app.services.best_four_point`（reads DB + persists；service layer）。
- API 放在 scanner namespace：`GET /api/v1/scanner/best-four-point`（task 建議）。
- 排程：reuse 既有 daily 17:30 後的時段，新增獨立 job 17:40（在 daily_sync/institutional 之後，確保價格資料已落地）。

## Blockers
(none)
</content>
</invoke>
