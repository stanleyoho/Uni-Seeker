# Portfolio Tracker — Architecture & Design (Uni-Seeker)

**日期：** 2026-05-20
**作者：** System Architect (architecture rewrite)
**範疇：** 「股票紀錄對賬」backend + frontend 架構設計；spec only，不生成 `.py` / migration / yaml

---

## 1. Status

2026-05-20 architecture rewrite（取代當日稍早 inherit-and-extend 立場的 494 行 draft）。

**已敲定的設計決策（不重新討論）：**

| 決策 | 內容 | 來源 |
|------|------|------|
| Q1 | trades-based（每筆買賣記一筆，positions 為 derived view） | Stanley 確認 |
| Q2 | MVP 支援 **TW + US** 兩個市場；CRYPTO 排 Phase 4+ | Stanley 確認 |
| Q3 | **separate schema**（新 namespace `portfolio_*`，既有 `trade_journal/` schema 完全不動） | Stanley 確認；理由詳見 §2 |
| Q4 | Tier guard via YAML + Pydantic（`config/tier_limits.yaml` + `app/billing/tier_limits.py`，`@lru_cache` in-memory，strong-typed） | Stanley 確認 |
| Q6 | 簡單算法：資產增益 = `Σ(qty × last_price) − Σ(qty × avg_cost)`，只算當下持股，已賣出不累計 | Stanley 確認 |

**Pre-reading 重大發現（影響後續設計）：**

1. **`/api/v1/portfolio/` prefix 已被 portfolio backtest 佔用**（`backend/app/api/v1/portfolio.py:28`）→ 新 module 必須換 prefix，建議 `/api/v1/holdings/`（見 §5.4）
2. **`app/middleware/tier_guard.py::require_tier(min_tier)` 已存在**（`UserTier` ordering FREE<BASIC<PRO，含 `settings.enable_monetization` toggle 與 Prometheus 觀測）→ 本 spec 的 `tier_limits.yaml` 是補「**數量上限**」（accounts/trades/symbols 上限），與既有「tier 門檻」正交，**不是 reinvent**
3. **既有 `/api/v1/journal/*` 全部 unauthenticated**（`app/api/v1/journal.py` line 51-89 沒有任何 `require_auth`），開發資料 5 row → 處置策略列入 Q (見 §14)
4. **`fifo_engine.py:1` 第一行明文寫「Pure FIFO engine — no database, no side effects」**→ 跨 schema 直接 `import` 零成本
5. **US 股 daily close 已可寫入 `stock_prices`** — `app/modules/price_updater/yfinance_provider.py` 已實作 + 已被 `app/api/v1/prices.py::backfill_*` 端點使用，但 yfinance 為 backfill 用途，**live price 仍需新增 fetcher**
6. **`UNI-PORT-001` migration ID 未被佔用**（既有 `UNI-BILL-001/002`、`UNI-COMP-001`、`UNI-WATCH-001`）

---

## 2. Why "Separate Schema" Is the Right Call

Q3 在 brainstorm 階段已敲定 separate schema。本節補齊 **6 個架構層面的證據**，每點 cite 既有檔案。

### 2.1 語意分離（Bounded Context）

- **`trade_journal`** 的語意是 **「交易筆記」**：immutable event log + FIFO lot 重建 + 群組 / 再平衡 / 日快照（見 `app/models/journal.py:33-44 AccountGroup`、`:88-110 TradeLot`、`:135-159 PortfolioSnapshot`）
- **`portfolio_tracker`** 的語意是 **「對賬持倉」**：使用者面向的 KPI / 損益 / 單日漲跌 / 資產增益
- 同樣的 `trades` 表硬塞兩種語意 → DDD 反 pattern；命名衝突、index 衝突、生命週期衝突會在 Phase 4 後集中爆發

### 2.2 權限模型不同

- 既有 `app/api/v1/journal.py` 整批 routes **完全沒掛 `require_auth`**（line 51, 66, 72, 93, 137, 167, 206, 212, 268, 315 全部裸用 `DbDep`）
- 新 module 必須**第一天就強制 user-scoped**（`Depends(require_auth)` + `account.user_id == current_user.id` 校驗）
- 在既有 `trades` 表加 `user_id` → 必須 backfill 既有 5 row dev data；新 schema → zero migration risk

### 2.3 生命週期不同

- 既有 `journal/*` 已有 40 個 integration test（`tests/integration/test_journal_api.py` + `tests/unit/test_fifo_engine.py` T01-T14、`test_rebalance.py`），改動 schema 會牽動全部 → 強迫一次性大改
- 新 schema → 新 test suite，舊 test 零影響，**可平行開發**

### 2.4 Dev data 5 row 不用 migrate

- Stanley 已確認 Q3 既有 trade_journal 只有 5 row dev data
- separate schema → 雙 schema 並存，dev DB 不需 SET NOT NULL backfill；若 inherit-and-extend → `ALTER TABLE trade_accounts ADD COLUMN user_id NOT NULL` 須先 backfill「第一個 admin user」否則 fail

### 2.5 模組邊界乾淨（依賴方向 strictly inward）

新 schema 對 `app/modules/trade_journal/` 的依賴 = **只 import `fifo_engine.py`**（pure function，line 1 已宣告 no DB / no side effects），不依賴 `position_sync.py`（schema-coupled，line 10 `from app.models.journal import Position, Trade, TradeLot`）→ 依賴方向 inward only，零循環

### 2.6 未來合併彈性

- 若 Phase 4+ Stanley 決定合併兩個 module（例如「對賬功能進化成完整 trade journal」）→ 可寫 one-shot migration 把 `portfolio_trades` 倒進 `trades`
- 若先合再分 → 不可逆；schema 不會回滾

---

## 3. Architectural Goals

| Goal | 實現方式 |
|------|---------|
| **G1. Pure domain logic** | `app/modules/portfolio/` 模組零 DB / FastAPI 依賴，全 dataclass + Decimal 純函數；reuse `fifo_engine.FIFOEngine` |
| **G2. User isolation by construction** | 所有 service 層方法 signature 第一個參數固定 `user_id: int`；repo 層 query 第一個 `WHERE` 永遠是 `account.user_id = user_id`；無法在 architecture 上「忘記」加 user filter |
| **G3. Single source of truth = trades** | `portfolio_positions` / `portfolio_lots` 為 derived view，可由 `portfolio_trades` 完整 rebuild；提供 `rebuild_positions(account_id)` 工具方法 |
| **G4. Tier limit as data, not code** | YAML 改數字不用 deploy code；`@lru_cache` warm-up boot 一次；Pydantic 確保 strong-typed |
| **G5. Live price as pluggable interface** | `LivePriceFetcher` Protocol → TW impl / US impl / Mock impl 可獨立 swap；測試用 mock，prod 用真實 fetcher |
| **G6. Test pyramid by layer** | Pure logic → unit / Repo → integration（DB only）/ API → full stack（mock price）/ External adapter → contract test |
| **G7. Phase 4+ extension hooks defined upfront** | 預留 `TradeImportAdapter` / `CorporateActionProcessor` / `FXConverter` interface stubs，避免 Phase 4 改動需要動 Phase 1 code |

---

## 4. Overall Architecture

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                          HTTP / FastAPI Layer                                │
│                                                                              │
│  app/api/v1/holdings/                                                        │
│    ├─ accounts.py    (POST/GET/PATCH/DELETE /holdings/accounts)              │
│    ├─ trades.py      (POST/GET/PATCH/DELETE /holdings/accounts/{id}/trades)  │
│    ├─ positions.py   (GET /holdings/positions  cross-account aggregate)      │
│    └─ summary.py     (GET /holdings/summary    KPI row)                      │
│                                                                              │
│  cross-cutting: Depends(require_auth) + Depends(tier_guard(feature=...))     │
└────────────────────────────────────┬─────────────────────────────────────────┘
                                     │  (Pydantic schemas in app/schemas/portfolio/)
                                     ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                       Service Layer (orchestration)                          │
│                                                                              │
│  app/services/portfolio/                                                     │
│    ├─ account_service.py   (CRUD on accounts + tier guard call)              │
│    ├─ trade_service.py     (add/update/delete trade → calls domain + repo)   │
│    ├─ position_service.py  (aggregate positions × live price × P&L)          │
│    └─ summary_service.py   (KPI row composition)                             │
│                                                                              │
│  Rule: 不直接寫 raw SQL，必須透過 repository                                  │
└──────────┬──────────────────────────────────────────────┬──────────────────┘
           │                                              │
           ▼                                              ▼
┌──────────────────────────────────┐    ┌──────────────────────────────────────┐
│  Domain Logic Layer (PURE)        │    │  Repository Layer                     │
│                                   │    │                                       │
│  app/modules/portfolio/           │    │  app/repositories/portfolio/          │
│    ├─ pnl.py                      │    │    ├─ account_repo.py                 │
│    ├─ cost_basis.py               │    │    ├─ trade_repo.py                   │
│    │   (wraps FIFOEngine via      │    │    ├─ lot_repo.py                     │
│    │   import from trade_journal) │    │    ├─ position_repo.py                │
│    ├─ dividend_processor.py       │    │    └─ price_lookup_repo.py            │
│    └─ live_price_fetcher.py       │    │                                       │
│       (Protocol + TW/US impl)     │    │  Rule: 純 CRUD + query，無 business   │
│                                   │    │       logic；不算 P&L、不判斷 tier    │
│  Rule: 零 DB import / 零 FastAPI  │    └──────────────────────────────────────┘
│       import；全 Decimal / dataclass│                          │
└──────────────────────────────────┘                          ▼
                                                    ┌────────────────────────┐
                                                    │   Data Layer (DB)       │
                                                    │                         │
                                                    │  app/db/models/portfolio/│
                                                    │  PostgreSQL tables      │
                                                    │  (see §6)               │
                                                    └────────────────────────┘

┌─────────────────────────────────────────────────────────────────────────────┐
│   Cross-Cutting Concerns                                                     │
│                                                                              │
│  app/billing/tier_limits.py + config/tier_limits.yaml  (YAML+Pydantic+cache) │
│  app/middleware/tier_guard.py::require_tier()  (既有，min-tier 門檻)         │
│  app/auth.py::require_auth                                                   │
│  app/services/audit.py::log_audit_event                                      │
│  app/obs/metrics.py  (新增 portfolio_* counters)                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

**依賴方向（strictly inward arrows）：**

```
api → services → domain        (允許)
api → services → repository    (允許)
api → schemas                  (允許 — 但 schemas 不 import services)
services → domain              (允許)
services → repository          (允許)
repository → db.models         (允許)
domain → trade_journal.fifo_engine (允許；唯一一條跨模組 import)

domain ↛ db.models / fastapi   (禁止 — pure)
repository ↛ services / domain (禁止 — 只做 CRUD)
schemas ↛ services / domain    (禁止 — DTO only)
api ↛ db.models 直接 query     (禁止 — 必須透過 repo)
```

---

## 5. Module Breakdown

### 5.1 `app/modules/portfolio/` — Domain logic, pure

純函數 / dataclass / `Decimal` only。所有檔案無 SQLAlchemy import、無 FastAPI import。

| File | Responsibility | 對外 surface |
|------|----------------|------------|
| `pnl.py` | Unrealized P&L、daily Δ、Q6 simple gain 算法 | `compute_unrealized(qty, avg_cost, last_price) -> Decimal`、`compute_daily_change(qty, last_price, prev_close)`、`compute_total_gain(positions: list[PositionView]) -> GainBreakdown` |
| `cost_basis.py` | 包裝 `FIFOEngine`（import from `app.modules.trade_journal.fifo_engine`），定義 `LotView` dataclass + `apply_buy_to_lots` / `apply_sell_to_lots` 純函數 | `apply_buy(open_lots, qty, price, fee) -> list[LotView]`、`apply_sell(open_lots, qty, price, fee, tax) -> SellResult` |
| `dividend_processor.py` | 配息對成本基礎的影響（Phase 3）— 現金股利不動 avg_cost，股票股利視同 split | `apply_cash_dividend(...)`、`apply_stock_dividend(...)` |
| `live_price_fetcher.py` | `LivePriceFetcher` Protocol + `TWLivePriceFetcher` / `USLivePriceFetcher` impl + `MockLivePriceFetcher`（測試用） | `async def fetch_price(symbol, market) -> PriceQuote` |

**Domain layer 對外只暴露 dataclass / Protocol，不暴露 ORM。**

### 5.2 `app/services/portfolio/` — Orchestration

每個 service 一個檔案。Service 持有 DB session、呼叫 repo + domain，做 transaction 邊界控制。

| File | Responsibility |
|------|----------------|
| `account_service.py` | `create_account(user_id, body)` / `list_accounts(user_id)` / `get_account(user_id, id)` / `update_account` / `delete_account`；建立前 call `tier_limits.assert_can_create_account(user_id, current_count)` |
| `trade_service.py` | `add_trade(user_id, account_id, body)` / `update_trade(user_id, trade_id, body)` / `delete_trade(user_id, trade_id)`；UPDATE/DELETE 觸發 `rebuild_positions(account_id)` |
| `position_service.py` | `list_positions(user_id)` — 跨帳戶 aggregate：query positions → query latest prices → call `pnl.compute_unrealized` / `compute_daily_change` |
| `summary_service.py` | `get_summary(user_id)` — KPI row 組合（total MV / total cost / total unrealized / realized YTD / daily Δ / Q6 gain） |

**Rule：service 必須是 stateless（每次注入 db session），不持有跨 request 的 state。**

### 5.3 `app/repositories/portfolio/` — DB only

只做 CRUD + query，**不做 business logic**。一個 repo 一個 file。

| File | Tables touched |
|------|----------------|
| `account_repo.py` | `portfolio_accounts` |
| `trade_repo.py` | `portfolio_trades` |
| `lot_repo.py` | `portfolio_lots`（FIFO lots） |
| `position_repo.py` | `portfolio_positions` |
| `price_lookup_repo.py` | `stock_prices`（既有表，read only） |

**Rule：所有 query 第一個 WHERE 必須 join account 並 filter `user_id`，由 architecture 強制。**

### 5.4 `app/api/v1/holdings/` — HTTP only

**Prefix 選用 `/holdings`** 而非 `/portfolio`，因為後者已被 `app/api/v1/portfolio.py:28` 註冊為 portfolio backtest 用途（`router = APIRouter(prefix="/portfolio", tags=["portfolio"])`，line 28；已在 `router.py:25` 掛載）。

| File | Routes |
|------|--------|
| `accounts.py` | `POST /holdings/accounts`、`GET /holdings/accounts`、`GET /holdings/accounts/{id}`、`PATCH /holdings/accounts/{id}`、`DELETE /holdings/accounts/{id}` |
| `trades.py` | `POST /holdings/accounts/{id}/trades`、`GET /holdings/accounts/{id}/trades`、`PATCH /holdings/trades/{id}`、`DELETE /holdings/trades/{id}` |
| `positions.py` | `GET /holdings/positions` — 跨帳戶 aggregated |
| `summary.py` | `GET /holdings/summary` — KPI row |

**全部 routes：**
- `Depends(require_auth)` — 強制登入（樣板：`app/api/v1/watchlist.py:54`）
- `Depends(tier_guard(feature="..."))` — 數量上限檢查（見 §9）

備選 namespace：`/api/v1/portfolio_tracker/`（語意明確但較長）；最終命名留 Stanley 拍板（Q in §14）。

### 5.5 `app/db/models/portfolio/` — ORM, one file per table

樣板對齊 `app/models/journal.py`（單一檔多 model）或 `app/models/watchlist_item.py`（一檔一 model）。**推薦一檔一 model**，理由：

- 拆檔 → grep 友善（`account.py` 一定是 PortfolioAccount）
- 拆檔 → 各 model FK 順序明確不會打架
- Index / UniqueConstraint 在同檔，閱讀成本低

| File | Model |
|------|-------|
| `account.py` | `PortfolioAccount` |
| `trade.py` | `PortfolioTrade` |
| `lot.py` | `PortfolioLot` |
| `position.py` | `PortfolioPosition` |
| `dividend.py` | `PortfolioDividend`（Phase 3 才啟用，Phase 1 預先建空檔註解） |
| `snapshot.py` | `PortfolioSnapshot`（Phase 4 才啟用） |

注意：與既有 `app/models/journal.py::PortfolioSnapshot` 同名，**但屬於不同 namespace + 不同 table_name `portfolio_snapshots_v2`**（既有那張是 trade_journal 用的，且 unused），Phase 4 拆解時須改名避免混淆 — 或新表叫 `holdings_snapshots`。

### 5.6 `app/billing/tier_limits.py` + `config/tier_limits.yaml` — Tier guard

**目的：** tier 數量上限 (accounts / trades / unique symbols) 改 YAML 即可，不重啟 code。

**新增目錄：** `app/billing/`（既有 `app/modules/billing/` 是 Stripe 服務；本檔屬於 billing 領域但是 cross-cutting 限額，新放在 `app/billing/`；或考慮放在 `app/services/billing/tier_limits.py`，留 Stanley 拍板）。

對外 API：

```python
# Pseudocode — implementation details left for plan stage
tier_limits.get_limit(user_tier=UserTier.FREE, feature="accounts") -> int | None  # None = unlimited
tier_limits.has_feature(user_tier=UserTier.FREE, feature="live_price") -> bool
tier_limits.assert_can_create_account(user_tier, current_count) -> None  # raises HTTPException(403)
```

**Caching：** `@lru_cache` on module load；reload-on-yaml-edit 機制 Phase 2+ 再考慮（Q in §14）。

**Pydantic schema (file structure, not code)：**

```
TierLimitsConfig
├── free: TierFeatureLimits
├── basic: TierFeatureLimits
└── pro: TierFeatureLimits

TierFeatureLimits
├── max_accounts: int | None        # null = unlimited
├── max_trades_per_account: int | None
├── max_unique_symbols: int | None
├── live_price: bool
├── history_range_days: int | None  # 30 / 365 / null
└── live_price_cache_ttl_sec: int   # 300 / 60 / 0
```

---

## 6. Schema Design

### 6.1 Migration ID

**`UNI-PORT-001_add_portfolio_tables.py`**（已確認未被佔用，sorted listing 顯示既有為 `UNI-BILL-001/002` / `UNI-COMP-001` / `UNI-WATCH-001`）。

### 6.2 Tables（6 張）

**Decimal-as-string 規範：** 所有 `Numeric(...)` 欄位在 schema 層回傳 string（既有 STRATOS / Pydantic Settings 規範 `CLAUDE.md` line 35）。`Numeric(24, 8)` 對齊 `app/models/journal.py:76 Trade.price` 既有規範。

#### Table 1: `portfolio_accounts`

| Column | Type | Constraint |
|--------|------|-----------|
| `id` | `BigInteger` | PK |
| `user_id` | `BigInteger` | FK `users.id` ON DELETE CASCADE, NOT NULL, **INDEX** |
| `name` | `String(100)` | NOT NULL |
| `broker` | `String(50)` | nullable |
| `market` | `Market` enum | NOT NULL (`TW_TWSE`/`TW_TPEX`/`US_NYSE`/`US_NASDAQ`) — reuse `app/models/enums.py::Market` |
| `currency` | `String(10)` | NOT NULL (`TWD`/`USD`) |
| `description` | `Text` | nullable |
| `created_at` | `DateTime(tz=True)` | server_default=now() |

Index: `ix_portfolio_accounts_user_id`

#### Table 2: `portfolio_trades`

| Column | Type | Constraint |
|--------|------|-----------|
| `id` | `BigInteger` | PK |
| `account_id` | `BigInteger` | FK `portfolio_accounts.id` ON DELETE CASCADE, NOT NULL |
| `symbol` | `String(20)` | NOT NULL |
| `market` | `Market` enum | NOT NULL |
| `action` | `String(10)` | NOT NULL — BUY / SELL / DIVIDEND / SPLIT |
| `trade_date` | `Date` | NOT NULL (避開 reserved word `date`) |
| `price` | `Numeric(24, 8)` | nullable (string in API) |
| `quantity` | `Numeric(24, 8)` | nullable |
| `fee` | `Numeric(24, 8)` | default 0 |
| `tax` | `Numeric(24, 8)` | default 0 |
| `note` | `Text` | nullable |
| `created_at` | `DateTime(tz=True)` | server_default=now() |
| `updated_at` | `DateTime(tz=True)` | server_default=now(), onupdate=now() |

Index: `ix_portfolio_trades_account_symbol(account_id, symbol, market, trade_date)`

#### Table 3: `portfolio_lots`

| Column | Type | Constraint |
|--------|------|-----------|
| `id` | `BigInteger` | PK |
| `trade_id` | `BigInteger` | FK `portfolio_trades.id` ON DELETE CASCADE |
| `account_id` | `BigInteger` | FK `portfolio_accounts.id` ON DELETE CASCADE |
| `symbol` | `String(20)` | NOT NULL |
| `market` | `Market` enum | NOT NULL |
| `original_qty` | `Numeric(24, 8)` | NOT NULL |
| `remaining_qty` | `Numeric(24, 8)` | NOT NULL |
| `cost_per_unit` | `Numeric(24, 8)` | NOT NULL |
| `is_exhausted` | `Boolean` | default False, INDEX |

Index: `ix_portfolio_lots_fifo(account_id, symbol, market, is_exhausted, trade_id)`

#### Table 4: `portfolio_positions`

| Column | Type | Constraint |
|--------|------|-----------|
| `id` | `BigInteger` | PK |
| `account_id` | `BigInteger` | FK `portfolio_accounts.id` ON DELETE CASCADE, INDEX |
| `symbol` | `String(20)` | NOT NULL |
| `market` | `Market` enum | NOT NULL |
| `currency` | `String(10)` | NOT NULL |
| `quantity` | `Numeric(24, 8)` | default 0 |
| `avg_cost_fifo` | `Numeric(24, 8)` | nullable |
| `total_cost` | `Numeric(24, 8)` | nullable |
| `realized_pnl` | `Numeric(24, 8)` | default 0 |
| `is_closed` | `Boolean` | default False, INDEX |
| `last_updated` | `DateTime(tz=True)` | server_default=now(), onupdate=now() |

Unique: `uq_portfolio_positions(account_id, symbol, market)`

#### Table 5: `portfolio_dividends` (Phase 3)

| Column | Type | Constraint |
|--------|------|-----------|
| `id` | `BigInteger` | PK |
| `account_id` | `BigInteger` | FK `portfolio_accounts.id` |
| `symbol` | `String(20)` | NOT NULL |
| `ex_date` | `Date` | NOT NULL |
| `amount_per_share` | `Numeric(24, 8)` | NOT NULL |
| `kind` | `String(10)` | CASH / STOCK |
| `created_at` | `DateTime(tz=True)` | server_default=now() |

Phase 1 不啟用，但先在 migration 建空表，避免 Phase 3 又需要 down-migrate 之前。**或** Phase 1 完全不建，Phase 3 再做（推薦：Phase 1 不建，避免空表困擾）。

#### Table 6: `holdings_snapshots` (Phase 4+)

延後設計；Phase 4 plan 再拆。注意命名避開既有 `portfolio_snapshots`。

### 6.3 Indices summary

- `ix_portfolio_accounts_user_id` — user list query 必需
- `ix_portfolio_trades_account_symbol` — trade history query
- `ix_portfolio_lots_fifo` — FIFO 取 oldest 開放 lot
- `uq_portfolio_positions(account_id, symbol, market)` — upsert 必需
- 不加 `partial index WHERE is_closed = FALSE`（Phase 1 不需要，row 數還少）

### 6.4 FK ON DELETE 行為

- `account.user_id` → users CASCADE（user 帳號刪除 → 所有 portfolio 資料隨之）
- `trade.account_id` → portfolio_accounts CASCADE（刪帳戶 → trades 全刪 → lots / positions 自動 CASCADE）
- `lot.trade_id` → portfolio_trades CASCADE
- `position.account_id` → portfolio_accounts CASCADE

對齊既有 `watchlist_items.user_id ON DELETE CASCADE`（`app/models/watchlist_item.py:28`）。

---

## 7. P&L Logic Specs

### 7.1 Unrealized P&L

對單一 position：

```
unrealized_pnl     = (last_price - avg_cost_fifo) * quantity
                   = market_value - total_cost
unrealized_pnl_pct = unrealized_pnl / total_cost
```

- `last_price` 來源：見 §8
- `avg_cost_fifo` = `total_cost / quantity`（由 FIFO 計算後 cached 在 `portfolio_positions`）
- 邊界：`quantity == 0` → return `Decimal("0")` for both（不分母）；`total_cost == 0` → pct = `Decimal("0")`

### 7.2 Realized P&L

複用 `app/modules/trade_journal/fifo_engine.py::FIFOEngine.process_sell`（line 55-90）。對每筆 SELL：

```
proceeds     = price * qty - fee - tax
total_cost   = Σ over consumed lots (cost_per_unit * shares_consumed)
realized_pnl = proceeds - total_cost
```

`portfolio_positions.realized_pnl` 累加值。

### 7.3 Daily change（per-stock + portfolio-wide）

**Per-stock：**

```
daily_change     = (last_price - prev_close) * quantity
daily_change_pct = (last_price - prev_close) / prev_close
```

`prev_close` 取 `stock_prices` table where `date < today` 最新一筆 close。

**Portfolio-wide：**

```
portfolio_daily_change     = Σ over open positions (daily_change)
portfolio_daily_change_pct = portfolio_daily_change / Σ (prev_close * quantity)
```

**多市場：** TW position 用 TWD 直接加，US position 須先以 `fx_rates`（既有 `app/models/journal.py:188-198`）折算 TWD 後加。**Phase 1 簡化：fx 用 hardcoded 30.5（in YAML），Phase 2 接 `fx_rates`。**

### 7.4 資產增益 (Q6 simple gain)

定義（已敲定）：

```
total_gain     = Σ (qty × last_price)   −   Σ (qty × avg_cost_fifo)
               = total_market_value     −   total_cost_basis
total_gain_pct = total_gain / total_cost_basis
```

**只算當下持股（即 `is_closed = FALSE` 的 positions），已賣出的部位不累計。**

邊界：

- 全部已賣出 → `total_cost = 0` → return `Decimal("0")` for gain, gain_pct
- `total_cost_basis < 0`（理論上不可能，realized 已從 positions 移除）→ raise invariant error

### 7.5 公式套用流程（service 層 pseudocode）

```
def get_summary(user_id):
    positions = position_repo.list_open(user_id)      # 跨帳戶
    symbols   = unique(positions.symbol)
    prices    = price_lookup_repo.get_latest(symbols) # batch query
    prev      = price_lookup_repo.get_prev_close(symbols)

    enriched = [
      pnl.PositionView(
        position    = p,
        last_price  = prices[p.symbol],
        prev_close  = prev[p.symbol],
      ) for p in positions
    ]
    gain = pnl.compute_total_gain(enriched)
    return SummaryResponse(...)
```

---

## 8. Live Price Feed Architecture

### 8.1 Pre-reading 探源結果

| 來源 | 路徑 | 涵蓋 | 狀態 |
|------|------|------|------|
| `app/modules/price_updater/twse.py` | TWSE openapi (`STOCK_DAY_ALL`) | TW 上市 | 已 prod；只跑 daily |
| `app/modules/price_updater/tpex.py` | TPEX openapi | TW 上櫃 | 已 prod；只跑 daily |
| `app/modules/price_updater/yfinance_provider.py` | yfinance lib | US 全市 + TW 歷史 | 已 prod，但 fetch_daily/fetch_history 皆非 live |
| `app/api/v1/prices.py` | `/api/v1/prices/update` + `/backfill` | manual trigger | 已 prod |
| `app/modules/finmind/*` | FinMind | TW fundamentals / institutional | 已 prod；無 intraday |

**結論：所有既有 source 為 daily close，無 intraday / live。**

### 8.2 LivePriceFetcher Protocol（abstract interface）

```
class LivePriceFetcher(Protocol):
    async def fetch_price(self, symbol: str, market: Market) -> PriceQuote: ...
    async def fetch_prices(self, symbols: list[tuple[str, Market]]) -> dict[tuple[str, Market], PriceQuote]: ...

@dataclass(frozen=True)
class PriceQuote:
    symbol: str
    market: Market
    last_price: Decimal       # current or latest close
    prev_close: Decimal       # 前一交易日 close
    as_of: datetime           # 報價時間
    source: str               # "twse_realtime" / "yfinance_intraday" / "stock_prices_db"
    is_realtime: bool         # True if intraday, False if EOD fallback
```

### 8.3 Phase 1 impl 選型

**MVP 不接 realtime，先用 `stock_prices` table 的最新 close 當 last_price。**

```
class DailyCloseLivePriceFetcher:
    """Phase 1 impl: 從 stock_prices 取最新 close 當 last_price。
    Source = 'stock_prices_db', is_realtime = False。
    """
```

Phase 2 加 `TWSELivePriceFetcher`（TWSE realtime API or FinMind intraday）+ `YFinanceLivePriceFetcher`（`yf.Ticker.fast_info`）。

### 8.4 Cache strategy（trade-off 分析）

| 選項 | 優點 | 缺點 |
|------|------|------|
| **In-memory TTL（`cachetools.TTLCache`）** | 零依賴；FastAPI worker 內 hit 率高；簡單 | 多 worker 各自 cache（不一致）；重啟丟失；無法跨機 |
| **Redis TTL** | 跨 worker 共享；TTL 自動過期；既有 `redis_url` config | 多一跳網路；序列化成本；需處理 connection 池 |
| **無 cache** | 最簡單；資料 freshest | API rate limit 容易爆；不同 user 重複打同 symbol |

**推薦：in-memory TTL（Phase 1）+ Phase 2 視 traffic 升級 Redis。**

理由：MVP user 數小（< 100），多 worker cache miss 可接受；Redis 增加 deploy 複雜度。Cache TTL 從 `tier_limits.yaml` 讀取（FREE 300s / BASIC 60s / PRO 0s = live）。

### 8.5 Retry policy / rate limit

樣板：`app/modules/price_updater/updater.py:149-169 _fetch_with_retry`（指數 backoff，max_retries=3）。LivePriceFetcher 各 impl 內部自帶 retry。

對於 yfinance：已知 unofficial API 易被 throttle，須在 wrapper 加 jitter；rate limit 觸發時 fallback 到 `stock_prices` table。

---

## 9. Tier Guard Design

### 9.1 兩層 tier guard 設計（與既有 `require_tier()` 並存）

| 既有 | 新增 |
|------|------|
| `app/middleware/tier_guard.py::require_tier(min_tier)` | `app/billing/tier_limits.py::tier_guard(feature=...)` |
| 用途：**門檻** — endpoint 要 BASIC 才能用 | 用途：**配額** — FREE 最多 1 個 account / 50 trade |
| 樣板：`/screener` 要 BASIC | 樣板：`POST /holdings/accounts` 檢查 current count vs limit |

兩者**正交**，可疊加：

```python
# Pseudocode
@router.post("/accounts")
async def create_account(
    body: AccountCreate,
    user: User = Depends(require_auth),  # 一定要登入
    db: AsyncSession = Depends(get_db),
    _: None = Depends(tier_guard(feature="accounts.create")),  # 配額檢查
):
    ...
```

### 9.2 YAML 結構

```yaml
# config/tier_limits.yaml
free:
  max_accounts: 1
  max_trades_per_account: 50
  max_unique_symbols: 10
  live_price: false
  history_range_days: 30
  live_price_cache_ttl_sec: 300

basic:
  max_accounts: 3
  max_trades_per_account: 500
  max_unique_symbols: 50
  live_price: false
  history_range_days: 365
  live_price_cache_ttl_sec: 60

pro:
  max_accounts: null            # null = unlimited
  max_trades_per_account: null
  max_unique_symbols: null
  live_price: true
  history_range_days: null
  live_price_cache_ttl_sec: 0
```

### 9.3 Pydantic model（schema 邏輯，非 code）

```
class TierFeatureLimits(BaseModel):
    max_accounts: int | None
    max_trades_per_account: int | None
    max_unique_symbols: int | None
    live_price: bool
    history_range_days: int | None
    live_price_cache_ttl_sec: int = Field(ge=0)

    @field_validator(...)
    # validate: 數值欄位若非 None 必 > 0

class TierLimitsConfig(BaseModel):
    free: TierFeatureLimits
    basic: TierFeatureLimits
    pro: TierFeatureLimits
```

### 9.4 Loader

```
@lru_cache(maxsize=1)
def load_tier_limits() -> TierLimitsConfig:
    path = Path("config/tier_limits.yaml")
    raw = yaml.safe_load(path.read_text())
    return TierLimitsConfig.model_validate(raw)
```

**Hot reload：** Phase 1 不做；YAML 改動需 restart worker（同 `app/config.py:42 model_config = {"env_file": ".env"}` 的 Pydantic Settings 思路）。

### 9.5 FastAPI Dependency factory

```
def tier_guard(feature: str) -> Callable:
    """產生 dependency；feature 字串如 'accounts.create' / 'trades.create' / 'live_price'"""
    async def _check(
        user: User = Depends(require_auth),
        db: AsyncSession = Depends(get_db),
    ) -> None:
        limits = load_tier_limits()
        tier_limits = getattr(limits, user.tier.value)  # free / basic / pro
        # dispatch by feature
        if feature == "accounts.create":
            current = await account_repo.count_by_user(db, user.id)
            if tier_limits.max_accounts is not None and current >= tier_limits.max_accounts:
                raise HTTPException(403, detail="portfolio_account_limit_exceeded")
        elif feature == "trades.create":
            # 須帶 account_id 進來，否則無法 count；FastAPI dep 從 path param 取
            ...
        elif feature == "live_price":
            if not tier_limits.live_price:
                raise HTTPException(403, detail="live_price_requires_pro")
    return _check
```

**Trade-off：** Path param 依賴需要從 `Request` 取，會比較 hacky；replacement 是 service 層 explicit call `tier_limits.assert_can_create_account(user_id, current_count)`，更明確但無法純宣告式 — Stanley 可在 plan 階段拍板。

---

## 10. Testing Strategy

### 10.1 Unit Tests（zero DB, zero HTTP）

**目標：** ~30 cases。樣板對齊 `tests/unit/test_fifo_engine.py`（已有 T01-T14 純函數 parametrize）。

| 對象 | Test cases (estimated) |
|------|----------------------|
| `pnl.compute_unrealized` | 8 cases：正常 / qty=0 / total_cost=0 / 負值 / 高精度 Decimal / TWD US 同價位 / prev_close 缺失 / last_price < avg |
| `pnl.compute_daily_change` | 6 cases：漲 / 跌 / prev_close = 0 / qty = 0 / 多 position 加總 / 跨市場（fx） |
| `pnl.compute_total_gain` (Q6) | 4 cases：全部獲利 / 全部虧損 / 全部 closed → 0 / 部分 closed 部分 open |
| `cost_basis.apply_buy` | 4 cases：第一筆 / 補倉 / 含 fee / 零 quantity error |
| `cost_basis.apply_sell` (wrap FIFOEngine) | 4 cases：partial / 跨 lot / insufficient → raise / 含 tax |
| `dividend_processor` (Phase 3 起算) | Phase 1 暫不測 |
| `live_price_fetcher.MockLivePriceFetcher` | 4 cases：fetch single / batch / cache hit / cache expired |

**Pattern：** `@pytest.mark.parametrize` table-driven，每個 case (id, inputs, expected) 顯式列出。

### 10.2 Integration Tests（DB, no live price）

**目標：** ~25 cases。樣板對齊 `tests/integration/test_journal_api.py`（SQLite in-memory + JSONB patch + `app.dependency_overrides[get_db]`）。

| 對象 | Test cases |
|------|-----------|
| `account_repo` CRUD | 5 cases：create / list / get / update / delete + cascade |
| `trade_repo` CRUD | 5 cases：add BUY / add SELL / list by account / pagination / soft delete? |
| `lot_repo` FIFO query | 3 cases：取 open lots / 排序正確 / `is_exhausted` filter |
| `position_repo` upsert | 4 cases：first insert / upsert update / close detection / cross-account aggregate |
| Tier guard enforcement | 4 cases：FREE create 2nd account 403 / FREE 51st trade 403 / BASIC 4th account 403 / monetization=False bypass |
| User isolation | 4 cases：user A 看不到 user B account (404) / 改不到 (403) / 刪不到 (404) / cascade delete user → 全清 |

**Fixtures：** `free_user`、`basic_user`、`pro_user`、`mock_live_price`（dependency override）、`portfolio_seed`（建 1 帳戶 + 3 trade）。

### 10.3 API Tests（full stack, mock live price）

**目標：** ~20 cases。

| Endpoint | Test cases |
|----------|-----------|
| `POST /holdings/accounts` | 201 happy / 401 unauthenticated / 403 tier exceeded / 422 invalid market |
| `POST /holdings/accounts/{id}/trades` | 201 BUY / 201 SELL / 422 insufficient shares / 422 invalid action / 403 not owner |
| `PATCH /holdings/trades/{id}` | 200 with positions rebuilt / 403 not owner / 404 |
| `DELETE /holdings/trades/{id}` | 200 with positions rebuilt / 403 not owner |
| `GET /holdings/positions` | 200 跨帳戶 / 200 mock live price 注入 / 200 空 → `[]` |
| `GET /holdings/summary` | 200 計算正確 / 200 Q6 gain only counts open / 200 多市場 fx |

### 10.4 Contract Tests（external dependencies）

**目標：** ~6 cases，防 upstream API breaking change。

| Adapter | Test |
|---------|------|
| `YFinanceLivePriceFetcher` | mock `yf.Ticker.fast_info` shape；snapshot test 防 yfinance v0.2.x → v0.3.x 欄位重命名 |
| `TWSELivePriceFetcher` (Phase 2) | mock TWSE openapi JSON shape |
| `stock_prices` DB read | row shape 對齊 `app/models/price.py::StockPrice` |

### 10.5 Test Fixtures Inventory

```
tests/integration/conftest.py (新增)
├── free_user_token       (UserTier.FREE，回傳 Authorization header dict)
├── basic_user_token
├── pro_user_token        (既有，line 11)
├── portfolio_account     (建 1 個 PortfolioAccount，回 account_id)
├── portfolio_seed        (account + 3 trade BUY/BUY/SELL)
├── mock_live_price       (注入 MockLivePriceFetcher，回 dict[symbol, Decimal])
└── stock_price_seed      (insert stock_prices for 2330.TW + AAPL)
```

---

## 11. Extensibility Hooks

### 11.1 Phase 4+ extension points

| 擴展點 | Interface | 實作方式 |
|-------|----------|---------|
| **FX support (multi-currency)** | `FXConverter Protocol` with `convert(amount, from_ccy, to_ccy, as_of) -> Decimal` | Phase 1 簡單 hardcoded；Phase 2 接 `fx_rates`；Phase 4+ 接外部 FX API |
| **Corporate actions** | `CorporateActionProcessor` with `apply(account_id, action: SplitAction|DividendAction|SpinOffAction)` | Phase 3 起 dividend；Phase 4 split + spin-off |
| **Broker API auto-import** | `TradeImportAdapter Protocol` with `async def import_trades(user_credential) -> list[TradeData]` | Phase 4+；既有 CSV import 也走這個 interface |
| **Tax reporting export** | `TaxReportExporter` with `export(user_id, year) -> bytes (PDF/CSV)` | Phase 4+；reuse `portfolio_trades` immutable log |
| **Snapshot job** | `SnapshotComputer.compute(user_id, as_of_date) -> SnapshotRow` | Phase 4；cron 每日跑 |

### 11.2 Anti-coupling rules（hard constraints）

| Rule | 違反後果 |
|------|---------|
| **R1. Domain layer (`app/modules/portfolio/`) MUST NOT import from `app/db/` or `fastapi`** | Pure logic 變 schema-coupled；單元測試需要 DB；無法在 CLI 工具或 batch job 重用 |
| **R2. Service layer MUST NOT issue raw SQL or `db.execute(text(...))`** | Repo pattern 失效；下次 schema migration 需要 grep service / api 全部地方；SQL injection 風險 |
| **R3. Repository layer MUST NOT contain business logic (P&L 計算 / tier 判斷)** | Repo 與 domain 邏輯混雜；無法切換 ORM（如未來換 SQLModel）；無法獨立測 repo CRUD |
| **R4. Schemas (`app/schemas/portfolio/`) MUST NOT import from `app/services/` or `app/modules/`** | DTO 反向耦合；circular import；Pydantic 變成業務邏輯載體 |
| **R5. API layer MUST NOT directly query DB models** | 跳過 repo → 跳過 user_id 強制 filter → 安全漏洞；違反 §3 G2 |
| **R6. Cross-module imports limited to `trade_journal.fifo_engine.FIFOEngine` + `trade_journal.fifo_engine.Lot/FIFOResult/InsufficientSharesError`** | 超出 → 違反 §2 separate schema 設計初衷；產生隱式相依 |

**Enforcement：** 可在 CI 加 `import-linter` rule，PR check 自動掃。Phase 1 先靠 review；違反次數 ≥ 3 加 CI。

---

## 12. Risks & Mitigations

| Risk | Impact | Mitigation |
|------|--------|-----------|
| **R1. Live price API rate limit（yfinance / TWSE）** | 持倉頁 5xx；user invisible | (a) `tier_limits.yaml` 限 FREE cache 5 min；(b) Phase 1 DailyCloseLivePriceFetcher 不打外部，全 DB 讀；(c) 加 retry + jitter |
| **R2. Race condition：同 account 同時兩筆 SELL 同 symbol，雙方都 `process_sell` 看到 same open_lots** | 一筆會 insufficient 或 double consume | `portfolio_lots.is_exhausted` 更新前 `SELECT ... FOR UPDATE`；transaction isolation = SERIALIZABLE for trade ops；或 application-level lock per (account_id, symbol) |
| **R3. Tier downgrade with existing data 超限** | FREE downgrade 後仍有 5 個 account，但 limit = 1 | downgrade 不刪資料；後續 create 動作被 tier_guard 擋；UI 顯示「您有 5 個帳戶，超過 FREE 上限，可繼續查看但無法新增」 |
| **R4. YAML typo 導致 boot 失敗** | Worker startup crash；prod 不能 deploy | Pydantic strict validate；`load_tier_limits()` 失敗 → log critical + raise；CI 加 YAML lint + Pydantic 預先 validate test |
| **R5. Stock_id format 不統一（TW vs US）** | `2330.TW` vs `2330` vs `AAPL` 三種寫法並存 → query 對不上 | (a) DB `stock_prices.symbol` 規範化為 `<code>.<MARKET_SUFFIX>` 形式；TW=`.TW`/`.TWO`，US=純 ticker；(b) `Portfolio Account` 建立時 normalize；(c) 加 helper `normalize_symbol(symbol, market)` 集中處理 |
| **R6. Cache invalidation（trade 改動後 positions 過時）** | UI 顯示舊持倉 | service 層在 `add_trade` / `update_trade` / `delete_trade` 結束時：(a) commit transaction；(b) invalidate position cache key（若 Phase 2 用 Redis）；(c) position 由 service 同步 rebuild，不靠 cache TTL 自然過期 |
| **R7. PATCH/DELETE trade 觸發 rebuild 成本** | account 有 5000 trade → rebuild 慢 | (a) 限制只能 PATCH 最近 90 天 trade（Q in §14）；(b) rebuild 改 background task；(c) 加 metric 觀察 p95 latency |
| **R8. Symbol 在 `stock_prices` 不存在 → last_price = null** | summary KPI 顯示 NaN；前端 crash | repo `get_latest` 回 `dict`，missing symbol 不在 key；domain `pnl.compute_*` 對 missing price 回 `PriceUnavailableError`；service 層 skip 該 position 並標 `last_price: null` 在 response，前端顯示「—」 |

---

## 13. Phased Rollout

### Phase 1 — Schema + CRUD + tier guard MVP（est. 2 days）

**交付物：**

- `UNI-PORT-001` migration（4 tables：accounts / trades / lots / positions）
- `app/db/models/portfolio/{account,trade,lot,position}.py`
- `app/modules/portfolio/{pnl,cost_basis,live_price_fetcher}.py`（pure logic）
- `app/repositories/portfolio/*.py`（5 個 repo）
- `app/services/portfolio/{account,trade,position,summary}_service.py`
- `app/api/v1/holdings/{accounts,trades,positions,summary}.py`
- `app/billing/tier_limits.py` + `config/tier_limits.yaml`
- `app/schemas/portfolio/*.py`
- Unit tests ~30 cases + integration tests ~25 cases + API tests ~20 cases

**Acceptance criteria：**

- AC1. User A 建 5 個帳戶（PRO），User B 看不到 A 任何資料（404 / 403）
- AC2. FREE user 建第 2 個 account 被擋（403 `portfolio_account_limit_exceeded`）
- AC3. `monetization=False` 時 FREE user 可建 N 個 account（行為等同 PRO）
- AC4. BUY 100 @580 + BUY 50 @620 → `positions.avg_cost_fifo = 593.33`；SELL 80 @700 → `realized_pnl = (700-580)*80 = 9600`，`positions.quantity = 70`
- AC5. PATCH trade 改 price → positions rebuild 後 avg_cost 同步更新
- AC6. DELETE 一筆中間 BUY → 後續 SELL 的 realized_pnl 重算
- AC7. Audit log 寫入 `portfolio_account_created` / `portfolio_trade_added` / `portfolio_trade_updated` / `portfolio_trade_deleted`

**對外 visible features：** Backend-only Phase；無 frontend。可由 curl / Postman 驗證。

### Phase 2 — Live price + summary KPI（est. 1.5 days）

**交付物：**

- `DailyCloseLivePriceFetcher`（從 `stock_prices` 取最新 close）
- `TWLivePriceFetcher`（FinMind intraday or TWSE realtime — Q in §14）
- `USLivePriceFetcher`（yfinance fast_info wrapper + retry + cache）
- In-memory TTL cache（`cachetools.TTLCache`），TTL 從 `tier_limits.yaml` 讀
- `GET /holdings/positions` 回傳 enriched 含 `last_price` / `unrealized_pnl` / `daily_change`
- `GET /holdings/summary` 回 KPI row（Q6 gain）
- Contract tests for yfinance + TWSE adapter

**AC：**

- B1. 持 2330.TW 100 股 avg_cost 580，`stock_prices` 今日 close 650 → unrealized=6950
- B2. portfolio summary daily_change 加總正確（兩支股票 same day）
- B3. `stock_prices` 缺今日資料 → fallback 最近一筆 close，response 標 `last_price_at`
- B4. FREE user `/holdings/positions` cache TTL 300s 生效（5 分鐘內第二次打不打 yfinance）
- B5. PRO user `live_price=true` 走 realtime fetcher
- B6. Mock missing symbol → 該 position 回 `last_price: null`，summary 不 crash

**對外 visible features：** Backend API 完整可用；可由 Postman 看到實際持倉與 P&L。

### Phase 3 — Frontend `/holdings` 頁（est. 2 days）

**交付物：**

- `frontend/app/holdings/page.tsx`
- `frontend/components/holdings/PortfolioKpiRow.tsx`（STRATOS KpiCard）
- `frontend/components/holdings/PositionsTable.tsx`（GlassPanel + tabular-nums + `var(--stock-up)`/`var(--stock-down)` 配色）
- `frontend/components/holdings/AddTradeModal.tsx`（BUY/SELL/DIVIDEND/SPLIT tabbed）
- `frontend/components/holdings/AccountSwitcher.tsx`
- API client 用 Decimal-as-string 處理（`Number()` 在 render 前才轉）

**AC：**

- C1. `cd frontend && npx tsc --noEmit` zero error
- C2. 截圖確認 STRATOS 視覺對齊（GlassPanel + AmbientBackground）
- C3. console 無 error；網路 panel 顯示 200
- C4. tier downgraded user 仍能看現有 portfolio（不被 504 擋）
- C5. 多帳戶切換 → URL 加 `?account_id=...`，刷新後保留

**對外 visible features：** 完整 `/holdings` 頁可使用。

### Phase 4+ Backlog

- Snapshot job + history chart（`holdings_snapshots`）
- Dividend processor + `portfolio_dividends` 表
- 升級資產增益至 TWR（Q6 from simple 升 weighted）
- CSV import（元大 / 永豐 / IB）
- 券商 API 自動同步
- 加密貨幣市場
- 稅務報表匯出 PDF/CSV
- Redis-backed live price cache
- YAML hot reload

---

## 14. Open Questions — RESOLVED 2026-05-20

**所有 Q14.x 已拍板，原問題 + 選項保留如下作為決策歷史。**

| # | 議題 | 決議 | vs agent 推薦 |
|---|------|------|---------------|
| Q14.1 | 既有 `/api/v1/journal/*` 處置 | **C** — 隱藏 OpenAPI + 不加 auth | ✓ 一致 |
| Q14.2 | Namespace 命名 | **`/api/v1/holdings/`** | ✓ 一致 |
| Q14.3 | Live price cache | **in-memory TTL（Phase 1）** | ✓ default 收 |
| Q14.4 | PATCH 歷史 trade UX | **A — 全開放 + audit log + 觀察 R7** | ✓ default 收 |
| Q14.5 | US 股 live price provider | **yfinance（Phase 1）**；付費 SaaS 留 Phase 4+ | ✓ default 收 |
| Q14.6 | tier_limits.py 模組位置 | **`app/modules/billing/tier_limits.py`** | ✓ 一致 |
| Q14.7 | Tier guard 模式 | **dependency-first + service 層補 assertion** | ✓ default 收 |
| Q14.8 | 既有 `portfolio_snapshots` 表 | **A — 保留** | ✓ default 收 |

**原問題與選項保留如下作為歷史：**

### Q14.1 既有 `/api/v1/journal/*` unauthenticated routes 怎麼處置？

選項：

- **A. 完全保留**（不動，dev 用）
- **B. 加 `require_auth` + tier guard**（兩套 namespace 平行運作，最終 deprecate journal）
- **C. 在 router 加 `include_in_schema=False` 隱藏 OpenAPI**（D2-style）
- **D. 直接從 `router.py:48` 移除 import + delete 檔**（清除 5 row dev data）

推薦 **C**（隱藏不刪，保留可 reuse fifo_engine 的測試覆蓋率），但 Stanley 可拍 D。

### Q14.2 Namespace 命名：`/holdings/` vs `/portfolio_tracker/`?

`/portfolio/` 已被 backtest 用。剩餘 :

- `/holdings` — 短、語意精準（持倉）
- `/portfolio_tracker` — 完整但長
- `/journal_v2` — 對齊既有 journal 但語意混淆
- 改 backtest 為 `/portfolio_backtest/`，新 module 佔回 `/portfolio/`（**會 break frontend backtest 既有路由**）

推薦 `/holdings`。

### Q14.3 Live price cache 用 in-memory（`cachetools.TTLCache`）vs Redis?

- in-memory：MVP 簡單，多 worker 不一致
- Redis：可跨 worker，但要處理 connection / serialization

推薦 Phase 1 in-memory，Phase 2+ 視 traffic 升級。

### Q14.4 PATCH 歷史 trade UX 邊界？

允許 PATCH 任意歷史 trade → 整條 lot chain rebuild + realized_pnl 重算。選項：

- **A. 全開放** + audit log
- **B. 只能 PATCH 最近 90 天**
- **C. 只能改 note / tag，price/qty 鎖死**（要改就刪除重建）
- **D. PATCH 觸發 background rebuild job，UI 顯示 pending**

推薦 **A**（完整 immutable event log + rebuild），但 R7 risk 須觀察。

### Q14.5 US 股 live price provider：yfinance 還是 IEX / Polygon / Alpha Vantage?

- **yfinance**：免費，已用於 backfill；unofficial API 易 throttle；無 SLA
- **IEX Cloud / Alpha Vantage**：付費 SaaS，有 SLA；要 API key 設定
- **Polygon.io**：付費，有 free tier

推薦 Phase 1 沿用 yfinance + cache + fallback，Phase 4+ 若 user 量增加再升級付費。

### Q14.6 `app/billing/` 還是 `app/services/billing/` 還是 `app/modules/billing/`?

既有 `app/modules/billing/` 是 Stripe 服務。本 spec 新增 `tier_limits.py` 屬於 cross-cutting 限額：

- **A. `app/billing/`**（與 Stripe 平行）
- **B. `app/services/billing/tier_limits.py`**（歸 services 層）
- **C. `app/modules/billing/tier_limits.py`**（與 stripe_service 同 module）

推薦 **C**（避免新目錄；與 Stripe 共生）。

### Q14.7 Tier guard 「配額型」採宣告式 dependency 還是 explicit service-call?

§9.5 列了兩種：dependency `Depends(tier_guard(feature="..."))` 還是 service 層 `assert_can_create_account(...)`。前者 declarative 但需要拿 path/body param；後者 explicit 但要記得 call。

推薦 **dependency-first + service 層補一層 assertion**（雙保險，避免單一遺漏）。

### Q14.8 既有 `portfolio_snapshots` 表（trade_journal Phase 4 預留）怎麼處置？

新 schema 的 snapshot 表已命名 `holdings_snapshots` 避免衝突。但既有空表佔 namespace，是否 drop？

- **A. 保留**（trade_journal 仍可能用）
- **B. drop**（明確只走新 schema）

推薦 **A**。

---

## 15. Related Files

### 15.1 Existing — will be referenced / reused

| 路徑 | 用途 |
|------|------|
| `backend/app/modules/trade_journal/fifo_engine.py` | **唯一一條跨模組 import**；reuse `FIFOEngine` / `Lot` / `FIFOResult` / `InsufficientSharesError` |
| `backend/app/middleware/tier_guard.py` | 既有 `require_tier(min_tier)`；本 spec 不改，新增 `tier_guard(feature=...)` 並存 |
| `backend/app/auth.py` | `require_auth` dependency（line 78-91） |
| `backend/app/services/audit.py` | `log_audit_event` for portfolio actions |
| `backend/app/models/user.py` | `User.tier` (UserTier enum) |
| `backend/app/models/enums.py` | `UserTier` (FREE/BASIC/PRO) + `Market` (TW_TWSE/TW_TPEX/US_NYSE/US_NASDAQ) |
| `backend/app/models/price.py` | `StockPrice` table — live price daily close source |
| `backend/app/models/stock.py` | `Stock` table — symbol normalization reference |
| `backend/app/models/watchlist_item.py` | user × stock CRUD pattern + FK CASCADE 樣板 |
| `backend/app/models/journal.py:188-198` | `FXRate` table — Phase 2+ 跨幣別折算 |
| `backend/app/config.py` | Pydantic Settings pattern：`UNI_` prefix, `enable_monetization` toggle |
| `backend/app/api/v1/watchlist.py` | endpoint pattern：require_auth + tier check + audit log |
| `backend/app/api/v1/billing.py` | UserTier dispatch pattern (line 111) |
| `backend/app/api/v1/router.py` | router include 處 — 新 routers 在此 mount |
| `backend/app/modules/price_updater/yfinance_provider.py` | US 股 fetch reference；Phase 2 LivePriceFetcher 樣板 |
| `backend/app/modules/price_updater/twse.py` | TW 股 fetch reference |
| `backend/app/modules/price_updater/updater.py:149-169` | retry pattern 樣板 |
| `backend/tests/integration/test_journal_api.py` | integration test 樣板（SQLite + JSONB patch + dep override） |
| `backend/tests/integration/conftest.py` | `pro_user_token` fixture（line 11） |
| `backend/tests/integration/test_watchlist_api.py` | tier guard test 樣板 |
| `backend/tests/unit/test_fifo_engine.py` | T01-T14 parametrize 樣板 |
| `backend/tests/unit/test_tier_guard.py` | tier_guard test 樣板（dep override） |
| `backend/tests/unit/test_rebalance.py` | pure logic test 樣板 |
| `backend/alembic/versions/UNI-WATCH-001_add_watchlist_items.py` | tier-aware migration 樣板 |

### 15.2 Existing — will NOT be touched

| 路徑 | 理由 |
|------|------|
| `backend/app/models/journal.py` | trade_journal schema 整批保留不動（Q3 separate schema） |
| `backend/app/modules/trade_journal/position_sync.py` | schema-coupled，**不 reuse**；新 schema 自己寫 lot/position 同步邏輯 |
| `backend/app/modules/trade_journal/rebalance.py` | 群組再平衡邏輯；Phase 4+ 才考慮 |
| `backend/app/modules/trade_journal/fx_service.py` | Phase 2+ FX 才參考 |
| `backend/app/api/v1/journal.py` | unauthenticated routes 保留（或 Q14.1 隱藏） |
| `backend/app/api/v1/portfolio.py` | portfolio backtest，prefix 已佔；不動 |
| `backend/app/schemas/journal.py` | trade_journal schemas |

### 15.3 New — will be created in Phase 1

| 路徑 | 內容 |
|------|------|
| `backend/alembic/versions/UNI-PORT-001_add_portfolio_tables.py` | 4 tables migration |
| `backend/app/db/models/portfolio/__init__.py` | re-export |
| `backend/app/db/models/portfolio/account.py` | `PortfolioAccount` |
| `backend/app/db/models/portfolio/trade.py` | `PortfolioTrade` |
| `backend/app/db/models/portfolio/lot.py` | `PortfolioLot` |
| `backend/app/db/models/portfolio/position.py` | `PortfolioPosition` |
| `backend/app/modules/portfolio/__init__.py` | re-export |
| `backend/app/modules/portfolio/pnl.py` | pure P&L logic |
| `backend/app/modules/portfolio/cost_basis.py` | wraps FIFOEngine |
| `backend/app/modules/portfolio/live_price_fetcher.py` | Protocol + impls |
| `backend/app/repositories/portfolio/__init__.py` | re-export |
| `backend/app/repositories/portfolio/account_repo.py` | CRUD |
| `backend/app/repositories/portfolio/trade_repo.py` | CRUD |
| `backend/app/repositories/portfolio/lot_repo.py` | CRUD |
| `backend/app/repositories/portfolio/position_repo.py` | CRUD + upsert |
| `backend/app/repositories/portfolio/price_lookup_repo.py` | `stock_prices` read |
| `backend/app/services/portfolio/__init__.py` | re-export |
| `backend/app/services/portfolio/account_service.py` | orchestrate |
| `backend/app/services/portfolio/trade_service.py` | orchestrate + rebuild |
| `backend/app/services/portfolio/position_service.py` | aggregate |
| `backend/app/services/portfolio/summary_service.py` | KPI |
| `backend/app/api/v1/holdings/__init__.py` | router |
| `backend/app/api/v1/holdings/accounts.py` | route |
| `backend/app/api/v1/holdings/trades.py` | route |
| `backend/app/api/v1/holdings/positions.py` | route |
| `backend/app/api/v1/holdings/summary.py` | route |
| `backend/app/schemas/portfolio/__init__.py` | re-export |
| `backend/app/schemas/portfolio/account.py` | Pydantic DTO |
| `backend/app/schemas/portfolio/trade.py` | Pydantic DTO |
| `backend/app/schemas/portfolio/position.py` | Pydantic DTO |
| `backend/app/schemas/portfolio/summary.py` | Pydantic DTO |
| `backend/app/modules/billing/tier_limits.py`（或 `app/billing/` per Q14.6） | YAML loader + Pydantic + lru_cache + `tier_guard(feature=...)` factory |
| `config/tier_limits.yaml` | tier 配額表 |
| `backend/tests/unit/modules/portfolio/test_pnl.py` | ~18 cases |
| `backend/tests/unit/modules/portfolio/test_cost_basis.py` | ~8 cases |
| `backend/tests/unit/modules/portfolio/test_live_price_fetcher.py` | ~4 cases |
| `backend/tests/integration/test_holdings_repo.py` | ~20 cases |
| `backend/tests/integration/test_holdings_api.py` | ~20 cases |
| `backend/tests/integration/test_holdings_tier_guard.py` | ~4 cases |
| `backend/tests/contract/test_yfinance_contract.py` | snapshot test |
| `docs/superpowers/plans/2026-05-XX-portfolio-tracker-backend.md` | Phase 1+2 backend plan（plan 階段拆解） |
| `docs/superpowers/plans/2026-05-XX-portfolio-tracker-frontend.md` | Phase 3 frontend plan |

---

## Appendix A. Architecture trade-offs cheat sheet

| 議題 | Picked | Trade-off |
|------|--------|-----------|
| Schema 策略 | separate schema | + 乾淨邊界；− 多一套 model 維護 |
| Namespace | `/holdings`（暫定） | + 短；− 與 `journal` 並存可能混淆 |
| Cost basis 演算法 | FIFO（reuse FIFOEngine） | + 已測過；台股稅務通用；− 美股 IRS 允許 LIFO/specific lot，未來可能補 |
| 資產增益 (Q6) | simple gain（current holdings only） | + 直覺易懂；− 補倉/抽資金時不反映 |
| Live price MVP | DailyCloseLivePriceFetcher（DB read） | + 零外部依賴；− 非真 intraday |
| Live price cache | in-memory TTL | + 簡單；− 多 worker 不一致 |
| Tier guard 配額 | YAML + Pydantic + lru_cache | + 改 limit 不重啟 worker（restart 即可）；− 真要熱 reload 還需做 |
| Schemas 拆檔 | 一檔一 table | + grep 友善；− 檔案多 |
| User isolation | 結構性強制（service signature 第一個固定 user_id） | + 無法在 architecture 漏 filter；− boilerplate 多一個 param |
| PATCH/DELETE trade | 開放 + full rebuild | + 真 immutable event sourcing；− 大 account rebuild 慢 |
| 跨模組 import | 只 `fifo_engine` | + 邊界最乾淨；− 不能 reuse `position_sync` |

---

## Appendix B. 與 2026-05-20 早期 draft 的關鍵差異

| 項目 | 早期 draft（inherit-and-extend） | 本 spec（separate schema + architecture） |
|------|--------------------------------|-----------------------------------------|
| Schema 策略 | 沿用 `app/models/journal.py` + 加 `user_id` 欄位 | 全新 `portfolio_*` 6 張表 |
| Migration | 加欄位需 backfill 既有 5 row dev data | 純建表，零 backfill 風險 |
| Namespace | `/api/v1/journal/*` | `/api/v1/holdings/*`（避開 backtest 佔用） |
| 跨模組 import | `fifo_engine` + `position_sync` | **僅** `fifo_engine`（pure） |
| 模組分層 | 隱含（沿用既有 modules/api 結構） | **顯式 5 層**（api / service / domain / repo / data） |
| Tier guard | `FREE_TIER_LIMIT = 10` 常數 | **YAML + Pydantic + lru_cache**（Q4 已敲定） |
| Architecture diagram | 無 | ASCII 全圖 + 依賴方向標註 |
| Anti-coupling rules | 無 | 6 條 hard constraints + 違反後果 |
| Extensibility hooks | "Phase 4+ backlog" 一行 | 5 個 extension points + interface stub |
| Testing strategy | 一段話 | 5 個 test type + ~75 cases inventory + fixtures |
| Risk inventory | 無 | 8 risks + mitigations |
| Open questions | 9 個（多為已敲定的 Q1-Q6） | 8 個（聚焦剩餘未拍板） |
| Trade-off 標註 | 少數 | 每節含 trade-off 表 |
| 行數 | 494 | ~ 900 |
