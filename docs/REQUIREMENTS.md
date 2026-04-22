# Uni-Seeker 需求規格文件

> 版本：1.0 | 日期：2026-04-22 | 狀態：Draft

---

## 1. 專案概述

Uni-Seeker 是一套**台美股分析平台**，提供股價追蹤、技術指標計算、財報分析、投資策略回測與到價通知等功能。系統採模組化架構設計，確保高擴充性與可測試性（測試覆蓋率 >= 90%）。

### 1.1 目標用戶

- **Phase 1**：個人使用
- **Phase 2+**：開放訂閱制（多用戶、權限分級）

### 1.2 支援市場

| 市場 | 交易所 |
|------|--------|
| 台股 | TWSE（上市）、TPEX（上櫃） |
| 美股 | NYSE、NASDAQ |

---

## 2. 技術棧

### 2.1 後端

| 項目 | 技術 | 說明 |
|------|------|------|
| 語言 | Python 3.12+ | 金融數據分析生態最成熟 |
| Web 框架 | FastAPI | 高效能、自動 OpenAPI 文件、async 支援 |
| ORM | SQLAlchemy 2.0 | async 支援、型別安全 |
| Migration | Alembic | 資料庫版本控制 |
| 排程 | APScheduler | 定時任務（盤前/盤中/盤後通知） |
| 快取 | Redis | 股價快取、排程狀態、Rate limit |
| 測試 | pytest + pytest-cov + pytest-asyncio | 覆蓋率 >= 90% |
| Linting | ruff | 統一程式碼風格 |
| 型別檢查 | mypy | 靜態型別驗證 |

### 2.2 前端

| 項目 | 技術 | 說明 |
|------|------|------|
| 框架 | Next.js 15 (App Router) | SSR + CSR 混合渲染 |
| 語言 | TypeScript | 型別安全 |
| 樣式 | TailwindCSS + shadcn/ui | 快速開發、一致性 UI |
| 圖表 | TradingView Lightweight Charts / Recharts | 專業 K 線圖 + 數據圖表 |
| 狀態管理 | Zustand | 輕量、簡潔 |
| 測試 | Vitest + Testing Library | 覆蓋率 >= 90% |

### 2.3 基礎設施

| 項目 | 技術 |
|------|------|
| 資料庫 | PostgreSQL 16 |
| 快取/佇列 | Redis 7 |
| 容器化 | Docker + docker-compose |
| CI/CD | GitHub Actions |
| 通知 | python-telegram-bot |

---

## 3. 資料來源

### 3.1 台股

| 資料類型 | 來源 | API 端點 | 備註 |
|----------|------|----------|------|
| 每日股價 (OHLCV) | TWSE OpenAPI | `https://openapi.twse.com.tw/v1/exchangeReport/STOCK_DAY_ALL` | 免費、無需 API Key、收盤後更新 |
| 上櫃股價 | TPEX OpenAPI | `https://www.tpex.org.tw/openapi/v1/tpex_mainboard_quotes` | 免費、無需 API Key |
| 本益比/殖利率/淨值比 | TWSE OpenAPI | `https://openapi.twse.com.tw/v1/exchangeReport/BWIBBU_ALL` | 含產業別 PE 比較 |
| 財務報表 | MOPS 公開資訊觀測站 | `https://mops.twse.com.tw/mops/web/ajax_t163sb05` | 需節流（3-5 秒間隔），IP 封鎖風險 |
| 歷史資料備援 | TWSE 官網 CSV | `https://www.twse.com.tw/exchangeReport/STOCK_DAY` | CSV 下載 |

### 3.2 美股

| 資料類型 | 來源 | 備註 |
|----------|------|------|
| 每日股價 (OHLCV) | yfinance | 免費、無需 Key、15 分鐘延遲、~2000 req/hr |
| 財務報表 | SEC EDGAR XBRL | `https://data.sec.gov/api/xbrl/companyfacts/CIK{cik}.json`、10 req/s、需 User-Agent |
| 即時報價（備援） | Finnhub Free | 60 calls/min、需 API Key |
| 歷史備援 | Alpha Vantage Free | 25 req/day（極度受限，僅作備援） |

### 3.3 資料來源抽象層

所有資料來源必須實作統一介面 (`DataProvider` Protocol)，確保：
- 可替換資料來源而不影響上層模組
- 可注入 Mock Provider 進行測試
- 未來可接入付費資料源

---

## 4. 模組規格

### 4.1 股價更新模組 (`price_updater`)

**職責**：定時抓取並儲存台美股每日股價資料

**功能需求**：
- FR-4.1.1：每日收盤後自動抓取 TWSE/TPEX 全市場股價
- FR-4.1.2：每日收盤後自動抓取美股全市場股價
- FR-4.1.3：支援單一股票手動更新
- FR-4.1.4：支援歷史資料回補（指定日期範圍）
- FR-4.1.5：資料去重、驗證（價格合理性檢查）
- FR-4.1.6：失敗自動重試（最多 3 次，指數退避）
- FR-4.1.7：更新完成後發送狀態通知

**非功能需求**：
- NFR-4.1.1：全市場更新需在 10 分鐘內完成
- NFR-4.1.2：預留即時資料擴充介面（WebSocket ready）

**資料模型**：
```
StockPrice:
  - symbol: str (e.g., "2330.TW", "AAPL")
  - market: enum (TW_TWSE, TW_TPEX, US_NYSE, US_NASDAQ)
  - date: date
  - open: Decimal
  - high: Decimal
  - low: Decimal
  - close: Decimal
  - volume: int
  - change: Decimal
  - change_percent: Decimal
  - created_at: datetime
  - updated_at: datetime
```

---

### 4.2 技術指標模組 (`indicators`)

**職責**：基於股價資料計算各類技術指標

**功能需求**：
- FR-4.2.1：RSI（Relative Strength Index）— 支援自訂天數（預設 14）
- FR-4.2.2：MACD — 支援自訂快慢線/訊號線週期（預設 12/26/9）
- FR-4.2.3：KD（Stochastic Oscillator）— 支援自訂週期（預設 9/3/3）
- FR-4.2.4：本益比 (PE Ratio)
- FR-4.2.5：本淨比 (PB Ratio)
- FR-4.2.6：殖利率 (Dividend Yield)
- FR-4.2.7：移動平均線 MA（5/10/20/60/120/240）
- FR-4.2.8：布林通道 (Bollinger Bands)
- FR-4.2.9：成交量指標 (OBV, Volume MA)
- FR-4.2.10：支援批量計算（一次計算多檔股票）
- FR-4.2.11：指標結果快取（Redis），避免重複計算
- FR-4.2.12：Plugin 架構 — 可透過註冊機制新增自訂指標

**設計原則**：
- 每個指標為獨立的 `Indicator` class，實作統一 `calculate(prices) -> IndicatorResult` 介面
- 純函數設計，無副作用，易於測試

---

### 4.3 指標過濾器模組 (`screener`)

**職責**：透過指標組合條件篩選符合標準的股票

**功能需求**：
- FR-4.3.1：支援單一指標條件篩選（e.g., RSI < 30）
- FR-4.3.2：支援多指標 AND/OR 組合條件
- FR-4.3.3：支援比較運算（>, <, >=, <=, ==, between）
- FR-4.3.4：支援儲存/載入篩選條件（命名策略）
- FR-4.3.5：支援依市場（台/美）篩選
- FR-4.3.6：支援依產業別篩選
- FR-4.3.7：篩選結果支援排序（依任意指標欄位）
- FR-4.3.8：篩選結果支援分頁

**條件 DSL 範例**：
```json
{
  "name": "超跌反彈候選",
  "market": "TW",
  "conditions": {
    "operator": "AND",
    "rules": [
      { "indicator": "RSI", "params": {"period": 14}, "op": "<", "value": 30 },
      { "indicator": "KD_K", "params": {"period": 9}, "op": "<", "value": 20 },
      { "indicator": "volume_ma_ratio", "params": {"period": 5}, "op": ">", "value": 1.5 }
    ]
  },
  "sort_by": "RSI",
  "sort_order": "asc"
}
```

---

### 4.4 產業低基期過濾器 (`industry_screener`)

**職責**：透過產業平均本益比找出低基期、高勝率的投資標的

**功能需求**：
- FR-4.4.1：計算各產業平均 PE / PB / 殖利率
- FR-4.4.2：計算個股 PE 相對產業的偏離程度（Z-Score）
- FR-4.4.3：篩選 PE 低於產業平均 N 個標準差的股票
- FR-4.4.4：排除虧損股（負 EPS）
- FR-4.4.5：支援歷史產業 PE 區間分析（目前處於歷史何種位置）
- FR-4.4.6：支援台股產業分類（TWSE 產業別）
- FR-4.4.7：支援美股 GICS 產業分類
- FR-4.4.8：產出「低基期評分」綜合排名

---

### 4.5 財報分析模組 (`financial_analysis`)

**職責**：解析並分析公司財務報表

**功能需求**：
- FR-4.5.1：自動抓取並解析季度/年度財報
- FR-4.5.2：三大報表分析（損益表、資產負債表、現金流量表）
- FR-4.5.3：關鍵財務比率計算：
  - 獲利能力：毛利率、營業利益率、淨利率、ROE、ROA
  - 經營效率：存貨週轉率、應收帳款週轉率
  - 償債能力：流動比率、速動比率、負債比率
  - 成長性：營收 YoY、EPS YoY、淨利 YoY
- FR-4.5.4：財報趨勢分析（連續 N 季比較）
- FR-4.5.5：同業財報比較
- FR-4.5.6：異常偵測（突然的毛利率變化、應收帳款暴增等）
- FR-4.5.7：財報評分（綜合健康度指標）

---

### 4.6 訂單與現金流分析模組 (`cashflow_analysis`)

**職責**：分析公司訂單能見度與現金流健康程度

**功能需求**：
- FR-4.6.1：營業現金流分析（自由現金流計算）
- FR-4.6.2：現金流品質評估（營業現金流 vs 淨利 比率）
- FR-4.6.3：資本支出趨勢分析
- FR-4.6.4：股利發放能力評估（自由現金流 vs 股利）
- FR-4.6.5：現金轉換週期 (Cash Conversion Cycle) 計算
- FR-4.6.6：營收月增率/年增率趨勢（台股月營收）
- FR-4.6.7：現金流警示（連續 N 季營業現金流為負）

---

### 4.7 到價通知模組 (`notifier`)

**職責**：監控股價並在觸發條件時透過 Telegram 發送通知

**功能需求**：
- FR-4.7.1：設定價格到達通知（上穿/下穿指定價格）
- FR-4.7.2：設定漲跌幅通知（單日漲跌幅超過 N%）
- FR-4.7.3：設定技術指標通知（e.g., RSI 低於 30 時通知）
- FR-4.7.4：每日三時段通知：
  - 盤前摘要（08:30 台股 / 21:00 美股）：前日回顧 + 今日觀察清單
  - 盤中警示：觸發條件時即時通知（預留，Phase 2）
  - 盤後總結（14:00 台股 / 05:00 美股）：持股表現 + 篩選結果
- FR-4.7.5：通知去重（同一條件同日不重複發送）
- FR-4.7.6：支援通知靜音（特定時段暫停通知）
- FR-4.7.7：通知歷史紀錄查詢

**通知格式範例**：
```
[盤後總結] 2026-04-22 台股

持股表現：
  2330 台積電  $890 (+2.3%)
  2317 鴻海    $178 (-0.5%)

今日篩選命中：
  超跌反彈: 2412 中華電 (RSI: 28.5)
  低基期: 3034 聯詠 (PE: 11.2, 產業均: 18.5)
```

**通知管道**：
- Phase 1：Telegram Bot
- Phase 2+：LINE Notify、Email、Web Push

---

### 4.8 股價預估模組 (`price_estimator`)

**職責**：基於多種模型預估股票合理價格

**功能需求**：
- FR-4.8.1：本益比估值法（歷史 PE 區間 × 預估 EPS）
- FR-4.8.2：本淨比估值法
- FR-4.8.3：股利折現模型 (DDM)
- FR-4.8.4：自由現金流折現模型 (DCF) — 簡化版
- FR-4.8.5：同業比較估值法
- FR-4.8.6：綜合估值（多模型加權平均）
- FR-4.8.7：輸出便宜價/合理價/昂貴價三檔價格
- FR-4.8.8：估值信心指標（依資料完整度與模型一致性）

---

### 4.9 投資策略模組 (`strategy`)

**職責**：定義可執行的投資策略規則

**功能需求**：
- FR-4.9.1：策略定義框架（進場條件、出場條件、部位管理）
- FR-4.9.2：內建策略：
  - 均線突破策略（MA crossover）
  - RSI 超賣反彈策略
  - 低基期價值投資策略
  - 股利成長策略
- FR-4.9.3：自訂策略（組合指標條件 + 進出場規則）
- FR-4.9.4：策略參數化（所有閾值皆可調整）
- FR-4.9.5：策略版本管理（儲存/載入/比較不同版本）
- FR-4.9.6：策略觸發通知整合

**策略定義結構**：
```python
class Strategy:
    name: str
    description: str
    entry_conditions: list[Condition]   # 進場條件
    exit_conditions: list[Condition]    # 出場條件
    position_sizing: PositionRule       # 部位規則
    risk_management: RiskRule           # 風控規則
```

---

### 4.10 回測模組 (`backtester`)

**職責**：以歷史資料驗證投資策略的績效

**功能需求**：
- FR-4.10.1：支援任意時間範圍回測
- FR-4.10.2：支援單一股票 & 投資組合回測
- FR-4.10.3：績效指標計算：
  - 總報酬率、年化報酬率
  - 最大回撤 (Max Drawdown)
  - 夏普比率 (Sharpe Ratio)
  - 勝率 (Win Rate)
  - 盈虧比 (Profit Factor)
  - 交易次數、平均持有天數
- FR-4.10.4：支援交易成本模擬（手續費、交易稅）
  - 台股：手續費 0.1425%（可折扣）、交易稅 0.3%（賣出）
  - 美股：可自訂
- FR-4.10.5：回測結果視覺化（權益曲線、交易標記）
- FR-4.10.6：多策略比較回測
- FR-4.10.7：Walk-forward 驗證（滾動視窗回測）
- FR-4.10.8：回測報告產出（含統計摘要 + 圖表）

---

## 5. 非功能需求

### 5.1 測試要求

| 項目 | 要求 |
|------|------|
| 後端單元測試覆蓋率 | >= 90% |
| 前端單元測試覆蓋率 | >= 90% |
| 整合測試 | 所有 API endpoint |
| E2E 測試 | 關鍵使用者流程 |
| 測試框架 | pytest (後端) / Vitest (前端) |
| CI 自動測試 | 每次 PR 必須通過 |

### 5.2 程式碼品質

- 所有模組須有型別標註 (Python type hints / TypeScript strict)
- ruff 格式化 + mypy strict mode
- 每個模組須有獨立的 README 說明用途、介面、範例
- API 文件由 FastAPI 自動產生 (OpenAPI/Swagger)

### 5.3 效能

- 全市場股價更新：< 10 分鐘
- 單一指標計算（單檔股票）：< 100ms
- 篩選器查詢（全市場）：< 3 秒
- 回測（單股 10 年日線）：< 5 秒
- API 回應（一般查詢）：< 500ms

### 5.4 安全性

- API Key / Token 環境變數管理，不入版控
- Telegram Bot Token 加密儲存
- Phase 2：JWT 認證 + RBAC 權限
- Rate limiting（防濫用）
- SQL Injection 防護（ORM 參數化查詢）

### 5.5 可觀測性

- 結構化日誌 (structlog)
- 關鍵操作 metrics（更新耗時、錯誤率）
- 健康檢查端點 (`/health`)

---

## 6. 開發階段規劃

### Phase 1 — 基礎建設 + 核心資料（4 週）

| 週次 | 任務 |
|------|------|
| W1 | 專案架構建立、Docker 環境、CI/CD pipeline、DB schema |
| W2 | 股價更新模組（台股 TWSE/TPEX + 美股 yfinance） |
| W3 | 技術指標模組（RSI、MACD、KD、MA、BB） |
| W4 | 前端骨架 + 股價圖表頁面 + 指標疊加顯示 |

**交付物**：可更新股價、計算指標、前端看盤頁面

### Phase 2 — 篩選 + 通知（3 週）

| 週次 | 任務 |
|------|------|
| W5 | 指標過濾器模組（條件 DSL + 篩選引擎） |
| W6 | 產業低基期過濾器 + 到價通知模組 (Telegram) |
| W7 | 前端篩選器 UI + 通知設定頁面 |

**交付物**：可篩選股票、設定通知、收到 Telegram 推播

### Phase 3 — 財報 + 估值（3 週）

| 週次 | 任務 |
|------|------|
| W8 | 財報分析模組（台股 MOPS + 美股 SEC EDGAR） |
| W9 | 現金流分析模組 + 股價預估模組 |
| W10 | 前端財報頁面 + 估值儀表板 |

**交付物**：完整財報分析、估值模型、視覺化呈現

### Phase 4 — 策略 + 回測（3 週）

| 週次 | 任務 |
|------|------|
| W11 | 投資策略模組（策略定義框架 + 內建策略） |
| W12 | 回測模組（回測引擎 + 績效計算） |
| W13 | 前端策略管理 + 回測結果視覺化 |

**交付物**：可定義策略、執行回測、查看績效報告

### Phase 5 — 優化 + 訂閱制（2 週）

| 週次 | 任務 |
|------|------|
| W14 | 效能優化、快取策略、錯誤處理強化 |
| W15 | 用戶認證系統 (JWT)、訂閱分級、部署準備 |

**交付物**：Production-ready 系統

---

## 7. 專案結構

```
uni-seeker/
├── backend/
│   ├── app/
│   │   ├── main.py                 # FastAPI entry point
│   │   ├── config.py               # Settings (pydantic-settings)
│   │   ├── database.py             # DB engine & session
│   │   ├── models/                 # SQLAlchemy models
│   │   │   ├── stock.py
│   │   │   ├── price.py
│   │   │   ├── financial.py
│   │   │   └── notification.py
│   │   ├── schemas/                # Pydantic request/response schemas
│   │   ├── api/                    # API routers
│   │   │   ├── v1/
│   │   │   │   ├── prices.py
│   │   │   │   ├── indicators.py
│   │   │   │   ├── screener.py
│   │   │   │   ├── financials.py
│   │   │   │   ├── notifications.py
│   │   │   │   ├── strategies.py
│   │   │   │   └── backtest.py
│   │   │   └── deps.py             # Shared dependencies
│   │   ├── modules/                # Core business logic
│   │   │   ├── price_updater/
│   │   │   │   ├── __init__.py
│   │   │   │   ├── base.py         # DataProvider protocol
│   │   │   │   ├── twse.py         # TWSE implementation
│   │   │   │   ├── tpex.py         # TPEX implementation
│   │   │   │   ├── yfinance_provider.py
│   │   │   │   └── updater.py      # Orchestrator
│   │   │   ├── indicators/
│   │   │   │   ├── __init__.py
│   │   │   │   ├── base.py         # Indicator protocol
│   │   │   │   ├── registry.py     # Plugin registry
│   │   │   │   ├── rsi.py
│   │   │   │   ├── macd.py
│   │   │   │   ├── kd.py
│   │   │   │   ├── moving_average.py
│   │   │   │   ├── bollinger.py
│   │   │   │   └── volume.py
│   │   │   ├── screener/
│   │   │   │   ├── __init__.py
│   │   │   │   ├── engine.py       # Filter engine
│   │   │   │   ├── conditions.py   # Condition DSL
│   │   │   │   └── industry.py     # Industry screener
│   │   │   ├── financial_analysis/
│   │   │   │   ├── __init__.py
│   │   │   │   ├── parser.py       # Report parser
│   │   │   │   ├── ratios.py       # Financial ratios
│   │   │   │   ├── scorer.py       # Health scorer
│   │   │   │   └── cashflow.py     # Cash flow analysis
│   │   │   ├── price_estimator/
│   │   │   │   ├── __init__.py
│   │   │   │   ├── pe_model.py
│   │   │   │   ├── ddm.py
│   │   │   │   ├── dcf.py
│   │   │   │   └── composite.py    # Weighted ensemble
│   │   │   ├── strategy/
│   │   │   │   ├── __init__.py
│   │   │   │   ├── base.py         # Strategy protocol
│   │   │   │   ├── builtin/        # Built-in strategies
│   │   │   │   └── manager.py      # CRUD + versioning
│   │   │   ├── backtester/
│   │   │   │   ├── __init__.py
│   │   │   │   ├── engine.py       # Backtest engine
│   │   │   │   ├── portfolio.py    # Portfolio tracker
│   │   │   │   ├── metrics.py      # Performance metrics
│   │   │   │   └── report.py       # Report generator
│   │   │   └── notifier/
│   │   │       ├── __init__.py
│   │   │       ├── base.py         # Channel protocol
│   │   │       ├── telegram.py     # Telegram implementation
│   │   │       ├── scheduler.py    # Notification scheduler
│   │   │       └── templates.py    # Message templates
│   │   └── services/               # Cross-module orchestration
│   ├── alembic/                    # DB migrations
│   ├── tests/
│   │   ├── conftest.py             # Shared fixtures
│   │   ├── unit/                   # Unit tests (mirrors modules/)
│   │   ├── integration/            # API integration tests
│   │   └── factories/              # Test data factories
│   ├── pyproject.toml
│   └── Dockerfile
├── frontend/
│   ├── src/
│   │   ├── app/                    # Next.js App Router pages
│   │   ├── components/
│   │   │   ├── charts/             # Stock charts, equity curves
│   │   │   ├── screener/           # Screener UI
│   │   │   ├── financials/         # Financial report views
│   │   │   └── ui/                 # shadcn/ui components
│   │   ├── lib/                    # API client, utils
│   │   └── stores/                 # Zustand stores
│   ├── tests/
│   ├── package.json
│   └── Dockerfile
├── docker-compose.yml
├── .github/
│   └── workflows/
│       ├── backend-ci.yml
│       └── frontend-ci.yml
└── docs/
    ├── REQUIREMENTS.md              # 本文件
    └── API.md                       # API 文件（自動產生）
```

---

## 8. 開放問題

| # | 問題 | 影響模組 | 優先級 |
|---|------|----------|--------|
| Q1 | 是否需要支援 ETF？ | price_updater, indicators | Medium |
| Q2 | 回測是否需要支援做空？ | backtester, strategy | Low |
| Q3 | 是否需要支援加密貨幣市場？ | 全模組 | Low |
| Q4 | 前端是否需要多語系（中/英）？ | frontend | Medium |
| Q5 | 部署環境偏好？（VPS / Cloud / Self-hosted） | infra | Phase 5 |
| Q6 | 訂閱制的分級方案？（功能差異） | auth, all modules | Phase 5 |

---

## 9. 驗收標準

- [ ] 所有模組通過單元測試，覆蓋率 >= 90%
- [ ] 整合測試涵蓋所有 API endpoint
- [ ] 前端測試覆蓋率 >= 90%
- [ ] Docker Compose 一鍵啟動完整環境
- [ ] Telegram 通知正常運作
- [ ] 回測結果與手動驗算一致（誤差 < 0.1%）
- [ ] 全市場篩選回應時間 < 3 秒
