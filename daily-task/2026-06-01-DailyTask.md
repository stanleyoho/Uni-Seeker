# 2026-06-01 DailyTask

## 主任務 (Parent Ticket)

**feat/tw-institutional-flow-and-signal-board** — 為 day-trader 加上「TW 三大法人」+「盤前訊號」首頁區塊與後端 endpoint。

## 需求脈絡 (Requirement Context)

### Q1: Why
- 13F 是美股季度延遲 45 天資料，對台股 day-trader 零價值。
- Day-trader 真正需要的是台股三大法人 (外資/投信/自營) 盤後 17:00 公布的買賣超。
- 同時，早晨 8:30 打開 app 應該立刻看到昨晚 batch 跑出來的訊號 (黃金交叉 / 量價突破 / RSI 反彈)。

### Q2: Definition of Success
1. 後端有 `GET /api/v1/tw-institutional/top-net` 與 `GET /api/v1/tw-institutional/symbol/{symbol}` 兩個 endpoint，DB 無資料時不 500。
2. 後端有 `GET /api/v1/signals/recent` 回傳近 N 小時的訊號列表 + group counts。
3. 首頁 KPI row 下方多出一條「昨日 / 盤前訊號」+ 一條「三大法人」mini-tile row，可點擊。
4. `auto_scheduler.py` 增加 17:30 後的 institutional 同步 (任務已在 sync chain，需確保保留)。
5. backend pytest 在新模組 clean、frontend tsc/lint clean、首頁截圖落地 warroom data。

### Q3: Scope-out
- 不動 `frontend/src/app/institutional/**` (那是 13F surface)。
- 不動其他 agent 領地：K1 routes、K2 schemas、K7 RSC migration、K8 indicators、scanner 內部、per-stock dashboard。
- TW institutional 不做歷史 backfill UI，只做 top-net + per-symbol 兩支查詢。
- signal_fires 表只做最小欄位，不做事件溯源。

## 團隊單 (Team Subtasks)

### #A1 [tw-institutional] Backend endpoint + sync
- 狀態: `todo`
- DoD:
  - [ ] `TwInstitutionalNet` model + alembic migration (idempotent)
  - [ ] Sync task `tw_institutional` 接入 scheduler，17:30 daily 跑
  - [ ] `GET /tw-institutional/top-net` + `GET /tw-institutional/symbol/{symbol}` 回傳合法 shape
  - [ ] Pytest 覆蓋 happy path + empty DB

### #A2 [signal-board] Backend recent signals endpoint
- 狀態: `todo`
- DoD:
  - [ ] `SignalFire` model (或重用 `SignalScanRecord`) — 預設 reuse
  - [ ] `GET /signals/recent?lookback_hours=20&top=10` 回傳 signals[] + grouped counts
  - [ ] scanner 寫入 signal_scans 時補上 BUY signals 為 signal_fires (走 reuse 路徑)
  - [ ] Pytest 覆蓋 lookback / grouped counts

### #A3 [home] Frontend home segment
- 狀態: `todo`
- DoD:
  - [ ] `<PreMarketSignalRow />` 3 mini-tiles + click → /research?template=...
  - [ ] `<TwInstitutionalRow />` 3 mini-tiles + click → /tw-institutional?kind=...
  - [ ] 接 hooks 兩支新 endpoint
  - [ ] tsc / lint clean
  - [ ] 首頁截圖落 `/Users/stanley/stanley-project/warroom/data/screenshot-home-with-signals-and-flow.png`

## 內部步驟 (Internal WBS)

### Batch A — Backend foundation (parallel: A1.x with A2.x — no overlap)

- **A1.1** Create `TwInstitutionalNet` model + alembic migration (revises `UNI_SYNC_002`)
- **A1.2** Create `TwInstitutionalSyncTask` (reuses FinMindInstitutionalProvider)
- **A1.3** Register task in `SyncScheduler._tasks` + `_TASK_ORDER`
- **A1.4** Create `GET /tw-institutional/top-net` + `/symbol/{symbol}` router; mount in `v1_router`
- **A1.5** Pytest: model insert + endpoint happy/empty paths

- **A2.1** Add `SignalFire` ORM (or persist via SignalScanRecord — pick reuse)
- **A2.2** `GET /signals/recent` reads SignalScanRecord rows within lookback
- **A2.3** Pytest: lookback / grouped counts

### Batch B — Frontend (depends on Batch A endpoints existing)

- **B.1** Add `fetchTwInstitutionalTopNet`, `fetchRecentSignals` to api-client.ts (type-only against new endpoints)
- **B.2** Add `useTwInstitutionalTopNet`, `useRecentSignals` hooks
- **B.3** Add `<PreMarketSignalRow />` + `<TwInstitutionalRow />` to home page between KPI row and HotSectorsRow
- **B.4** tsc / lint check

### Batch C — Verify + ship

- **C.1** Restart backend + frontend via warroom
- **C.2** Curl smoke both endpoints
- **C.3** Screenshot home page → warroom/data
- **C.4** Self-review gate → commit → push → PR

## Layer Mapping

| 團隊單 | 內部步驟 |
|--------|----------|
| #A1 | A1.1 - A1.5 |
| #A2 | A2.1 - A2.3 |
| #A3 | B.1 - B.4 |

## Decisions

- Reuse existing `SignalScanRecord` model rather than create new `signal_fires` — already has `(symbol, scan_date, signals_json)` shape, fits requirement.
- TW institutional uses ints (matches FinMind data scale) but model uses BigInteger to handle 外資 single-day net of >10 億.
- Endpoint prefix `/tw-institutional` (not `/institutional`) — avoid colliding with `/institutional/{symbol}` legacy catch-all and the 13F namespace.

## 已完成 (Completed)

(none)
