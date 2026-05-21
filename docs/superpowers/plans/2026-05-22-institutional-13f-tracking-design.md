# Institutional 13F Holdings Tracker — Architecture & Design (Uni-Seeker)

**日期：** 2026-05-22 (檔名鎖定為 Stanley 指定 spec date；本次 spec 撰寫於 2026-05-19)
**作者：** System Architect
**範疇：** 「機構/名人 13F 持倉追蹤」backend module 架構設計（Uni-Seeker namespace）；spec only，不生成 `.py` / migration / yaml

---

## 1. Status

Spec draft 2026-05-22。**Awaiting Stanley 拍板 §10 open questions**（至少 Q1/Q2/Q3/Q5/Q8 必須先答，才能進 plan 階段）。

**Trigger：** Stanley 想追特定 filer（example: Leopold Aschenbrenner / Situational Awareness LP — SALP，2024 Q4 AUM $255M → 2025 Q4 $5.5B → options 名義 $13.67B）的 13F 季度持倉異動，整合進 Uni-Seeker。

**敲定立場（不重新討論）：**

| 決策 | 內容 | 來源 |
|------|------|------|
| 命名 / namespace | Uni-Seeker 自建 module，**不**走 smart_money collector | Stanley「把這功能做到 Uni-Seeker」 |
| 架構樣板 | 5-layer（api / service / domain / repo / data）+ tier guard 雙保險，對齊 `2026-05-20-portfolio-tracker-design.md` | Spec 設計慣例 |
| 13F flavour | Phase 1 只接 13F-HR（含 amendments）。13F-NT、13D、13G、Form 4 排 backlog | §2 |
| 共用設施 | Stock 模型 `app/models/stock.py` 不動，須**新增** `cusip` 欄位 + index（migration 內處理；見 §4.5） | §4 |

---

## 2. Problem & Scope

### 2.1 In scope

- 註冊 / 取消 watchlist of filer（例: SALP, Berkshire Hathaway, Renaissance Technologies, ARK Invest）
- 顯示 filer 最新 13F snapshot（持倉清單 + market value + share count + 名義 options）
- **Quarter-over-quarter diff**：NEW / INCREASED / DECREASED / EXITED / UNCHANGED
- 為個股提供「institutional ownership panel」聚合視角（哪些 filer 持有此股 + 最近一季 delta）
- On-demand refresh endpoint（user 觸發；rate-limited）

### 2.2 Out of scope（明確排除，Phase 4+ backlog）

- Real-time 13D / 13G filings（活動主義 / 大股東）
- Form 4 insider transactions（smart_money 已有 `SecEdgarCollector` 處理）
- 全球 / 非 US filings（13F 是 SEC-specific）
- Options 細節破口（Phase 1 只標 `put_call` flag；不算 delta / 名義金額拆解）
- Filer 之間 social graph / cross-holding 分析
- Notification（TG bot / email）— 等 Phase 2+

### 2.3 跟 smart_money 既有 `SecEdgarCollector` 的關係

**Pre-reading 結論：** smart_money 的 `smart_money/collectors/sec_edgar_collector.py` 已實作 Form 4（insider transactions），輸出 `SmartMoneyEvent`（actor_type=INSIDER），走自己的 Parquet + Postgres 雙寫管線（`base_collector.py:32-35`）。13F-HR 與 Form 4 雖然同 EDGAR 平台，但是：

| 維度 | Form 4 (smart_money) | 13F-HR (本 spec) |
|------|---------------------|------------------|
| 語意 | per-transaction event | quarter-end snapshot |
| Cadence | 2 business days after trade | 45 days after quarter end |
| Schema | `SmartMoneyEvent`（單筆 BUY/SELL） | filer + filing + per-position row（snapshot） |
| Output | smart_money DB + Parquet（90d hot + cold） | Uni-Seeker Postgres（operational, query 友善） |
| Tier-gated | No（research pipeline） | **Yes**（user-facing feature） |
| 服務對象 | Adaptive Alpha Engine feature store | Uni-Seeker 前端 user |

**架構選擇分析：**

- **Option A — 共用 smart_money collector：** 加 `sec_13f_collector.py` 進 smart_money/collectors/，data 流 smart_money DB，Uni-Seeker 反向 query。優點：DRY、collector pattern 一致。缺點：(a) `SmartMoneyEvent` schema 撐不下 snapshot 語意（actor=filer, action=hold? 牽強）；(b) Uni-Seeker → smart_money cross-service query 違反 bounded context；(c) tier guard / user subscription 邏輯只能寫在 Uni-Seeker，會出現 dual-DB join 的尷尬。
- **Option B — Uni-Seeker 自建（採用）：** 邏輯重複（EDGAR HTTP client + XML parser），但 ownership boundary 乾淨；schema 為 13F 量身打造；不依賴跨 service consistency。

**結論：採 Option B。** 共享只到「設計樣板與經驗」層，不到 code import。smart_money `SecEdgarCollector` 的 `requests + BeautifulSoup + ZoneInfo("America/New_York")` 設計（line 26-45）是有用的 reference，**但 Uni-Seeker 改用 `httpx async` 對齊 backend 既有風格**（如 `app/modules/price_updater/yfinance_provider.py`）。

---

## 3. Data Source

### 3.1 SEC EDGAR

| 屬性 | 值 |
|------|------|
| Auth | 無 |
| Rate limit | 10 req/sec（SEC fair-use policy） |
| Required header | `User-Agent: Uni-Seeker stanly7768@gmail.com`（Stanley 的 contact email） |
| Format | XML（primary_doc.xml + infotable.xml） |
| Latency | Filing 通常 quarter-end + 30~45 day 出現 |

### 3.2 關鍵 endpoints

| 用途 | URL pattern |
|------|------------|
| Filer index (submissions metadata) | `https://data.sec.gov/submissions/CIK{cik_10digit_padded}.json` |
| 13F filing list (search by form) | `https://efts.sec.gov/LATEST/search-index?q=&forms=13F-HR&ciks={cik}` |
| Filing detail page | `https://www.sec.gov/cgi-bin/browse-edgar?action=getcompany&CIK={cik}&type=13F-HR` |
| Primary doc | `https://www.sec.gov/Archives/edgar/data/{cik_int}/{accession_nodash}/primary_doc.xml` |
| Holdings table | `https://www.sec.gov/Archives/edgar/data/{cik_int}/{accession_nodash}/infotable.xml` |

### 3.3 13F-HR `infoTable` row schema（XML → 內部欄位）

| XML element | 內部欄位 | 備註 |
|-------------|---------|------|
| `nameOfIssuer` | `name_of_issuer` (str) | 公司名（free text，SEC 不正規化） |
| `cusip` | `cusip` (str, 9-char) | 美股股票識別 |
| `value` | `value_usd` (Decimal) | **單位 = 1000 USD**（×1000 後存） |
| `shrsOrPrnAmt/sshPrnamt` | `shares_or_principal` (Decimal) | 數量 |
| `shrsOrPrnAmt/sshPrnamtType` | `quantity_type` (str) | `SH` (shares) / `PRN` (principal amt) |
| `putCall` | `put_call` (str \| null) | `PUT` / `CALL` / 空（純股票） |
| `investmentDiscretion` | `investment_discretion` (str) | `SOLE` / `SHARED` / `NONE` |
| `votingAuthority/{sole,shared,none}` | `voting_*` (Decimal) | 三個欄位 |

**Edge cases：**

- 同一 filer 同 cusip 可出現 **多 row**（例: 一行純股票 + 一行 CALL option）→ schema 用 `(filing_id, cusip, put_call)` natural composite key 區分
- `value` 為 0（filer 在 13F 報告期間 exit but 還沒 quit 報告） → 視同 0-position
- `infotable.xml` 在較舊 filing（pre-2013）可能是 HTML table 而非 XML → Phase 1 限 2013 之後 filing；舊資料 Phase 2 補

### 3.4 CUSIP → Stock symbol mapping

13F 用 9-char CUSIP（不含 check digit 也常見 8-char），Uni-Seeker 內部用 `symbol`。**Phase 1 採 lazy lookup：**

1. 從 13F infotable 拿 cusip
2. 試 `Stock.cusip == cusip`（須新增此欄位，見 §4.5）
3. 若無命中 → `holding.stock_id = null` + 標 `unmapped_cusip = true`，仍寫入 row（不丟資料）
4. Phase 2 加 batch mapping refresh job（資料源候選：OpenFIGI free tier / SEC `company_tickers.json` + CIK→CUSIP 反查）

**為什麼不在 Phase 1 強 mapping：** SEC 沒有官方 CUSIP→ticker 對應 dump；OpenFIGI 雖免費但有 25 req/min limit；先把 raw data 抓回來，UI 在 unmapped row 顯示 cusip + nameOfIssuer 也可用。

---

## 4. Data Model

### 4.1 Naming convention

所有新表 prefix `f13_`（form 13 縮寫），與既有 `portfolio_*` / `watchlist_*` / `journal_*` 並列。

### 4.2 Migration ID

**`UNI-F13-001_add_institutional_13f_tables.py`**

Pre-reading 確認既有 alembic head 為 `UNI-PORT-003_add_holdings_snapshots.py`（已 applied）。本 migration 以 `UNI-PORT-003` 為 `down_revision`。

### 4.3 Tables（4 張 + 1 schema patch）

#### Table 1: `f13_filers` — 機構 / 名人 identity

| Column | Type | Constraint |
|--------|------|-----------|
| `id` | `BigInteger` | PK |
| `cik` | `String(10)` | NOT NULL, **UNIQUE**, INDEX — 10-digit zero-padded |
| `name` | `String(200)` | NOT NULL — short display name (e.g. "Situational Awareness LP") |
| `legal_name` | `String(300)` | NOT NULL — SEC 登錄全名 (e.g. "SITUATIONAL AWARENESS LP") |
| `aum_usd_self_reported` | `Numeric(20, 2)` | nullable — 由 filer 主動填 (§10 Q3) |
| `latest_filing_id` | `BigInteger` | FK `f13_filings.id` ON DELETE SET NULL, nullable, indexed |
| `created_at` | `DateTime(tz=True)` | server_default=now() |
| `updated_at` | `DateTime(tz=True)` | server_default=now(), onupdate=now() |

**註：** `f13_filers` 不掛 `user_id` — filer 是 **共享資源**（10 個 user 追同一個 SALP，filer row 只有一份）。user-filer 關係走 `f13_user_subscriptions` (Table 2)。

Index: `ix_f13_filers_cik` (already unique), `ix_f13_filers_name_trgm`（pg_trgm fuzzy search，若 Postgres 已有 extension，否則 Phase 2 再加）

#### Table 2: `f13_user_subscriptions` — user watchlist

| Column | Type | Constraint |
|--------|------|-----------|
| `id` | `BigInteger` | PK |
| `user_id` | `BigInteger` | FK `users.id` ON DELETE CASCADE, NOT NULL, INDEX |
| `filer_id` | `BigInteger` | FK `f13_filers.id` ON DELETE CASCADE, NOT NULL, INDEX |
| `notify_on_new_filing` | `Boolean` | NOT NULL, default `true` |
| `user_alias` | `String(100)` | nullable — 使用者自定 alias (§10 Q7) |
| `subscribed_at` | `DateTime(tz=True)` | server_default=now() |

Unique: `uq_f13_user_subscriptions(user_id, filer_id)`

#### Table 3: `f13_filings` — 季度 snapshot meta

| Column | Type | Constraint |
|--------|------|-----------|
| `id` | `BigInteger` | PK |
| `filer_id` | `BigInteger` | FK `f13_filers.id` ON DELETE CASCADE, NOT NULL, INDEX |
| `accession_number` | `String(20)` | NOT NULL — SEC unique (e.g. "0001234567-25-012345") |
| `form_type` | `String(10)` | NOT NULL — `13F-HR` / `13F-HR/A` (amendment) / `13F-NT` |
| `report_period_end` | `Date` | NOT NULL — quarter end (e.g. 2025-12-31) |
| `filed_at` | `DateTime(tz=True)` | NOT NULL |
| `total_value_usd` | `Numeric(20, 2)` | nullable — Σ(value × 1000) |
| `total_positions` | `Integer` | nullable |
| `options_notional_usd` | `Numeric(20, 2)` | nullable — Σ over put_call ≠ null |
| `raw_xml_url` | `String(500)` | nullable — infotable.xml URL |
| `ingested_at` | `DateTime(tz=True)` | server_default=now() |
| `created_at` | `DateTime(tz=True)` | server_default=now() |

Unique: `uq_f13_filings_accession(filer_id, accession_number)`
Index: `ix_f13_filings_period_desc(filer_id, report_period_end DESC)` — 加速 latest filing query

#### Table 4: `f13_holdings` — per-position rows

| Column | Type | Constraint |
|--------|------|-----------|
| `id` | `BigInteger` | PK |
| `filing_id` | `BigInteger` | FK `f13_filings.id` ON DELETE CASCADE, NOT NULL, INDEX |
| `cusip` | `String(9)` | NOT NULL, INDEX |
| `name_of_issuer` | `String(200)` | NOT NULL |
| `value_usd` | `Numeric(20, 2)` | NOT NULL — `value × 1000` |
| `shares_or_principal` | `Numeric(24, 4)` | NOT NULL |
| `quantity_type` | `String(3)` | NOT NULL — `SH` / `PRN` |
| `put_call` | `String(4)` | nullable — `PUT` / `CALL` / null |
| `investment_discretion` | `String(10)` | NOT NULL |
| `voting_sole` | `Numeric(24, 4)` | default 0 |
| `voting_shared` | `Numeric(24, 4)` | default 0 |
| `voting_none` | `Numeric(24, 4)` | default 0 |
| `stock_id` | `BigInteger` | FK `stocks.id` ON DELETE SET NULL, nullable, INDEX (partial: WHERE stock_id IS NOT NULL) |

Unique: `uq_f13_holdings_position(filing_id, cusip, put_call)` — 同 filing 同 cusip 同 put/call 不可重複，但允許「2330.TW 純股票 + CALL option」共存

Index: `ix_f13_holdings_cusip(cusip)`（cross-filing query「哪些 filer 持有此 CUSIP」），`ix_f13_holdings_stock_id` partial

### 4.4 FK ON DELETE 行為

- `subscriptions.user_id → users.id` CASCADE — user 帳號刪除 → subscription 隨之
- `subscriptions.filer_id → filers.id` CASCADE — filer 不會被刪（無 UI delete 路徑），但 migration safety
- `filings.filer_id → filers.id` CASCADE
- `holdings.filing_id → filings.id` CASCADE — 重新 ingest 同 filing 時可整批清除重灌
- `holdings.stock_id → stocks.id` SET NULL — stock 變 inactive 不該破壞歷史 13F 記錄

### 4.5 既有 `stocks` 表的 schema patch

**`stocks` 需新增：**

| Column | Type | Constraint |
|--------|------|-----------|
| `cusip` | `String(9)` | nullable, INDEX |

理由：

- 同 migration `UNI-F13-001` 內 `ALTER TABLE stocks ADD COLUMN cusip VARCHAR(9)` + index
- 此欄位**已是 portfolio / watchlist module 也會用到的 universal identifier**（不算為 13F 專屬污染）
- Phase 1 不 backfill（lazy lookup 容忍 null）

對既有 portfolio / watchlist code 影響：**zero**（純加欄位、無 NOT NULL constraint）。

---

## 5. Architectural Layering

完全對齊 `2026-05-20-portfolio-tracker-design.md` §4 的 5-layer：

```
┌──────────────────────────────────────────────────────────────────────────┐
│                           HTTP / FastAPI Layer                            │
│  app/api/v1/institutional/                                                │
│    ├─ filers.py        (POST/GET/DELETE filers + search)                  │
│    ├─ filings.py       (GET filer's filings + holdings)                   │
│    ├─ diff.py          (GET quarter-over-quarter diff)                    │
│    ├─ stock_view.py    (GET /stocks/{symbol}/institutional)               │
│    └─ refresh.py       (POST /filers/{id}/refresh)                        │
│                                                                           │
│  All: Depends(require_auth) + Depends(tier_guard(...))                    │
└────────────────────────────────────┬──────────────────────────────────────┘
                                     ▼ (Pydantic schemas in
                                        app/schemas/institutional/)
┌──────────────────────────────────────────────────────────────────────────┐
│                       Service Layer (orchestration)                       │
│  app/services/institutional/                                              │
│    ├─ filer_service.py     (subscribe / unsubscribe / search)             │
│    ├─ filing_service.py    (list filings, ingest, persist holdings)       │
│    ├─ diff_service.py      (compute QoQ diff for a filer)                 │
│    ├─ stock_view_service.py (aggregate filer holdings by stock)           │
│    └─ refresh_service.py   (orchestrate EDGAR fetch + parse + persist)    │
└──────────┬──────────────────────────────────────────┬────────────────────┘
           ▼                                          ▼
┌──────────────────────────────────┐  ┌──────────────────────────────────────┐
│  Domain Logic Layer (PURE)        │  │  Repository Layer                     │
│  app/modules/institutional/       │  │  app/repositories/institutional/      │
│    ├─ edgar_client.py             │  │    ├─ filer_repo.py                   │
│    │   (httpx wrapper +           │  │    ├─ subscription_repo.py            │
│    │    User-Agent + rate limit)  │  │    ├─ filing_repo.py                  │
│    ├─ xml_parser.py (infotable)   │  │    └─ holding_repo.py                 │
│    ├─ diff_engine.py              │  │                                       │
│    ├─ cusip_normalizer.py         │  │  Rule: 純 CRUD + query                │
│    └─ models.py (dataclass)       │  │       無 business logic               │
│                                   │  └──────────────────────────────────────┘
│  Rule: edgar_client 為 I/O，                              │
│       其餘 modules 純函數 / dataclass                      ▼
└───────────────────────────────────┘    ┌─────────────────────────────────┐
                                         │   Data Layer (DB)                │
                                         │   app/db/models/institutional/   │
                                         │   (filer/subscription/filing/    │
                                         │   holding ORM)                   │
                                         └─────────────────────────────────┘
```

**依賴方向（strictly inward，與 portfolio spec §4 R1–R6 一致）：**

- `api → services → {domain, repository}` 允許
- `services → domain` / `services → repository` 允許
- `domain.edgar_client → httpx`（唯一允許 I/O 的 domain submodule，因為 SEC API 是純粹的外部介面，沒道理拉進 service 層；但 **不允許 import sqlalchemy / fastapi**）
- `domain.{xml_parser, diff_engine, cusip_normalizer, models}` MUST NOT import 任何 I/O（zero side effect）
- `repository ↛ services / domain`（repo 純 CRUD）
- `schemas ↛ services / domain / models`（DTO only）
- `api ↛ db.models` 直接 query（必須走 repo）

---

## 6. Module Breakdown

### 6.1 `app/modules/institutional/` — Domain logic

| File | Responsibility | 對外 surface |
|------|---------------|------------|
| `models.py` | Pure dataclass — `FilerMeta`, `FilingMeta`, `HoldingRow`, `HoldingChange`, `DiffSummary` | dataclass exports |
| `edgar_client.py` | httpx AsyncClient wrapper + User-Agent + token bucket rate limit (10 req/s) + retry (3x exp backoff) | `EdgarClient.fetch_filer(cik)`, `fetch_filing_list(cik)`, `fetch_infotable_xml(url)` |
| `xml_parser.py` | Parse `infotable.xml` → `list[HoldingRow]`; lxml-based；handle namespace `ns1:` 變體 | `parse_infotable(xml_bytes) -> list[HoldingRow]`, `parse_primary_doc(xml_bytes) -> FilingMeta` |
| `diff_engine.py` | Pure function — compute QoQ diff between two filings | `compute_diff(prev: list[HoldingRow], curr: list[HoldingRow]) -> list[HoldingChange]` |
| `cusip_normalizer.py` | Strip / pad CUSIP, validate check digit | `normalize_cusip(raw: str) -> str` |

**`edgar_client.py` 內部結構：**

```
class EdgarClient:
    def __init__(self, user_agent: str, rate_limit_per_sec: int = 10):
        self._client = httpx.AsyncClient(headers={"User-Agent": user_agent})
        self._bucket = TokenBucket(rate_limit_per_sec)

    async def fetch_filer(self, cik: str) -> FilerMeta:
        await self._bucket.acquire()
        # GET data.sec.gov/submissions/CIK{padded}.json
        # parse: name, sic, addresses, recent filings

    async def fetch_filing_list(self, cik: str, form: str = "13F-HR") -> list[FilingRef]: ...
    async def fetch_infotable_xml(self, archive_url: str) -> bytes: ...
    async def search_filers(self, query: str) -> list[FilerSearchResult]:
        # GET efts.sec.gov/LATEST/search-index?q=...
        ...
```

### 6.2 `app/services/institutional/` — Orchestration

| File | Responsibility |
|------|---------------|
| `filer_service.py` | `subscribe(user_id, cik)` → fetch_filer(cik) if not exists → insert filer row → insert subscription. `list_subscriptions(user_id)`, `unsubscribe(user_id, filer_id)`, `search_filers(query)` (proxy to EDGAR search) |
| `filing_service.py` | `list_filings(user_id, filer_id, paginated)`, `get_holdings(user_id, filer_id, period)` |
| `diff_service.py` | `compute_qoq_diff(user_id, filer_id, from_date, to_date)` — load prev + curr filings via repo → call `diff_engine.compute_diff` |
| `stock_view_service.py` | `list_filers_holding_stock(user_id, symbol)` — query `f13_holdings` JOIN `stocks` JOIN `f13_filings` JOIN `f13_filers` |
| `refresh_service.py` | `refresh_filer(user_id, filer_id)` — fetch new filings since last ingested → parse → upsert filings + holdings → trigger CUSIP→stock_id lazy mapping |

**Rule：** Service 第一個參數 always `user_id`，repo query 必先 join subscription 驗證 ownership（同 portfolio spec G2）。例外：`f13_filers` / `f13_filings` / `f13_holdings` 本身是公開資料，但**「user 是否 subscribed」決定他能否看到 deep data**（free user 看不到非自己訂的 filer detail）。

### 6.3 `app/repositories/institutional/` — DB only

| File | Tables touched |
|------|----------------|
| `filer_repo.py` | `f13_filers` |
| `subscription_repo.py` | `f13_user_subscriptions` |
| `filing_repo.py` | `f13_filings` |
| `holding_repo.py` | `f13_holdings` |

### 6.4 `app/api/v1/institutional/` — HTTP

**Prefix：** `/api/v1/institutional/`（建議；待 §10 Q6 拍板，備選 `/api/v1/f13/`）

| File | Routes |
|------|--------|
| `filers.py` | `POST /institutional/filers` (subscribe by CIK), `GET /institutional/filers` (list mine), `GET /institutional/filers/{filer_id}`, `DELETE /institutional/filers/{filer_id}` (unsubscribe), `GET /institutional/filers/search?q=...` |
| `filings.py` | `GET /institutional/filers/{filer_id}/filings`, `GET /institutional/filers/{filer_id}/holdings?period=latest\|<date>` |
| `diff.py` | `GET /institutional/filers/{filer_id}/diff?from=<date>&to=<date>` |
| `stock_view.py` | `GET /institutional/stocks/{symbol}/holders`, `GET /institutional/stocks/{symbol}/recent-changes` |
| `refresh.py` | `POST /institutional/filers/{filer_id}/refresh` (rate-limited per filer per hour) |

### 6.5 `app/db/models/institutional/` — ORM

一檔一 model（對齊 portfolio spec §5.5 推薦）：

- `filer.py` → `F13Filer`
- `subscription.py` → `F13UserSubscription`
- `filing.py` → `F13Filing`
- `holding.py` → `F13Holding`

### 6.6 `app/schemas/institutional/` — Pydantic DTO

- `filer.py` → `FilerCreateRequest`, `FilerResponse`, `FilerSearchResult`
- `filing.py` → `FilingResponse`, `HoldingResponse`
- `diff.py` → `HoldingChangeResponse`, `DiffSummaryResponse`
- `stock_view.py` → `StockHolderResponse`

---

## 7. Domain Logic Specs

### 7.1 13F XML parser

```
def parse_infotable(xml_bytes: bytes) -> list[HoldingRow]:
    """
    Parse SEC infotable.xml → list[HoldingRow].

    XML namespace 變體：
      - "ns1:infoTable" (常見)
      - 無 namespace (純 <infoTable>)
      - "n1:infoTable"

    使用 lxml 的 local-name() XPath 避開 namespace 不一致。

    Edge cases:
      - 缺 cusip / value → skip row + log warning
      - value 不是數字 → skip row
      - sshPrnamtType ∉ {"SH","PRN"} → 仍接受，但標 warning
      - putCall 為空字串 → 視為 None（純股票）
    """
```

### 7.2 Diff engine

```
@dataclass(frozen=True)
class HoldingChange:
    cusip: str
    name_of_issuer: str
    stock_id: int | None
    put_call: str | None
    change_type: Literal["NEW", "INCREASED", "DECREASED", "EXITED", "UNCHANGED"]
    prev_shares: Decimal | None     # None if NEW
    curr_shares: Decimal | None     # None if EXITED
    delta_shares: Decimal            # curr - prev (negative for DECREASED/EXITED)
    delta_pct: Decimal | None        # None if NEW or EXITED
    prev_value_usd: Decimal | None
    curr_value_usd: Decimal | None
    delta_value_usd: Decimal

def compute_diff(
    prev_holdings: list[HoldingRow],
    curr_holdings: list[HoldingRow],
) -> list[HoldingChange]:
    """
    Key by (cusip, put_call).
    Threshold for UNCHANGED: |delta_shares / prev_shares| < 0.5%
    （避免 share buyback / minor adjustment 觸發誤報；可配置）
    """
```

### 7.3 EDGAR client wrapper — rate limit 策略

- Token bucket（10 token/sec, burst=10）
- 5xx → exponential backoff（1s, 2s, 4s, 上限 3 次）
- 429 → respect `Retry-After` header
- 連續 3 次失敗 → raise `EdgarTransientError`（service 層 retry 或 fail user request 503）

User-Agent 須讀 `settings.edgar_user_agent`（新增 config，default `"Uni-Seeker stanly7768@gmail.com"`）— SEC 要求 contact info，否則回 403。

---

## 8. Tier Guard Proposal

對齊既有 `app/modules/billing/tier_limits.py`（已 spec §9 in portfolio doc）。

### 8.1 `config/tier_limits.yaml` 補欄位

```yaml
free:
  # ... 既有欄位不動 ...
  max_tracked_filers: 1
  features:
    # ... 既有 ...
    institutional_realtime_refresh: false
    institutional_ownership_panel: false

basic:
  max_tracked_filers: 5
  features:
    institutional_realtime_refresh: false
    institutional_ownership_panel: false

pro:
  max_tracked_filers: null  # unlimited
  features:
    institutional_realtime_refresh: true
    institutional_ownership_panel: true
```

### 8.2 Tier guard 套用

| Endpoint | tier_guard |
|----------|-----------|
| `POST /institutional/filers` | `tier_guard(limit_key="max_tracked_filers", current_count_provider=tracked_filers_count_provider)` |
| `POST /institutional/filers/{id}/refresh` | `tier_guard(feature="institutional_realtime_refresh")` — only PRO can on-demand refresh |
| `GET /institutional/stocks/{symbol}/holders` | `tier_guard(feature="institutional_ownership_panel")` |
| `GET /institutional/filers/{id}/holdings` | 無 — 已 subscribed 都能看 |
| `GET /institutional/filers/{id}/diff` | 無 |

**`tracked_filers_count_provider`** 是新 async function，count `f13_user_subscriptions` where `user_id = user.id`。對齊既有 `app/api/v1/holdings/_count_providers.py::account_count_provider` pattern。

### 8.3 Cache TTL（refresh 結果）

| Tier | Refresh 最低間隔 |
|------|----------------|
| FREE | 30 day（最近一筆 cached filing；不主動 fetch） |
| BASIC | 7 day |
| PRO | 1 day + on-demand `POST /refresh` |

由 `refresh_service` 在 fetch 前檢查 `f13_filings.ingested_at` 距 now < threshold → 直接回 cached，不打 EDGAR。

---

## 9. Rollout Plan

### Phase 1 — MVP backend（est. 3–4h）

**交付物：**

- Migration `UNI-F13-001`（4 tables + stocks.cusip patch）
- 4 ORM models in `app/db/models/institutional/`
- 5 modules in `app/modules/institutional/`（models / edgar_client / xml_parser / diff_engine / cusip_normalizer）
- 5 services in `app/services/institutional/`
- 4 repos in `app/repositories/institutional/`
- 5 API endpoint files in `app/api/v1/institutional/`
- 4 Pydantic schemas in `app/schemas/institutional/`
- `config/tier_limits.yaml` 補欄位 + `tier_limits.py` Pydantic schema 加 `max_tracked_filers` + 2 features
- Refresh: **on-demand only**, no scheduler
- Tests: ~50 cases（pure parser/diff ~15 + repo CRUD ~12 + tier guard ~6 + API smoke ~12 + EDGAR contract ~5）

**Acceptance criteria：**

- AC1. User A `POST /institutional/filers {cik:"0002048840"}` (SALP) → 201, fetch fills `f13_filers.name` from SEC
- AC2. `POST /filers/{id}/refresh` 拉最新 13F-HR XML → 寫 `f13_filings` + `f13_holdings`（SALP 2025-Q4 範例 ≥ 30 positions）
- AC3. `GET /filers/{id}/diff?from=2025-09-30&to=2025-12-31` 回傳 diff list 含 NEW/EXITED/INCREASED/DECREASED
- AC4. FREE user 試訂第 2 個 filer → 403 `limit_exceeded:max_tracked_filers`
- AC5. FREE user 試 PRO-only refresh → 403 `feature_unavailable:institutional_realtime_refresh`
- AC6. CUSIP 已存在 `stocks.cusip` → `holding.stock_id` 填；不存在 → null（不丟資料）
- AC7. User B 看不到 User A 的 subscription（404 / 403）

**估時合理性檢查：** 對照 portfolio Phase 1（est. 2 days = 16h，實際結果在 daily-task 紀錄）— 13F 邏輯比 portfolio 簡單很多（無 FIFO / 無 P&L / 無 live price）但多了 XML parser + EDGAR client。3–4h **僅當 Stanley 的 4 個關鍵 open question 已先答**，否則 plan + implementation 會反覆。**保守估 6–8h 較實際**。

### Phase 2 — Scheduler + frontend（est. 4–6h）

- APScheduler job `refresh_active_subscriptions` daily（for PRO） / weekly（for BASIC）
- CUSIP → symbol mapping job (OpenFIGI / SEC `company_tickers.json`)
- Frontend `frontend/app/institutional/` page (filer list + holdings table + diff view，STRATOS primitives)

### Phase 3+ backlog

- Per-stock institutional panel integration to `/stocks/{symbol}` page (Pro)
- Notifications on new filing (TG bot)
- Options 期權 delta / 名義金額 breakdown
- 13D / 13G filing types
- AUM growth chart
- Popular filer discovery page（top 100 by AUM, etc.）

---

## 10. Open Questions（待 Stanley 拍板）

### Top 5（plan 階段前必答）

1. **Q1 — Filing refresh strategy**：Phase 1 採 **on-demand only**（user 點 refresh 才打 EDGAR）；Phase 2 上 scheduler（daily/weekly per tier）。OK 嗎？或一上來就要 scheduler？
2. **Q2 — Filer 共享 vs per-user**：`f13_filers` 設計為**共享資源**（10 user 追同一 SALP 只一份 row），這與 portfolio 的 user-scoped 設計**相反**。但符合 13F 本質（filer 是公開的）。是否同意此 trade-off？
3. **Q3 — AUM 顯示**：13F 只報 **long-only US equities**，不含 cash / bonds / non-US / shorts。SALP 報的 $5.5B 是 13F market value，$13.67B 是含 options 名義。要顯示哪個？(a) 純 13F long total / (b) 13F + options notional / (c) 三個都顯示（推薦） / (d) 用 self-reported AUM 欄位讓 filer 主動填？
4. **Q5 — Tier 數字**：FREE 1 / BASIC 5 / PRO unlimited 合理嗎？Stanley 自己會用 PRO，朋友試用大概什麼比例？
5. **Q8 — 歷史 backfill 範圍**：Stanley 訂閱 SALP 後，要抓多久的歷史 filing？(a) 只抓 latest 1 季 / (b) 抓 last 4 季（年度比較） / (c) 5 年 / (d) all-time。資料量 trade-off：SALP 才成立不久所以小，但 Berkshire 抓 all-time 會 50+ filing。

### 其他 3 個

6. **Q4 — Filer search 介面**：用 SEC EDGAR full-text search API proxy（即時 hit SEC，每次 ~500ms latency），還是先建本地 popular-filers 表（top 500 by AUM）做 autocomplete？
7. **Q6 — API prefix**：`/api/v1/institutional/`（語意清楚）vs `/api/v1/f13/`（簡短）— 哪個？
8. **Q7 — User alias**：`f13_user_subscriptions.user_alias` 欄位是否要在 Phase 1 開放？例如 Stanley 把 SALP 別名為「Leopold 的基金」。

---

## 11. Risks & Mitigations

| Risk | Impact | Mitigation |
|------|--------|------------|
| **R1. SEC 改 API / 改 XML schema** | Parser 全掛、UI 顯示空 | (a) Contract test on every Phase；(b) `xml_parser` 對 unknown element raise warning 而非 hard fail；(c) raw_xml_url 存著，可手動 reprocess |
| **R2. CUSIP→symbol mapping 命中率低（Phase 1）** | UI 大量 row 顯示 cusip 而非 ticker | (a) 接受並標 unmapped；(b) Phase 2 OpenFIGI 補；(c) UI 顯示 `nameOfIssuer` 仍可讀 |
| **R3. EDGAR rate limit 觸發** | refresh 失敗或慢 | Token bucket 強制 10 req/s；single refresh 通常 < 5 request；不會 burst |
| **R4. 同一 cusip 同 filer 多次 ingest 重複插入** | Holding row 暴增 | `uq_f13_filings_accession` + `uq_f13_holdings_position` 保護；refresh 採 upsert pattern（DELETE filing CASCADE → re-INSERT），符合 13F snapshot 語意 |
| **R5. SALP CIK 找不到 / Leopold 沒登錄成 fund**（具體案例風險） | Stanley 第一個 user story 就掛 | **Phase 1 開工前**請 Stanley 先在 https://efts.sec.gov/LATEST/search-index?q=situational+awareness&forms=13F-HR 驗證 SALP CIK 存在；本 spec 假設 CIK = 0002048840（需 Stanley 驗） |
| **R6. 13F-HR/A amendment 處理** | Amendment 是「整份重發」，若不處理會雙倉 | refresh 邏輯：以 (filer_id, report_period_end) 為 logical key，新 accession → DELETE 舊 filing CASCADE → INSERT 新 filing + holdings。`form_type` 欄位記 `13F-HR/A` |
| **R7. Tier downgrade with > limit filer** | BASIC user 訂了 5 filer 後降 FREE | downgrade 不刪 subscription；後續新增被擋；UI 顯示「您訂閱 5 個 filer 超過 FREE 上限，無法新增」（同 portfolio spec R3 pattern） |
| **R8. 13F filing 太大（Berkshire 千行）** | XML download + parse > 10s | (a) httpx stream download；(b) lxml iterparse 而非 ET.fromstring；(c) refresh service async，不阻塞 HTTP request — 改 background job + status polling endpoint |

**預期 Phase 1 後最大 architecture risk：** **R5 + R6** — 真實 EDGAR XML 的 namespace / amendment / 多 putCall row 三種 edge case 互相疊加時，parser 容錯需要實戰調整。建議 Phase 1 最後安排 **「跑 5 個真實 filer」smoke run**（SALP, Berkshire, Renaissance, ARK, Citadel），用真實資料驗 parser robustness，比 unit test 覆蓋率更實際。

---

## 12. Related Files

### Existing — referenced as design inspiration（NOT imported）

- `/Users/stanley/stanley-project/smart_money/collectors/sec_edgar_collector.py:1-158` — Form 4 collector（reference for User-Agent / EDGAR URL pattern）
- `/Users/stanley/stanley-project/smart_money/collectors/base_collector.py:21-68` — collector ABC pattern（reference only；Uni-Seeker 不繼承）
- `/Users/stanley/stanley-project/smart_money/aggregator/slow_track.py:1-200` — slow track quarterly aggregator pattern（reference for cadence；Uni-Seeker 採 user-triggered + scheduler，不走 DuckDB ATTACH）

### Existing — same project, will reuse via import

- `/Users/stanley/stanley-project/Uni-Seeker/backend/app/modules/billing/tier_limits.py:228` — `tier_guard()` factory（Phase 1 直接 import）
- `/Users/stanley/stanley-project/Uni-Seeker/backend/app/api/v1/holdings/_count_providers.py` — `account_count_provider` 樣板（複製出 `tracked_filers_count_provider`）
- `/Users/stanley/stanley-project/Uni-Seeker/backend/app/auth.py::require_auth` — auth dependency
- `/Users/stanley/stanley-project/Uni-Seeker/backend/app/models/stock.py:10` — `Stock` model（migration 加 `cusip` column）
- `/Users/stanley/stanley-project/Uni-Seeker/config/tier_limits.yaml` — 補 `max_tracked_filers` + 2 features

### Existing — NOT touched

- smart_money/ 全部 collectors / aggregator / db — separate concern
- Existing `/api/v1/holdings/*` 全部 endpoint
- Existing `/api/v1/watchlist/*`, `/api/v1/journal/*`
- Existing `app/models/journal.py`, `app/models/watchlist_item.py`

### New（will be created in Phase 1）

- Migration `UNI-F13-001_add_institutional_13f_tables.py`
- ORM: `app/db/models/institutional/{filer,subscription,filing,holding}.py`
- Domain: `app/modules/institutional/{models,edgar_client,xml_parser,diff_engine,cusip_normalizer}.py`
- Services: `app/services/institutional/{filer,filing,diff,stock_view,refresh}_service.py`
- Repos: `app/repositories/institutional/{filer,subscription,filing,holding}_repo.py`
- API: `app/api/v1/institutional/{filers,filings,diff,stock_view,refresh}.py`
- Schemas: `app/schemas/institutional/{filer,filing,diff,stock_view}.py`
- Tests: `tests/unit/test_13f_parser.py`, `test_13f_diff.py`, `tests/integration/test_13f_repo.py`, `test_13f_api.py`, `tests/contract/test_edgar_client.py`

---

## 13. Decision Log

| Date | Decision | Rationale |
|------|----------|-----------|
| 2026-05-22 | Uni-Seeker 自建 module, 不走 smart_money collector | Stanley 明確指示 + bounded context（§2.3） |
| 2026-05-22 | `f13_filers` 共享資源（無 user_id 欄位） | 13F filer 本質公開；user 關係走 subscription | 
| 2026-05-22 | Prefix `/api/v1/institutional/`（建議） | 語意明確；備選 `/f13/` 留 Stanley 拍板 |
| 2026-05-22 | Migration ID `UNI-F13-001`，down_revision = `UNI-PORT-003` | Verified alembic head |
| 2026-05-22 | `stocks` 表加 `cusip` column（universal identifier） | 不算為 13F 專屬污染；portfolio/watchlist 未來也會用 |
| 2026-05-22 | Phase 1 refresh **on-demand only**, no scheduler | 縮小 surface area；scheduler Phase 2（待 Q1） |
| 2026-05-22 | CUSIP→symbol Phase 1 lazy lookup（容忍 null） | 沒官方 dump；OpenFIGI 限額；不阻塞 ingest |
| 2026-05-22 | XML parser 用 lxml + local-name() XPath | SEC namespace 變體；ET.fromstring 不夠強健 |
| 2026-05-22 | EDGAR client async (httpx) | 對齊 backend 既有 async 風格；smart_money 用 requests 是不同 service |
