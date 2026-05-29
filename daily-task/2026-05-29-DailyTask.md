# 2026-05-29 DailyTask

## 主任務 (Parent Ticket)

**feat/institutional-browseable** — `/institutional` 頁面要 list 可訂閱機構並支援搜尋，取代「empty state → 點按鈕開 modal」的隱晦動線。

## 需求脈絡 (Requirement Context)

### Q1: Why

使用者進到 `/institutional`，預設只看到一個 `+ 訂閱機構/基金` 的空狀態 + CTA。他不知道按下去會看到什麼、也不知道可訂閱的機構長相，無法瀏覽與探索。原話：「訂閱機構應該要有 list 出來 並且可以搜尋」。

### Q2: Definition of Success

- 預設視窗看得到「搜尋框 + filer list」，不必再點開 modal 才看得到資料。
- 搜尋框 ≥2 字元觸發 SEC EDGAR + 本地 DB 混合搜尋（既有 `POST /institutional/filers/search`）。
- 每筆 row 顯示 name + CIK + 訂閱狀態（已訂閱／未訂閱可一鍵訂閱）。
- 空查詢時不撒網 backend（會 422），改 fallback 三筆 curated（Berkshire / Bridgewater / ARK）以給 first-time user 立刻可點的入口。
- TypeScript、ESLint、Vitest 全綠；瀏覽器實機驗證 + 截圖。

### Q3: Scope-out

- 不動 backend（搜尋／list endpoint 已存在）。
- 不改 `frontend/src/app/page.tsx`、`globals.css`、home 元件。
- 不重構共用 quote-row 元件（γ agent 範圍）。
- 不重做 `批次訂閱` tab；保留現狀。
- 不引入新分頁、虛擬化套件（list 量級 20 ≦ limit 50；簡單 scroll 即可）。

## 團隊單 (Team Subtasks)

### #1 [feat/institutional-browseable][subtask] FilerBrowser 元件

- 狀態: `todo`
- DoD:
  - [ ] 預設無 query → 顯示 3 筆 curated（Berkshire / Bridgewater / ARK），可一鍵訂閱
  - [ ] 輸入 ≥2 字 → 顯示混合搜尋結果，每 row 顯示 name + CIK + 已/未訂閱 chip
  - [ ] 訂閱錯誤 (403 / 409 / 502) 顯示 zh-TW 對應訊息

### #2 [feat/institutional-browseable][subtask] /institutional 預設視窗整合

- 狀態: `todo`
- DoD:
  - [ ] `filers.length === 0` 時 FilerBrowser inline 取代 empty state
  - [ ] `批次訂閱` / `+ 訂閱機構/基金` modal entry 仍保留可用
  - [ ] 已訂閱使用者進來，視窗 = 既有 FilerListResponsive（不退化）

### #3 [feat/institutional-browseable][subtask] 驗證 + 截圖 + PR

- 狀態: `todo`
- DoD:
  - [ ] `npx tsc --noEmit` clean
  - [ ] `npm run lint` clean
  - [ ] `npx vitest run` no regression
  - [ ] /institutional 截圖至 `/Users/stanley/stanley-project/warroom/data/screenshot-institutional-after.png`
  - [ ] PR 開出，body 附 before/after 截圖路徑 + endpoints + fallback 說明

## 內部步驟 (Internal WBS)

### Batch A — 同檔域 sequential（同一頁面/元件鏈，無法平行）

- **T1.1** 新增 `frontend/src/components/institutional/filer-browser.tsx` — 狀態: `todo`
  - 依賴: 無
  - 產出: FilerBrowser export + filer-browser row 子元件
- **T1.2** 在 `components/institutional/index.ts` export FilerBrowser — 狀態: `todo`
  - 依賴: T1.1
- **T1.3** 修改 `app/institutional/page.tsx`: empty-list 時 render FilerBrowser — 狀態: `todo`
  - 依賴: T1.2

### Batch B — 驗證（必須在 Batch A 完成後）

- **T2.1** `cd frontend && npx tsc --noEmit` — 狀態: `todo`
- **T2.2** `cd frontend && npm run lint` — 狀態: `todo`
- **T2.3** `cd frontend && npx vitest run` — 狀態: `todo`
- **T2.4** restart uni-seeker-frontend + screenshot — 狀態: `todo`

### Batch C — Self-review + commit + PR

- **T3.1** `self-review` skill 6 維度 — 狀態: `todo`
- **T3.2** commit + push + gh pr create — 狀態: `todo`

## Layer Mapping

| 團隊單 | 內部步驟 |
|--------|----------|
| #1 FilerBrowser 元件 | T1.1, T1.2 |
| #2 整合 | T1.3 |
| #3 驗證 + PR | T2.1–T2.4, T3.1, T3.2 |

## 已完成 (Completed)

(none)

## Blockers

(none)

## Decisions

- **curated CIK fallback**: backend `searchFilers("")` 422，所以無法用空查詢拉「Top 50 by AUM」。改 hard-code 3 個經典 13F filers (Berkshire 0001067983, Bridgewater 0001350694, ARK 0001697748) 作 first-paint 可訂閱入口；後續 backend 若加 `q="*"` 支援可再升級。
- **不改 modal**: `批次訂閱` 與 `+ 訂閱機構/基金` 維持 modal 入口，避免改動既有 quick-action 行為；只在「空清單」這個 dead-end 場景補 inline 探索。
- **沒加虛擬化**: 搜尋 backend `limit=50`，curated 只有 3 筆，純 scroll 足夠。
