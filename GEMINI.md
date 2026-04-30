# Uni-Seeker - Project Context & Guidelines

Uni-Seeker 是一個模組化的**台美股分析平台**，提供股價追蹤、技術指標計算、財報分析、投資策略回測與到價通知功能。

## 專案概述
- **目標**：提供個人化的自動化投資分析工具，涵蓋台股 (TWSE/TPEX) 與美股 (NYSE/NASDAQ)。
- **核心架構**：
    - **後端**：基於 Python 3.12 + FastAPI。採用 **Protocol-based (介面導向)** 設計，確保所有資料來源 (DataProviders) 與指標 (Indicators) 易於替換與擴充。
    - **前端**：基於 Next.js 15+ (App Router) + TypeScript + TailwindCSS。
    - **資料庫**：PostgreSQL (主儲存)、Redis (快取與排程)。
- **當前進度**：已完成 Phase 1 (基礎建設) 與 Phase 2 (篩選器與通知)，即將進入 Phase 3 (財報與估值)。

## 技術棧詳情
### 後端 (Backend)
- **框架**：FastAPI (非同步支援)
- **ORM**：SQLAlchemy 2.0 (Async) + Alembic (遷移)
- **資料分析**：Pandas, yfinance
- **排程與通知**：APScheduler, python-telegram-bot
- **測試**：pytest + pytest-asyncio + pytest-cov (目標覆蓋率 >= 90%)
- **品質控制**：Ruff (Linting/Formatting), Mypy (Type checking), pre-commit hooks

### 前端 (Frontend)
- **框架**：Next.js 16 (React 19)
- **樣式**：TailwindCSS + shadcn/ui
- **圖表**：Lightweight Charts (TradingView)
- **狀態管理**：Zustand
- **測試**：Vitest (待補齊覆蓋率)

## 開發慣例與指南
- **TDD (測試驅動開發)**：在開發新功能或修復 Bug 時，必須先編寫測試。後端必須維持 90% 以上的覆蓋率。
- **模組化設計**：
    - 新的技術指標應繼承 `app.modules.indicators.base.Indicator` 協議並註冊到 `registry`。
    - 新的資料來源應實作 `app.modules.price_updater.base.DataProvider` 協議。
- **API 規格**：使用 Pydantic Schemas 定義 Request/Response。所有 API 應位於 `app.api.v1/`。
- **Git 流程**：不直接 commit 到 main 分支 (理想情況)。使用結構化的 commit messages。
- **安全性**：Secrets (API Keys, Tokens) 必須透過環境變數管理，嚴禁入版控。參考 `.env` (如有) 或 `app/config.py`。

## 關鍵運行指令
### 啟動服務 (Docker)
```bash
docker compose up -d
```

### 後端開發環境
```bash
cd backend
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
# 運行測試
pytest
# 啟動開發伺服器
uvicorn app.main:app --reload
```

### 前端開發環境
```bash
cd frontend
npm install
npm run dev
```

## 重要文件位置
- `docs/REQUIREMENTS.md`：原始需求說明文件。
- `docs/superpowers/plans/`：各階段開發計畫書。
- `backend/app/modules/`：核心業務邏輯。
- `frontend/src/app/`：頁面與路由。
