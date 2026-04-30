# Uni-Seeker 優化規劃清單

> 完整專案審計結果，依優先級排序

---

## 🔴 CRITICAL — 必須立即修復

| # | 類別 | 問題 | 檔案 | 建議做法 |
|---|------|------|------|---------|
| 1 | 安全 | JWT Secret Key 寫死在程式碼中 | `backend/app/auth.py` | 改用環境變數 `JWT_SECRET_KEY` |
| 2 | 安全 | Docker Compose 資料庫密碼明碼 | `docker-compose.yml` | 用 `.env` + Docker Secrets |
| 3 | 安全 | 登入 API 無頻率限制（暴力破解風險） | `backend/app/api/v1/auth.py` | 加 `slowapi` 或 Redis 限流 (5次/分/IP) |
| 4 | 安全 | 密碼無強度驗證 | `backend/app/api/v1/auth.py` | Pydantic validator: `min_length=8` + 複雜度 |
| 5 | 安全 | CSRF 保護缺失 | Backend 全域 | SameSite=Strict cookies + CSRF token |

---

## 🟠 HIGH — 優先處理

| # | 類別 | 問題 | 檔案 | 建議做法 |
|---|------|------|------|---------|
| 6 | 安全 | Nginx 缺少安全 Headers | `nginx.conf` | 加 `X-Frame-Options`, `X-Content-Type-Options`, `HSTS` |
| 7 | 安全 | Nginx 無請求限流 | `nginx.conf` | 加 `limit_req_zone` 防 DOS |
| 8 | API | 前端 API Client 無 retry/timeout | `frontend/src/lib/api-client.ts` | 加 `AbortController` 10s timeout + 指數退避 retry |
| 9 | API | API 錯誤回傳格式不統一 | `backend/app/middleware/error_handler.py` | 統一 `{error, message, detail}` 格式 |
| 10 | 效能 | 回測 API 無執行超時 | `backend/app/api/v1/backtest.py` | 加 30s timeout，長時間任務走 Job Queue |
| 11 | 效能 | Screener 有 N+1 查詢問題 | `backend/app/api/v1/screener.py` | 批次查詢 + 分頁 |
| 12 | 安全 | 登入失敗無日誌記錄 | `backend/app/api/v1/auth.py` | 記錄 IP、email、時間戳 |
| 13 | API | Auth Token 未自動注入所有請求 | `frontend/src/lib/api-client.ts` | 建 `apiClient` wrapper 自動帶 token |

---

## 🟡 MEDIUM — 持續改善

### 功能面

| # | 問題 | 建議做法 |
|---|------|---------|
| 14 | 個股頁面缺少技術指標圖表（RSI/MACD/BB） | 加指標 Tab，整合 lightweight-charts |
| 15 | 首頁市場行情無自動更新 | React Query `refetchInterval: 60000` |
| 16 | 自選股缺少批次操作/分組/排序 | 加多選、拖拽排序、資料夾分組 |
| 17 | 通知系統只有設定，沒有即時推播 | WebSocket 連線 + Toast 通知 |
| 18 | 無即時股價更新 | WebSocket 連線，1-5 秒更新 |
| 19 | 無匯出功能（CSV/PDF） | 篩選器、回測結果加 CSV 下載 |
| 20 | 比較頁面手機版需橫向滾動 | 響應式 Grid + 折疊式比較 |

### 設計面

| # | 問題 | 建議做法 |
|---|------|---------|
| 21 | 股價漲跌顏色與國際慣例相反（紅漲綠跌） | 加 locale-aware 顏色設定，或在設定頁讓使用者選 |
| 22 | 無淺色模式選項 | 加 `prefers-color-scheme` 支援 + 主題切換 |
| 23 | 缺乏正式排版系統（h1-h6） | 定義 CSS 字型大小變數 + 工具類別 |
| 24 | 頁面間距不一致（p-3 vs p-4） | 建立標準 page padding 元件 |
| 25 | CSS 變數命名不一致（bg-* vs card-*） | 審計並統一命名規範 |

### 無障礙 (A11Y)

| # | 問題 | 建議做法 |
|---|------|---------|
| 26 | 圖示按鈕缺少 `aria-label` | 全面補上 ARIA 標籤 |
| 27 | 熱力圖只用顏色區分（色盲不友善） | 加文字標籤 + 圖案 |
| 28 | DataTable 無鍵盤導覽 | 加 `role="button"`, `tabindex`, `aria-sort` |
| 29 | Focus 狀態不一致 | 審計所有互動元素的 `:focus-visible` |

### 國際化 (i18n)

| # | 問題 | 建議做法 |
|---|------|---------|
| 30 | 回測頁面 Tab 標籤寫死中文 | 改用 `t.backtest.xxx` i18n key |
| 31 | 數字/日期格式未跟隨語系 | 建 `useLocaleFormat()` hook |
| 32 | i18n key 命名不一致 | 統一用 camelCase 點號分隔 |
| 33 | 部分翻譯 key 缺失 | 補齊 screener、backtest 相關 key |

### 後端

| # | 問題 | 建議做法 |
|---|------|---------|
| 34 | Screener 輸入未限制 limit 上限 | `limit: int = Field(..., le=1000)` |
| 35 | 資料庫缺少 `date` 單獨索引 | 加 `Index("ix_stock_prices_date", "date")` |
| 36 | DB 連線池未設定 | `pool_size=20, max_overflow=40` |
| 37 | 市場數據 API 無快取 | Redis 快取 1 小時 |
| 38 | React Query key 無統一工廠 | 建 `queryKeys` 物件統一管理 |
| 39 | localStorage 多分頁同步問題 | 用 `BroadcastChannel` 或 `storage` 事件 |

---

## 🟢 LOW — 有空再做

### 功能

| # | 問題 | 建議做法 |
|---|------|---------|
| 40 | 自選股無匯出/匯入 | CSV 匯出入 |
| 41 | 無離線支援 | Service Worker + 離線快取 |
| 42 | 通知無 Backtest 結果關聯 | 加 FK 連結 notification → backtest_result |
| 43 | 無 Soft Delete | 所有 model 加 `deleted_at` 欄位 |

### UI 元件

| # | 問題 | 建議做法 |
|---|------|---------|
| 44 | Badge 元件缺少 neutral/warning 變體 | 新增語意化變體 |
| 45 | EmptyState 元件無預設圖示 | 加預設 SVG icon |
| 46 | DataTable 無 skeleton loading | 加 `isLoading` prop + 骨架屏 |
| 47 | LoadingSpinner 每次 render 重算 | 抽出常數 + `React.memo` |
| 48 | Nav Bar 連結過多擁擠 | Scanner/Portfolio 移到「工具」子選單 |
| 49 | Command Palette 搜尋無 debounce | 加 300ms debounce |

### 程式碼品質

| # | 問題 | 建議做法 |
|---|------|---------|
| 50 | 魔術數字散佈各處 | 抽出命名常數 |
| 51 | 前端型別用 `as` 斷言 | 改用 type guard |
| 52 | API response 無 runtime 驗證 | 用 Zod schema 驗證 |
| 53 | 缺少 ADR（架構決策紀錄） | 建 `/docs/adr/` 目錄 |

### 測試

| # | 問題 | 建議做法 |
|---|------|---------|
| 54 | 後端測試覆蓋率不足 (~45%) | 目標 80%，補 API 整合測試 |
| 55 | 無前端 E2E 測試 | Playwright 測關鍵流程 |
| 56 | 無 API 契約測試 | 用 Pact 確保前後端介面一致 |

### 部署

| # | 問題 | 建議做法 |
|---|------|---------|
| 57 | 前端容器無 Health Check | 加 curl -f localhost:3000 |
| 58 | Nginx 無 Gzip 壓縮 | `gzip on; gzip_types ...` |
| 59 | 前端環境變數寫死 | 改用 `.env` 動態注入 |

---

## 📊 統計

| 優先級 | 數量 |
|--------|------|
| 🔴 CRITICAL | 5 |
| 🟠 HIGH | 8 |
| 🟡 MEDIUM | 26 |
| 🟢 LOW | 20 |
| **合計** | **59** |

## 🎯 建議執行順序

1. **Phase 1** — 修復 5 個 CRITICAL 安全問題（1-2 天）
2. **Phase 2** — 處理 HIGH 項目 + API 錯誤處理統一（2-3 天）
3. **Phase 3** — 功能增強：技術指標圖表、即時更新、匯出功能（3-5 天）
4. **Phase 4** — 設計改善：主題切換、排版統一、無障礙修復（2-3 天）
5. **Phase 5** — 測試覆蓋率提升 + 部署優化（2-3 天）
