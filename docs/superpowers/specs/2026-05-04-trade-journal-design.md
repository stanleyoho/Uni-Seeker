# Trade Journal 功能設計規格

**日期：** 2026-05-04  
**狀態：** 已核准，待實作  
**範疇：** 全新 `/journal` 模組，不影響現有頁面

---

## 1. 功能概述

為 Uni-Seeker 新增真實交易記錄模組，讓使用者可以：

- 記錄多個券商帳戶的買賣交易
- 用 FIFO 法精確計算未實現 & 已實現損益
- 設定每個帳戶 / 策略群組的目標持股比例，超出閾值自動警示
- 以日 / 週 / 月 / 年增幅圖表追蹤整體資產表現
- 支援台股、美股、加密貨幣三個市場，統一折算台幣總覽

---

## 2. 決策記錄

| 問題 | 決定 | 理由 |
|------|------|------|
| 放在哪裡 | `/journal` 獨立頂層頁面 | 不污染現有 Portfolio，功能完整獨立 |
| 交易輸入 | Phase 1 純手動，預留 CSV / API 擴充點 | 先跑通核心流程 |
| 支援市場 | 台股（上市上櫃）、美股、加密貨幣 | 使用者實際交易的市場 |
| 幣別 | 各資產顯示原幣 + 總覽折算 TWD | 兩者都要 |
| 帳戶架構 | 帳戶 + 投資組合群組，兩層獨立 | 最靈活，一帳戶可加入多群組 |
| 再平衡層級 | 群組層（帳戶間資金比例）+ 帳戶層（持股比例）都設定 | 雙層監控 |
| 後端架構 | Hybrid：trades 作真相 + positions 快取 + 日快照 | FIFO 精確 + 查詢快 + 圖表完整 |

---

## 3. 資料庫 Schema

### 3.1 核心表（8 張）

#### `trade_accounts` — 真實券商帳戶
```sql
id          SERIAL PRIMARY KEY
name        VARCHAR(100) NOT NULL
broker      VARCHAR(50)             -- 元大/永豐/IB/Binance/自定
market      VARCHAR(10) NOT NULL    -- TW / US / CRYPTO
currency    VARCHAR(10) NOT NULL    -- TWD / USD / USDT / BTC
description TEXT
created_at  TIMESTAMP DEFAULT now()
```

#### `account_groups` — 策略群組
```sql
id            SERIAL PRIMARY KEY
name          VARCHAR(100) NOT NULL
description   TEXT
base_currency VARCHAR(10) DEFAULT 'TWD'  -- 群組折算基準幣
created_at    TIMESTAMP DEFAULT now()
```

#### `account_group_members` — 帳戶 ↔ 群組（M2M）
```sql
id            SERIAL PRIMARY KEY
group_id      INTEGER REFERENCES account_groups(id) ON DELETE CASCADE
account_id    INTEGER REFERENCES trade_accounts(id) ON DELETE CASCADE
target_weight NUMERIC(6,4)            -- 0.60 = 此帳戶應佔群組 60%
UNIQUE (group_id, account_id)
```

#### `trades` — 交易記錄（唯一真相，永遠不刪改）
```sql
id            SERIAL PRIMARY KEY
account_id    INTEGER REFERENCES trade_accounts(id) NOT NULL
symbol        VARCHAR(20) NOT NULL    -- "2330.TW" / "AAPL" / "BTC"
market        VARCHAR(10) NOT NULL    -- TW / US / CRYPTO
action        VARCHAR(10) NOT NULL    -- BUY / SELL / DIVIDEND / SPLIT
date          DATE NOT NULL
price         NUMERIC(24,8)           -- 原幣成交價
quantity      NUMERIC(24,8)           -- 股數 / 幣量（加密支援 8 位小數）
fee           NUMERIC(24,8) DEFAULT 0 -- 手續費（原幣）
tax           NUMERIC(24,8) DEFAULT 0 -- 證交稅（原幣，賣出才有）
trade_fx_rate NUMERIC(12,6)           -- 交易當日 原幣→TWD 匯率（USD/USDT 帳戶）
tags          JSONB DEFAULT '[]'      -- ["momentum", "earnings-play"]
note          TEXT
created_at    TIMESTAMP DEFAULT now()

INDEX (account_id, symbol, market, date)
```

#### `trade_lots` — FIFO 批次追蹤（由 trades 衍生，BUY 時建立）
```sql
id               SERIAL PRIMARY KEY
trade_id         INTEGER REFERENCES trades(id) NOT NULL  -- 對應的 BUY trade
account_id       INTEGER REFERENCES trade_accounts(id) NOT NULL
symbol           VARCHAR(20) NOT NULL
market           VARCHAR(10) NOT NULL
original_qty     NUMERIC(24,8) NOT NULL   -- 原始買入數量
remaining_qty    NUMERIC(24,8) NOT NULL   -- 尚未被 SELL 消耗的數量
cost_per_unit    NUMERIC(24,8) NOT NULL   -- 每股/每單位成本（含手續費均攤）
is_exhausted     BOOLEAN DEFAULT FALSE

INDEX (account_id, symbol, market, is_exhausted, trade_id)  -- FIFO 查詢專用
```

#### `positions` — 持倉快取（從 trades + trade_lots 計算，非真相）
```sql
id             SERIAL PRIMARY KEY
account_id     INTEGER REFERENCES trade_accounts(id) NOT NULL
symbol         VARCHAR(20) NOT NULL
market         VARCHAR(10) NOT NULL
currency       VARCHAR(10) NOT NULL           -- 冗餘，來自 trade_accounts
quantity       NUMERIC(24,8) NOT NULL DEFAULT 0
avg_cost_fifo  NUMERIC(24,8)                 -- 剩餘持倉的 FIFO 加權均價
total_cost     NUMERIC(24,8)                 -- 剩餘持倉總成本
realized_pnl   NUMERIC(24,8) DEFAULT 0       -- 累計已實現損益（原幣）
is_closed      BOOLEAN DEFAULT FALSE          -- quantity = 0 時設為 True
last_updated   TIMESTAMP DEFAULT now()

UNIQUE (account_id, symbol, market)
```

#### `portfolio_snapshots` — 日快照（供圖表）
```sql
id              SERIAL PRIMARY KEY
account_id      INTEGER REFERENCES trade_accounts(id)   -- 擇一非 NULL
group_id        INTEGER REFERENCES account_groups(id)   -- 擇一非 NULL
date            DATE NOT NULL
total_value     NUMERIC(24,8)     -- 市值（原幣 for account / TWD for group）
total_cost      NUMERIC(24,8)     -- 成本基礎
unrealized_pnl  NUMERIC(24,8)
realized_pnl    NUMERIC(24,8)
twd_value       NUMERIC(24,8)     -- 折算台幣市值

CHECK (
  (account_id IS NOT NULL AND group_id IS NULL) OR
  (account_id IS NULL AND group_id IS NOT NULL)
)
-- PostgreSQL 中 NULL != NULL，不能用普通 UNIQUE，改用 partial index：
CREATE UNIQUE INDEX uq_account_snapshot ON portfolio_snapshots(account_id, date) WHERE account_id IS NOT NULL;
CREATE UNIQUE INDEX uq_group_snapshot   ON portfolio_snapshots(group_id, date)   WHERE group_id IS NOT NULL;
```

#### `allocation_rules` — 再平衡配置規則
```sql
id               SERIAL PRIMARY KEY
account_id       INTEGER REFERENCES trade_accounts(id)   -- 帳戶層規則（標的配置）
group_id         INTEGER REFERENCES account_groups(id)   -- 群組層規則（合併標的配置）
symbol           VARCHAR(20) NOT NULL  -- 目標標的，如 "2330.TW"
                                       -- 群組層「帳戶間資金比例」由 account_group_members.target_weight 管理，不在此表
target_weight    NUMERIC(6,4) NOT NULL   -- 0.20 = 目標 20%
lower_threshold  NUMERIC(6,4) DEFAULT 0.03   -- 低於目標 3% 觸發
upper_threshold  NUMERIC(6,4) DEFAULT 0.03   -- 高於目標 3% 觸發
is_active        BOOLEAN DEFAULT TRUE

CHECK (
  (account_id IS NOT NULL AND group_id IS NULL) OR
  (account_id IS NULL AND group_id IS NOT NULL)
)
UNIQUE (account_id, symbol) WHERE account_id IS NOT NULL
UNIQUE (group_id, symbol)   WHERE group_id IS NOT NULL
```

#### `fx_rates` — 匯率快取
```sql
id            SERIAL PRIMARY KEY
date          DATE NOT NULL
from_currency VARCHAR(10) NOT NULL
to_currency   VARCHAR(10) NOT NULL DEFAULT 'TWD'
rate          NUMERIC(12,6) NOT NULL

UNIQUE (date, from_currency, to_currency)
```

### 3.2 Schema 修正清單（審查後納入）

| # | 問題 | 修正方式 |
|---|------|---------|
| 1 | FIFO 全掃描效能 | 新增 `trade_lots` 表，只讀 `is_exhausted=False` 的批次 |
| 2 | 缺少複合索引 | trades、positions、snapshots、fx_rates 各加複合 index |
| 3 | FX rate 今日缺失 | 查詢時 fallback 最近 N 天最新一筆 |
| 4 | 賣超持倉 | SELL 寫入前驗證 quantity ≤ sum(remaining_qty) |
| 5 | 股票分割 | SPLIT action 批量更新對應帳戶+標的所有 lots |
| 6 | 加密精度 | quantity / price 全用 `NUMERIC(24,8)` |
| 7 | 跨市場代碼碰撞 | positions UNIQUE key 含 market |
| 8 | 已賣清持倉 | `is_closed` flag，活躍視圖 WHERE is_closed=False |
| 9 | polymorphic 反模式 | snapshots / allocation_rules 改雙 FK + CHECK |
| 10 | 歷史損益匯率不準 | trades 加 `trade_fx_rate`（交易當日匯率） |
| 11 | 擴展：交易標籤 | trades 加 `tags JSONB` |

---

## 4. 後端架構

### 4.1 FIFO 引擎（獨立模組，優先實作並測試）

```
backend/app/modules/trade_journal/
├── fifo_engine.py      # FIFO 計算，純函數，無 DB 依賴
├── position_sync.py    # 將 FIFO 結果寫入 positions 快取
├── snapshot_job.py     # 日快照 cron job
├── rebalance.py        # 再平衡警示計算
└── fx_service.py       # 匯率查詢 + fallback 邏輯
```

**FIFO 流程：**
1. `BUY` → 建立 `trade_lots` record，更新 `positions`（qty↑, cost↑）
2. `SELL` → 驗證 qty 足夠 → 消耗最舊 lots（FIFO）→ 計算 realized_pnl → 更新 `positions`（qty↓, realized_pnl↑）
3. `SPLIT` → 更新同帳戶+標的所有 lots：`remaining_qty *= ratio`, `cost_per_unit /= ratio`
4. `DIVIDEND` → 建立現金收入記錄，不動持倉

**positions 重算幂等：** 可從 trades 完整重建 trade_lots 和 positions（用於資料修復）

### 4.2 API Routes（新增於 `/api/v1/journal/`）

```
POST   /journal/accounts              建立帳戶
GET    /journal/accounts              列出帳戶
GET    /journal/accounts/{id}         帳戶詳情（含持倉）
POST   /journal/accounts/{id}/trades  新增交易
GET    /journal/accounts/{id}/trades  交易記錄（分頁）

POST   /journal/groups                建立群組
GET    /journal/groups/{id}           群組詳情（合併持倉 + 配置）

GET    /journal/accounts/{id}/performance  帳戶績效（D/W/M/Y 增幅）
GET    /journal/groups/{id}/performance    群組績效

GET    /journal/alerts                所有觸發中的再平衡警示

POST   /journal/accounts/{id}/allocation  設定帳戶層配置規則
POST   /journal/groups/{id}/allocation    設定群組層配置規則
```

---

## 5. 前端頁面

### 5.1 頁面結構

```
/journal                          總覽 Dashboard
/journal/accounts                 帳戶列表
/journal/accounts/[id]            帳戶詳情（tab：持倉 / 配置 / 績效）
/journal/accounts/[id]/trades     交易記錄 + 新增
/journal/groups                   群組列表
/journal/groups/[id]              群組詳情（合併視圖 + 再平衡）
```

主導覽列新增「交易日誌」入口，與 Portfolio、Research 並列。

### 5.2 各頁面內容

**`/journal` Dashboard：**
- KPI 列（5 格）：總市值(TWD) / 未實現損益 / 已實現損益 / 週增幅 / 年增幅
- 資產曲線（AreaChart，切換 日/週/月/年）
- 再平衡警示列：紅=超標、黃=低標，標明偏差幅度
- 帳戶卡片：各帳戶市值 + 今日損益，點擊進入詳情

**`/journal/accounts/[id]` 持倉 Tab：**
- 帳戶 KPI：市值 / 未實現 / 已實現
- 持倉表格欄位：標的 / 數量 / FIFO均價 / 現價 / 未實現損益 / 當前佔比 vs 目標佔比
- 超標的佔比欄位以紅字顯示
- 已出清持倉（is_closed=True）摺疊顯示
- 右上角「+ 新增交易」按鈕

**新增交易 Modal（任何頁面都可觸發）：**
- 頂部切換：BUY / SELL / DIVIDEND / SPLIT
- 欄位：帳戶選擇 / 標的代碼+市場 / 日期 / 價格 / 數量 / 手續費 / 稅 / 備註+標籤
- 即時預覽：總成本、新批 FIFO 均價
- SELL 時顯示預估已實現損益

**`/journal/groups/[id]`：**
- 合併持倉：所有帳戶持倉加總，折算 TWD 顯示
- 群組層配置：各帳戶當前佔比 vs 目標，圖形化顯示
- 再平衡建議文字：「元大帳戶超配 +8%，建議減少 約 X 萬元」

### 5.3 設計規範

- 遵循現有 STRATOS 暗黑奢華風格：GlassPanel、ClippedButton、AmbientBackground
- 利潤用 `var(--stock-up)`（綠），虧損用 `var(--stock-down)`（紅）
- 所有數字欄位用 `tabular-nums`，金額用千分位格式
- 圖表沿用現有 recharts AreaChart 元件

---

## 6. 測試規格（40 個情境）

### Group 1：FIFO 賣出核心（9 tests）

| ID | 情境 | 輸入 | 預期 |
|----|------|------|------|
| T01 | 單 lot 完全賣出 | BUY 100@100 → SELL 100@150 | realized=+5000, lot=0 |
| T02 | 單 lot 部分賣出 | BUY 100@100 → SELL 40@150 | realized=+2000, lot=60@100 |
| T03 | 跨兩批 FIFO 賣出 | BUY 100@100, BUY 50@120 → SELL 120@150 | realized=+5600, Lot B 剩 30@120 |
| T04 | 恰好耗盡第一批 | BUY 100@100, BUY 50@120 → SELL 100@150 | Lot A=0，Lot B 完整 50@120 |
| T05 | 賠錢賣出 | BUY 100@100 → SELL 100@80 | realized=-2000 |
| T06 | 賣超持倉（應拒絕）| BUY 50@100 → SELL 100@150 | ValidationError: insufficient shares |
| T07 | 無持倉直接賣（應拒絕）| SELL 100@150（無 BUY）| ValidationError: no open position |
| T08 | 手續費+稅納入成本 | BUY 100@100 fee=100 → SELL 100@100 fee=100 tax=300 | realized=-500 |
| T09 | 多次買入多次賣出 | BUY×3 不同價，SELL×2 分批 | 每次 realized 對應正確 lot，總計一致 |

### Group 2：股票分割 / 除權息（5 tests）

| ID | 情境 | 輸入 | 預期 |
|----|------|------|------|
| T10 | 2:1 順分割 | BUY 100@100 → SPLIT 2:1 | lot: 200股, cost_per_unit=50 |
| T11 | 分割後賣出成本正確 | BUY 100@100 → SPLIT 2:1 → SELL 200@70 | realized=+4000 |
| T12 | 反向分割 1:10 | BUY 100@10 → SPLIT 1:10 | lot: 10股, cost_per_unit=100 |
| T13 | 多批 lot 同時分割 | BUY 100@100, BUY 50@120 → SPLIT 2:1 | 200@50 + 100@60 |
| T14 | 股息不影響持倉 | BUY 100@100 → DIVIDEND TWD 500 | lot 不變，現金收入+500 獨立記錄 |

### Group 3：持倉快取一致性（6 tests）

| ID | 情境 | 輸入 | 預期 |
|----|------|------|------|
| T15 | BUY 後 position 建立 | BUY 100@100 | positions: qty=100, cost=10000 |
| T16 | SELL 後 position 更新 | BUY 100@100 → SELL 40@150 | qty=60, realized=+2000 |
| T17 | 完全出清後 is_closed | BUY 100@100 → SELL 100@150 | is_closed=True, realized=+5000 |
| T18 | 未實現損益計算 | BUY 100@100，當前市價=130 | unrealized=+3000 |
| T19 | positions 重算幂等 | 從 trades 重新計算 positions | 結果與原 positions 完全一致 |
| T20 | 跨市場不混淆 | symbol=2330 market=TW 和 market=US | 兩個獨立 position 記錄 |

### Group 4：再平衡警示（8 tests）

| ID | 情境 | 輸入 | 預期 |
|----|------|------|------|
| T21 | 帳戶層：標的在範圍內 | target=20% ±3%，當前=21% | no alert |
| T22 | 帳戶層：超過上限 | target=20% +3%，當前=24.5% | ALERT 超標 +4.5% |
| T23 | 帳戶層：低於下限 | target=20% -3%，當前=15% | ALERT 低標 -5% |
| T24 | 群組層：帳戶比重正常 | 元大 target=60% ±5%，當前=62% | no alert |
| T25 | 群組層：帳戶比重超標 | 元大 target=60% +5%，當前=67% | ALERT 群組層 |
| T26 | 總值為零不崩潰 | 帳戶無持倉，total_value=0 | return 0%，no ZeroDivisionError |
| T27 | 未設 rule 的標的不觸發 | 持有 2330 但無 allocation_rule | no alert |
| T28 | is_active=False 不觸發 | rule 存在但 is_active=False | no alert |

### Group 5：多幣別 / FX / 日快照（12 tests）

| ID | 情境 | 輸入 | 預期 |
|----|------|------|------|
| T29 | TWD 帳戶不查匯率 | 台股帳戶，realized=5000 TWD | twd_value=5000 |
| T30 | USD 交易當日換算 | realized=100 USD，trade_fx_rate=31.5 | twd_realized=3150 |
| T31 | 未實現損益用今日匯率 | unrealized=200 USD，今日匯率=32.0 | twd_unrealized=6400 |
| T32 | 今日匯率缺失 fallback | fx_rates 無今日，有昨日=31.8 | 用 31.8，不報錯 |
| T33 | 完全無匯率資料 | fx_rates 表空 | FXRateNotFound（可處理） |
| T34 | 加密精度不損失 | BUY 0.00000001 BTC @94000 | cost=0.00094，無浮點誤差 |
| T35 | 日快照單帳戶 | 持倉 100×130，快照日期=今日 | total_value=13000 |
| T36 | 群組快照折TWD | 元大=1M TWD，IB=30K USD×32 | group twd_value=1,960,000 |
| T37 | 日增幅計算 | 昨日=100,000，今日=101,500 | daily_return=+1.5% |
| T38 | 週增幅計算 | 7天前=95,000，今日=101,500 | weekly_return=+6.84% |
| T39 | 快照缺失時跳過 | 30天前無快照，找最近一筆 | 用最近有快照日期計算 |
| T40 | 快照 upsert 幂等 | 重新跑 cron 覆寫同日快照 | 不重複建立 |

**覆蓋率目標：** FIFO 引擎核心 100%，API 層 80%+

---

## 7. 實作分期

### Phase 0 — FIFO 引擎 Spike（優先驗證）
在正式建 DB 前：
1. 建 `trades` + `trade_lots` 兩張表
2. 實作 `fifo_engine.py`
3. 跑 T01–T09 全部通過後再展開其他 Phase

### Phase 1 — 後端完整 Schema + API
- 建齊 8 張表 + migration
- `/journal/accounts` CRUD
- 交易記錄 API + FIFO 計算
- Positions 快取同步

### Phase 2 — 前端核心頁面
- `/journal` Dashboard + 帳戶詳情
- 新增交易 Modal
- 持倉表格 + 損益顯示

### Phase 3 — 群組 + 再平衡
- Account Groups CRUD
- 再平衡警示計算
- 群組詳情頁

### Phase 4 — 圖表 + 快照
- 日快照 cron job
- 日 / 週 / 月 / 年增幅圖表
- 群組績效曲線

### Phase 5 — 擴充預留（未來）
- CSV 匯入（元大、永豐、IB 格式）
- 券商 API 自動同步
- 稅務報告匯出

---

## 8. 擴充預留點

| 點 | 預留方式 |
|----|---------|
| CSV 匯入 | `trades` 加 `import_source` 欄位（null=手動） |
| 多用戶 | `trade_accounts` / `account_groups` 加 `user_id FK`（現在單人不加） |
| 更多幣別 | `fx_rates` 表設計無硬編碼，任意幣別對 TWD 均可 |
| 稅務申報 | `trade_lots` 保存完整批次，可依需求重算任意期間損益 |
| 加密網路手續費 | `trades.fee` 支援小數，`market=CRYPTO` 時可記錄 gas fee |
