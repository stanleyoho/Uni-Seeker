# Uni-Seeker

**[English](#english) | [中文](#中文)**

---

<a id="english"></a>

## English

### Overview

Uni-Seeker is a modular **Taiwan + US stock analysis platform** providing price tracking, technical indicators, financial analysis, investment strategy backtesting, and price alerts. Built with a Protocol-based architecture for high extensibility and testability (90%+ test coverage).

### Features

| Module | Status | Description |
|--------|--------|-------------|
| Price Updater | ✅ Phase 1 | Daily OHLCV from TWSE, TPEX, yfinance with retry/dedup/validation |
| Technical Indicators | ✅ Phase 1 | RSI, MACD, KD, MA (SMA/EMA), Bollinger Bands, OBV/VMA — plugin registry |
| Screener | ✅ Phase 2 | Filter stocks by indicator conditions (AND/OR DSL) |
| Industry Screener | ✅ Phase 2 | Find undervalued stocks via industry PE Z-Score |
| Notifications | ✅ Phase 2 | Telegram alerts: pre-market / post-market / price triggers |
| Financial Analysis | ✅ Phase 3 | Quarterly reports, ratios, health scoring (yfinance) |
| Price Estimator | ✅ Phase 3 | PE/DDM/DCF valuation models with composite ensemble |
| Strategy | ✅ Phase 4 | MA Crossover, RSI Oversold — extensible framework |
| Backtester | ✅ Phase 4 | Historical backtest with Sharpe, max drawdown, win rate |
| Auth | ✅ Phase 5 | JWT login/register, user tiers (free/basic/pro) |
| Caching | ✅ Phase 5 | Redis cache for indicator calculations |
| i18n | ✅ Phase 5 | Traditional Chinese + English with language switcher |

### Tech Stack

| Layer | Technology |
|-------|-----------|
| Backend | Python 3.12, FastAPI, SQLAlchemy 2.0 (async), PostgreSQL 16, Redis 7 |
| Frontend | Next.js 15, TypeScript, TailwindCSS, TradingView Lightweight Charts |
| Infra | Docker Compose, GitHub Actions CI, pre-commit (ruff + mypy + pytest) |

### Quick Start

```bash
# Clone
git clone https://github.com/stanleyoho/Uni-Seeker.git
cd Uni-Seeker

# Start all services
docker compose up -d

# Backend: http://localhost:8000/docs (Swagger UI)
# Frontend: http://localhost:3000
```

#### Local Development (without Docker)

```bash
# Backend
cd backend
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
pre-commit install

# Run tests
pytest -v

# Start server
uvicorn app.main:app --reload

# Frontend
cd frontend
npm install
npm run dev
```

### API Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/v1/prices/{symbol}` | Get stock prices (paginated) |
| GET | `/api/v1/indicators/` | List available indicators |
| POST | `/api/v1/indicators/calculate` | Calculate indicator for a stock |
| POST | `/api/v1/screener/screen` | Screen stocks by indicator conditions |
| GET | `/api/v1/notifications/rules` | List notification rules |
| POST | `/api/v1/notifications/rules` | Create notification rule |
| DELETE | `/api/v1/notifications/rules/{id}` | Delete notification rule |
| GET | `/health` | Health check |

### Data Sources

| Market | Source | Auth | Rate Limit |
|--------|--------|------|-----------|
| TW (Listed) | TWSE OpenAPI | None | ~1 req/day (bulk) |
| TW (OTC) | TPEX OpenAPI | None | ~1 req/day (bulk) |
| TW (Financials) | MOPS | None | 3-5s interval |
| US (Prices) | yfinance | None | ~2000 req/hr |
| US (Financials) | SEC EDGAR | User-Agent | 10 req/s |

### Project Structure

```
uni-seeker/
├── backend/
│   ├── app/
│   │   ├── api/v1/          # FastAPI routers
│   │   ├── models/          # SQLAlchemy models
│   │   ├── modules/
│   │   │   ├── price_updater/   # DataProvider protocol + implementations
│   │   │   └── indicators/      # Indicator protocol + plugin registry
│   │   ├── schemas/         # Pydantic request/response schemas
│   │   └── main.py          # App factory
│   └── tests/               # 61 tests, 91.93% coverage
├── frontend/
│   └── src/
│       ├── app/             # Next.js App Router pages
│       ├── components/      # Stock chart (candlestick)
│       └── lib/             # API client
└── docker-compose.yml
```

### Testing

```bash
cd backend
pytest -v                    # Run all tests
pytest --cov-report=html     # Generate HTML coverage report
pytest -m "not integration"  # Unit tests only
```

### License

MIT

---

<a id="中文"></a>

## 中文

### 概述

Uni-Seeker 是一套模組化的**台美股分析平台**，提供股價追蹤、技術指標計算、財報分析、投資策略回測與到價通知功能。採用 Protocol-based 架構設計，確保高擴充性與可測試性（測試覆蓋率 90% 以上）。

### 功能模組

| 模組 | 狀態 | 說明 |
|------|------|------|
| 股價更新 | ✅ Phase 1 | 每日 OHLCV（TWSE、TPEX、yfinance），含重試/去重/驗證 |
| 技術指標 | ✅ Phase 1 | RSI、MACD、KD、MA（SMA/EMA）、布林通道、OBV/VMA — Plugin 架構 |
| 指標篩選器 | ✅ Phase 2 | 透過指標條件組合篩選股票（AND/OR DSL） |
| 產業低基期 | ✅ Phase 2 | 以產業平均本益比 Z-Score 找出低估值標的 |
| 到價通知 | ✅ Phase 2 | Telegram 推播：盤前/盤後摘要、觸價警示 |
| 財報分析 | ✅ Phase 3 | 季報解析、財務比率、健康度評分（yfinance） |
| 股價預估 | ✅ Phase 3 | PE/DDM/DCF 估值模型 + 加權綜合估值 |
| 投資策略 | ✅ Phase 4 | MA 交叉、RSI 超賣 — 可擴充框架 |
| 回測模組 | ✅ Phase 4 | 歷史回測，含 Sharpe、最大回撤、勝率 |
| 用戶認證 | ✅ Phase 5 | JWT 登入/註冊、訂閱分級（free/basic/pro） |
| 快取 | ✅ Phase 5 | Redis 快取指標計算結果 |
| 多語系 | ✅ Phase 5 | 繁體中文 + English 切換 |

### 技術棧

| 層級 | 技術 |
|------|------|
| 後端 | Python 3.12、FastAPI、SQLAlchemy 2.0（async）、PostgreSQL 16、Redis 7 |
| 前端 | Next.js 15、TypeScript、TailwindCSS、TradingView K 線圖 |
| 基建 | Docker Compose、GitHub Actions CI、pre-commit（ruff + mypy + pytest） |

### 快速開始

```bash
# 複製專案
git clone https://github.com/stanleyoho/Uni-Seeker.git
cd Uni-Seeker

# 一鍵啟動所有服務
docker compose up -d

# 後端 API 文件：http://localhost:8000/docs
# 前端介面：http://localhost:3000
```

#### 本地開發（不使用 Docker）

```bash
# 後端
cd backend
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
pre-commit install

# 執行測試
pytest -v

# 啟動伺服器
uvicorn app.main:app --reload

# 前端
cd frontend
npm install
npm run dev
```

### API 端點

| 方法 | 端點 | 說明 |
|------|------|------|
| GET | `/api/v1/prices/{symbol}` | 取得股價資料（分頁） |
| GET | `/api/v1/indicators/` | 列出可用指標 |
| POST | `/api/v1/indicators/calculate` | 計算指定股票的技術指標 |
| POST | `/api/v1/screener/screen` | 依指標條件篩選股票 |
| GET | `/api/v1/notifications/rules` | 列出通知規則 |
| POST | `/api/v1/notifications/rules` | 建立通知規則 |
| DELETE | `/api/v1/notifications/rules/{id}` | 刪除通知規則 |
| GET | `/health` | 健康檢查 |

### 資料來源

| 市場 | 來源 | 認證 | 頻率限制 |
|------|------|------|----------|
| 台股（上市） | TWSE OpenAPI | 免費 | 每日批量取一次 |
| 台股（上櫃） | TPEX OpenAPI | 免費 | 每日批量取一次 |
| 台股（財報） | 公開資訊觀測站 | 免費 | 3-5 秒間隔 |
| 美股（股價） | yfinance | 免費 | ~2000 次/小時 |
| 美股（財報） | SEC EDGAR | User-Agent | 10 次/秒 |

### 測試

```bash
cd backend
pytest -v                    # 執行所有測試
pytest --cov-report=html     # 產生 HTML 覆蓋率報告
pytest -m "not integration"  # 僅執行單元測試
```

### 授權

MIT
