# Financials Page Redesign Spec

## Goal
將現有財報頁面遷移至 STRATOS 風格，並新增損益表 / 資產負債表 / 現金流量表逐行明細 tab，含 sparkline 趨勢圖。

## Architecture

**Files to touch:**
- `frontend/src/app/stocks/[symbol]/financials/page.tsx` — tab state 管理 + 單次 data fetch
- `frontend/src/app/stocks/[symbol]/financials/components/OverviewTab.tsx` — 新增
- `frontend/src/app/stocks/[symbol]/financials/components/StatementTab.tsx` — 新增

**Data source:** `GET /api/v1/financials/{symbol}` 已包含全部資料，無需後端改動。

## Tab Structure
1. **總覽** — KPI cards + 健康評分 + 2×2 趨勢圖
2. **損益表** — `financials.income_statements[]`
3. **資產負債表** — `financials.balance_sheets[]`
4. **現金流量表** — `financials.cash_flows[]`

## OverviewTab Layout
```
[ KPI: 年營收 | 毛利率 | 淨利率 | ROE ]   ← 4 KpiCard

[ 健康評分 CircularScore + 4 CategoryBar ] [ 2×2 AreaChart grid ]
  左欄 280px                                 右欄 flex-1
    - 獲利能力 bar                             - 毛利率趨勢
    - 營運效率 bar                             - 淨利率趨勢
    - 財務槓桿 bar                             - ROE 趨勢
    - 成長動能 bar                             - 自由現金流趨勢
```

KPI 數值來源：
- 年營收 = `financials.income_statements[0].data["Total Revenue"]`
- 毛利率 / 淨利率 / ROE = `ratios[0]`

趨勢圖資料：`ratios[]` 依 period 排序，X 軸為 period string。

## StatementTab Layout
共用組件，接收 `type: "income" | "balance" | "cashflow"` prop。

```
科目名稱 | 期間1 | 期間2 | 期間3 | 期間4 | [sparkline]
```

- 顯示最近 4 期（annual 或 quarterly 由資料決定）
- sparkline：80×28 SVG polyline，用 `recharts` Sparkline 或手寫 SVG
- 正值顯示 `var(--stock-up)` 色，負值 `var(--stock-down)` 色

## Style Rules
- 所有容器改用 `GlassPanel`
- `bg-[var(--card-bg)] rounded-lg` → `GlassPanel`
- 不使用 `card-hover`, `card-bg` class，改用 CSS variables
- Tab 切換用 `SubTabs` primitive（已存在）
- 頂部舊版導覽列（chart / financials link）移除，由 stock page layout 的 SubTabs 處理
