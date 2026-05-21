# YYYY-MM-DD DailyTask

> 模板：複製此檔，更名為 `YYYY-MM-DD-DailyTask.md`，把 `YYYY-MM-DD` 替換為今日日期
> （從 `<env>` 的 `Today's date` 取得；嚴禁從訓練資料推測）。

## 主任務 (Parent Ticket)

**<ticket-id>** — <一句話描述>

## 需求脈絡 (Requirement Context)

> 從 brainstorm 階段的 Q&A 整理。**MUST 寫在這裡，不可只放記憶體**。

### Q1: Why

<為什麼要做這件事>

### Q2: Definition of Success

<怎樣才算成功>

### Q3: Scope-out

<明確不做的項目，避免 scope creep>

## 團隊單 (Team Subtasks)

> 對外溝通用，粗粒度，3-5 張單。每張需有 DoD（Definition of Done）。

### #1 [<ticket-id>][subtask] <title>

- 狀態: `todo`
- DoD:
  - [ ] ...

## 內部步驟 (Internal WBS)

> 自己執行用，細粒度。每步驟標記 batch（A/B/C...）與依賴關係。
> Batch 內的步驟可平行；跨 batch 為順序依賴。

### Batch A — <description>

- **T1.1** <description> — 狀態: `todo`
  - 依賴: <prerequisites>
  - 產出: <deliverable>

## Layer Mapping (Team subtask ↔ Internal steps)

| 團隊單 | 內部步驟 |
|--------|----------|
| #1 ... | T1.1, T1.2, ... |

## Three Sync Points (適用 `cross-project-migration` skill 任務時)

- **Kickoff**: Q1-Q3 答完
- **CP1 (Plan Confirm)**: Plan 寫完，等使用者 confirm 才能往下
- **Closing**: AC report sign-off

## 已完成 (Completed)

> 完成的任務移到這裡保留紀錄，**不可刪除**。

(none)

## Blockers

> 卡住的事項，註明等什麼。

(none)

## Decisions

> 重要架構/設計決定，寫下原因。

(none)

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
