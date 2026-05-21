# Uni-Seeker → STRATOS 設計系統遷移規格書

**日期**: 2026-04-30
**狀態**: 待審核

---

## 1. 專案概述

將 Uni-Seeker 台美股分析平台的所有前端頁面（14 頁）遷移至 STRATOS 暗黑奢華交易終端設計系統。保留所有現有功能邏輯和 API 整合，僅重構 UI 層。

### 核心原則

- **不改後端** — 所有 API 端點、hooks、資料流不變
- **保留 i18n** — zh-TW / en 雙語切換
- **雙主題模式** — 暗色：STRATOS 黑金奢華 ｜ 淺色：紅色賽車主題
- **漸進遷移** — 4 階段推進，每階段可獨立驗證

---

## 2. 設計系統

### 2.1 色彩系統

#### 暗色模式（STRATOS Terminal）

| Token | 值 | 用途 |
|-------|-----|------|
| `--background` | `#000000` | 主背景 |
| `--bg-secondary` | `#0a0a0a` | 次要背景 |
| `--card-bg` | `rgba(255,255,255,0.03)` | GlassPanel 背景 |
| `--foreground` | `#FFFFFF` | 主文字 |
| `--text-secondary` | `#9CA3AF` | 次要文字 |
| `--text-muted` | `#6B7280` | 靜音文字 |
| `--accent-primary` | `#EE3F2C` | 品牌紅 / 漲（亞洲慣例） |
| `--accent-cyan` | `#00E5FF` | 互動高亮 / focus |
| `--stock-up` | `#EE3F2C` | 漲 |
| `--stock-down` | `#10B981` | 跌 |
| `--border-color` | `rgba(255,255,255,0.12)` | GlassPanel 邊框 |
| `--border-subtle` | `rgba(255,255,255,0.06)` | 細分隔線 |

#### 淺色模式（Racing Red）

| Token | 值 | 用途 |
|-------|-----|------|
| `--background` | `#FAFAFA` | 主背景 |
| `--bg-secondary` | `#F0F0F0` | 次要背景 |
| `--card-bg` | `#FFFFFF` | 卡片背景 |
| `--foreground` | `#1A1A1A` | 主文字 |
| `--text-secondary` | `#4A4A4A` | 次要文字 |
| `--text-muted` | `#7A7A7A` | 靜音文字 |
| `--accent-primary` | `#D42B1E` | 賽車紅（品牌主色） |
| `--accent-secondary` | `#B71C1C` | 深紅（hover） |
| `--accent-highlight` | `#FF6B35` | 橘色高亮（速度感） |
| `--stock-up` | `#D42B1E` | 漲（紅） |
| `--stock-down` | `#1B8A4E` | 跌（綠） |
| `--border-color` | `rgba(0,0,0,0.10)` | 卡片邊框 |
| `--border-subtle` | `rgba(0,0,0,0.05)` | 細分隔線 |

淺色模式視覺特徵：
- 卡片使用微妙 `box-shadow` 取代暗色的 glass 效果
- 品牌紅色作為 accent 貫穿按鈕、active state、圖表高亮
- 橘色 `#FF6B35` 用於次要 accent（hover 狀態、badge）
- Header 背景：白色 + 底部紅色 2px accent line
- ClippedButton 保留斜角切角，紅色主色調

### 2.2 字體

- **全站統一**：Rubik (Google Fonts)
- 權重：300 / 400 / 500 / 600 / 700
- 數字：`font-variant-numeric: tabular-nums`
- 標題：bold, uppercase, `letter-spacing: -0.04em`
- 資料標籤：14px, regular
- 小標籤：11px, uppercase, gray

### 2.3 共用元件（已建置，需遷移至共用路徑）

從 `src/app/stratos/components/primitives.tsx` 遷移至 `src/components/stratos/`:

| 元件 | 說明 |
|------|------|
| `GlassPanel` | 液態玻璃容器（暗色）/ 白卡 + shadow（淺色）|
| `ClippedButton` | 斜角按鈕，5 變體 3 尺寸 |
| `KpiCard` | 指標卡片，方向箭頭 + 顏色 |
| `AmbientBackground` | SVG 動態格線背景（僅暗色模式） |
| `Sparkline` | 迷你走勢線 |

### 2.4 GlassPanel 雙主題行為

```css
/* 暗色 */
[data-theme="dark"] .glass-panel {
  background: rgba(255,255,255,0.03);
  backdrop-filter: blur(40px) saturate(180%);
  border: 1px solid rgba(255,255,255,0.12);
  background-image: linear-gradient(135deg, rgba(255,255,255,0.08) 0%, transparent 50%);
  box-shadow: inset 0 1px 0 rgba(255,255,255,0.1), 0 8px 32px rgba(0,0,0,0.4);
}

/* 淺色（賽車主題）*/
[data-theme="light"] .glass-panel {
  background: #FFFFFF;
  border: 1px solid rgba(0,0,0,0.08);
  box-shadow: 0 1px 3px rgba(0,0,0,0.06), 0 4px 16px rgba(0,0,0,0.04);
  border-radius: 2px;
}
```

---

## 3. 導航架構

### 3.1 Header（64px 固定高度）

```
┌──────────────────────────────────────────────────────────────┐
│ △ STRATOS    Markets  Research  Portfolio  🔔    🔍 搜尋  🌙 EN │
└──────────────────────────────────────────────────────────────┘
```

- **Logo**：SVG 三角 + "STRATOS" 文字（暗色白色，淺色黑色+紅色三角）
- **主導航**：3 個文字連結 + 1 個鈴鐺圖示
  - **Markets** → `/` (首頁 dashboard)
  - **Research** → `/research` (篩選/掃描/低基期/比較)
  - **Portfolio** → `/portfolio` (自選股/回測/組合回測)
  - **🔔** → `/alerts` (通知管理)
- **右側**：搜尋按鈕（F 快捷鍵）、主題切換、語言切換、登入/用戶
- **Sub-tab 導航**：進入 Research 或 Portfolio 後，頂部顯示子頁面切換條

### 3.2 TickerStrip（40px，Header 下方）

- 接入 `useMarketIndices()` 真實資料
- 滾動跑馬燈顯示所有指數 + 漲跌幅
- hover 暫停

### 3.3 Sub-Tab 路由映射

| 主導航 | Sub-Tabs | 路由 |
|--------|----------|------|
| **Markets** | (無 sub-tab，首頁即完整 dashboard) | `/` |
| **Research** | Screener \| Scanner \| Low Base \| Compare | `/research`, `/research/scanner`, `/research/low-base`, `/research/compare` |
| **Portfolio** | Watchlist \| Backtest \| Portfolio Test | `/portfolio`, `/portfolio/backtest`, `/portfolio/test` |
| **Alerts** | (無 sub-tab) | `/alerts` |

個股詳情：`/stocks/[symbol]`（從任何股票列表點擊進入）
熱力圖和三大法人：整合進首頁 dashboard 的面板中

---

## 4. 頁面設計

### 4.1 首頁 Dashboard `/`

```
┌─────────────────────────────────────────────────────────┐
│ Header + TickerStrip                                     │
├─────────────────────────────────────────────────────────┤
│ KPI: Portfolio Value | Daily P&L | Win Rate | Positions  │
├──────────────────────────┬──────────────────────────────┤
│ 4 大指數走勢面板 (8col)    │ Watchlist 自選股 (4col)      │
│ ┌──────────┬──────────┐  │ 接入 useWatchlist() 真實資料  │
│ │ 台股加權   │ SPY      │  │ 含 Sparkline + 漲跌色        │
│ │ KPI+Area  │ KPI+Area │  │                              │
│ ├──────────┼──────────┤  │                              │
│ │ QQQ      │ 費半 SOX  │  │                              │
│ │ KPI+Area  │ KPI+Area │  │                              │
│ └──────────┴──────────┘  │                              │
├────────┬────────┬────────┼──────────────────────────────┤
│Sector  │漲跌排行 │ News   │                              │
│Heatmap │3 欄    │ Feed   │                              │
│(4col)  │(4col)  │(4col)  │                              │
└────────┴────────┴────────┴──────────────────────────────┘
```

**4 大指數面板**（取代原 PrimaryChart 區域）：
- 2x2 grid，每格一個指數
- 每格內容：指數名稱 (11px label) + 最新值 (24px bold) + 漲跌% + 迷你 Area Chart
- 指數來源：`useMarketIndices()` 篩選出加權指數、SPY、QQQ、SOX
- 每格 GlassPanel 包裝

**漲跌排行**（取代原 Order Book 位置）：
- 3 欄：漲幅排行 / 跌幅排行 / 成交量排行
- 接入 `useMarketMovers()` 真實資料
- 每行：排名 + 代號 + 價格 + 漲跌% + Sparkline

**Sector Heatmap**：接入 `useHeatmap()` 真實資料
**News Feed**：接入後端 news API（如無 API 則用 mock）
**Watchlist**：接入 `useWatchlist()` + `usePrices()` 真實報價

**三大法人**：整合為首頁底部的一個 GlassPanel 摘要面板，顯示當日外資/投信/自營商淨買超金額。點擊展開進入詳細頁。

### 4.2 Research 頁面群 `/research/*`

共用 layout：頂部 sub-tab 切換條（Screener | Scanner | Low Base | Compare）

#### Screener `/research`
- GlassPanel 包裝條件建構器
- ClippedButton 「開始篩選」(red-solid)
- 結果表格用 GlassPanel，行 hover + 選中紅色左邊框
- 保留現有 `useScreenStocks()` 邏輯

#### Scanner `/research/scanner`
- 策略多選 → GlassPanel 內的 toggle pills
- 結果：信號強度標籤 (Strong Buy / Buy / Hold / Sell / Strong Sell)
- 保留 `useRunScan()` 邏輯

#### Low Base `/research/low-base`
- 排行表格：綜合分數 + 估值 + 價格位階 + 品質
- KpiCard 顯示掃描/合格數量
- 保留 `useLowBaseRanking()` 邏輯

#### Compare `/research/compare`
- 最多 5 檔股票並排
- 每檔一個 GlassPanel 卡片
- 保留 `useFinancialAnalysis()` + `useCompanyInfo()` 邏輯

### 4.3 Portfolio 頁面群 `/portfolio/*`

共用 layout：頂部 sub-tab 切換條（Watchlist | Backtest | Portfolio Test）

#### Watchlist `/portfolio`
- STRATOS Watchlist 風格（已建置）
- 接入 `useWatchlist()` 真實資料 + `usePrices()` 即時報價
- 保留 CSV 匯入匯出功能
- 加入/移除自選股操作

#### Backtest `/portfolio/backtest`
- 策略建構器 → GlassPanel
- 結果：權益曲線 (Area Chart) + KpiCard 績效指標 + 交易紀錄表格
- 保留全部 hooks：`useStrategies()`, `useRunBacktest()`, `useBacktestHistory()`

#### Portfolio Test `/portfolio/test`
- 標的配置編輯器 → GlassPanel 表格
- 再平衡設定 → GlassPanel 內的 radio + input
- 結果：組合權益曲線 + 個股曲線對比
- 保留 `usePortfolioBacktest()` 邏輯

### 4.4 Alerts 頁面 `/alerts`

- 規則列表：GlassPanel 表格，每行顯示名稱/類型/股票/狀態
- 新增規則：GlassPanel 表單，ClippedButton 提交
- 保留 `useNotificationRules()` 邏輯 + WebSocket 即時通知

### 4.5 個股詳情 `/stocks/[symbol]`

```
┌─────────────────────────────┬──────────────┐
│ K 線圖 + 技術指標 (8col)      │ 公司資訊 (4col) │
│ PrimaryChart 元件             │ 產業/市場/代號  │
│ 時間軸 + MA/RSI/Volume toggle │              │
├─────────────────────────────┼──────────────┤
│ 財報分析 (8col)               │ 融資融券 (4col) │
│ 健康度雷達圖 + 關鍵比率        │ 餘額/使用率     │
├─────────────────────────────┴──────────────┤
│ 營收趨勢 (12col)                             │
│ 月營收長條圖 + YoY 成長率                      │
└─────────────────────────────────────────────┘
```

- 所有面板用 GlassPanel 包裝
- 保留全部 hooks：`usePrices()`, `useCompanyInfo()`, `useFinancialAnalysis()`, `useMarginData()`, `useRevenue()`

### 4.6 登入頁 `/login`

- 全螢幕黑底（暗色）/ 白底+紅色 accent（淺色）
- 居中 GlassPanel 表單
- Logo 在頂部
- ClippedButton 「登入」(red-solid) / 「註冊」(white-solid)
- 保留 `useAuth()` 邏輯

### 4.7 熱力圖全頁 `/heatmap`（從首頁 Heatmap 面板點擊展開）

- 全寬 GlassPanel
- 接入 `useHeatmap()` 真實資料
- 點擊產業展開成份股列表

### 4.8 三大法人詳情 `/institutional`（從首頁摘要面板點擊進入）

- 股票搜尋 + 日期範圍選擇
- 外資/投信/自營商買賣超表格
- 接入 `useInstitutional()` 真實資料

---

## 5. 檔案結構遷移

### 遷移前（現有）
```
src/
├── app/
│   ├── page.tsx              # 首頁
│   ├── backtest/
│   ├── compare/
│   ├── heatmap/
│   ├── institutional/
│   ├── login/
│   ├── low-base/
│   ├── notifications/
│   ├── portfolio/
│   ├── scanner/
│   ├── screener/
│   ├── stocks/[symbol]/
│   ├── watchlist/
│   └── stratos/              # STRATOS demo
├── components/
│   ├── nav-bar.tsx
│   ├── command-palette.tsx
│   └── ui/
└── contexts/
```

### 遷移後
```
src/
├── app/
│   ├── layout.tsx            # Rubik 字體 + 雙主題 Provider
│   ├── page.tsx              # 首頁 Dashboard (Markets)
│   ├── research/
│   │   ├── layout.tsx        # Sub-tab: Screener|Scanner|LowBase|Compare
│   │   ├── page.tsx          # Screener (預設)
│   │   ├── scanner/page.tsx
│   │   ├── low-base/page.tsx
│   │   └── compare/page.tsx
│   ├── portfolio/
│   │   ├── layout.tsx        # Sub-tab: Watchlist|Backtest|Test
│   │   ├── page.tsx          # Watchlist (預設)
│   │   ├── backtest/page.tsx
│   │   └── test/page.tsx
│   ├── alerts/page.tsx       # 通知管理
│   ├── stocks/[symbol]/
│   │   ├── page.tsx          # 個股詳情
│   │   └── financials/page.tsx
│   ├── heatmap/page.tsx      # 全頁熱力圖
│   ├── institutional/page.tsx
│   └── login/page.tsx
├── components/
│   ├── stratos/              # 共用 STRATOS 元件
│   │   ├── primitives.tsx    # GlassPanel, ClippedButton, KpiCard
│   │   ├── header.tsx        # StratosHeader + TickerStrip
│   │   ├── charts.tsx        # PrimaryChart, Sparkline, SectorHeatmap
│   │   ├── ambient.tsx       # AmbientBackground
│   │   └── sub-tabs.tsx      # 子頁面切換條
│   ├── command-palette.tsx   # 保留搜尋功能
│   └── ui/                   # 保留共用 UI (LoadingSpinner 等)
├── contexts/
│   ├── auth-context.tsx      # 不變
│   └── theme-context.tsx     # 擴展支援 STRATOS 雙主題
├── hooks/                    # 全部保留不變
├── i18n/                     # 保留，新增 STRATOS 相關翻譯 key
└── lib/
    └── api-client.ts         # 不變
```

---

## 6. 遷移階段

### Phase 1：基礎層（預計工作量最大）
1. 遷移 STRATOS 元件至 `src/components/stratos/`
2. 重寫 `layout.tsx`：Rubik 字體 + 雙主題 CSS 變數
3. 重寫 `StratosHeader`：接入真實導航 + 搜尋 + i18n
4. `TickerStrip` 接入 `useMarketIndices()` 真實資料
5. `GlassPanel` + `ClippedButton` 支援淺色模式
6. 新增 `SubTabs` 共用元件
7. i18n 新增導航相關翻譯 key

### Phase 2：首頁 + 核心頁面
1. 首頁 Dashboard 重建（4 指數面板 + Watchlist + Heatmap + Movers + News）
2. 個股詳情頁 STRATOS 化
3. 登入頁 STRATOS 化

### Phase 3：Research 頁面群
1. Screener 遷移
2. Scanner 遷移
3. Low Base 遷移
4. Compare 遷移
5. Research layout + SubTabs

### Phase 4：Portfolio + Alerts 頁面群
1. Watchlist 遷移（接入真實資料取代 mock）
2. Backtest 遷移
3. Portfolio Test 遷移
4. Alerts 遷移
5. Portfolio layout + SubTabs
6. Heatmap 全頁 + Institutional 詳情頁

---

## 7. 不變的部分

- 所有後端 API 端點
- 所有 React Query hooks（`src/hooks/`）
- `api-client.ts` 所有函式
- `auth-context.tsx` 認證邏輯
- `command-palette.tsx` 搜尋功能（UI 微調配合新主題）
- WebSocket 通知機制
- 本地儲存邏輯（watchlist, saved screens, theme）

---

## 8. 驗收標準

- [ ] 所有 14 頁功能可正常操作
- [ ] 暗色模式 STRATOS 風格一致
- [ ] 淺色模式紅色賽車主題一致
- [ ] i18n 中英切換正常
- [ ] 所有 API 資料正確顯示
- [ ] 首頁 4 大指數走勢圖正確渲染
- [ ] 導航 4 分類 + sub-tab 切換正常
- [ ] 搜尋功能（Command Palette）正常
- [ ] 響應式：1440px / 1024px / 768px / 375px
- [ ] keyboard 可達性 + focus ring
- [ ] Next.js build 無 TypeScript 錯誤
