# Financials Page Redesign Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 將財報頁面遷移至 STRATOS 風格，加入 4-tab 版面（總覽 / 損益表 / 資產負債表 / 現金流量表），總覽含 KPI + 健康評分 + 2×2 趨勢圖，報表 tab 含逐行明細 + sparkline。

**Architecture:** `page.tsx` 管理 tab state 與單次 API fetch，資料向下傳給兩個純呈現組件 `OverviewTab` 和 `StatementTab`（共用，依 `type` prop 決定顯示哪張報表）。無需後端改動，`GET /api/v1/financials/{symbol}` 已包含全部資料。

**Tech Stack:** Next.js 15 App Router, React, TanStack Query v5, recharts AreaChart（總覽趨勢圖）, inline SVG（sparkline），STRATOS primitives（GlassPanel、KpiCard）。

---

## File Map

| 檔案 | 動作 | 職責 |
|------|------|------|
| `frontend/src/app/stocks/[symbol]/financials/page.tsx` | Modify | tab state + data fetch + render tabs |
| `frontend/src/app/stocks/[symbol]/financials/components/OverviewTab.tsx` | Create | 4 KpiCard + 健康評分 + 2×2 趨勢圖 |
| `frontend/src/app/stocks/[symbol]/financials/components/StatementTab.tsx` | Create | 通用報表表格 + inline SVG sparkline |

---

## Task 1: 建立 OverviewTab 組件

**Files:**
- Create: `frontend/src/app/stocks/[symbol]/financials/components/OverviewTab.tsx`

### 完整實作

- [ ] **Step 1: 建立目錄**

```bash
mkdir -p frontend/src/app/stocks/\[symbol\]/financials/components
```

- [ ] **Step 2: 建立 OverviewTab.tsx**

```tsx
"use client";

import {
  AreaChart,
  Area,
  ResponsiveContainer,
  XAxis,
  Tooltip,
} from "recharts";
import type { FinancialRatios, HealthScore, FinancialStatement } from "@/lib/api-client";
import { GlassPanel, KpiCard } from "@/components/stratos/primitives";

interface OverviewTabProps {
  ratios: FinancialRatios[];
  healthScores: HealthScore[];
  cashFlows: FinancialStatement[];
}

function formatPct(v: string | null): string {
  if (!v) return "N/A";
  return `${(Number(v) * 100).toFixed(1)}%`;
}

function scoreColor(n: number, max: number) {
  const pct = (n / max) * 100;
  if (pct < 40) return "#ef4444";
  if (pct < 70) return "#eab308";
  return "#22c55e";
}

function CircularScore({ score }: { score: number }) {
  const radius = 48;
  const circ = 2 * Math.PI * radius;
  const progress = (score / 100) * circ;
  const color = scoreColor(score, 100);
  return (
    <div style={{ display: "flex", flexDirection: "column", alignItems: "center", gap: 8 }}>
      <svg width="120" height="120" viewBox="0 0 120 120">
        <circle cx="60" cy="60" r={radius} fill="none" stroke="rgba(255,255,255,0.04)" strokeWidth="9" />
        <circle
          cx="60" cy="60" r={radius} fill="none"
          stroke={color} strokeWidth="9"
          strokeDasharray={circ} strokeDashoffset={circ - progress}
          strokeLinecap="round" transform="rotate(-90 60 60)"
          style={{ filter: `drop-shadow(0 0 6px ${color}60)` }}
        />
        <text x="60" y="56" textAnchor="middle" fill={color} fontSize="26" fontWeight="700" fontFamily="monospace">
          {Math.round(score)}
        </text>
        <text x="60" y="74" textAnchor="middle" fill="#52525b" fontSize="10" fontFamily="monospace">
          / 100
        </text>
      </svg>
      <span style={{ fontSize: 9, letterSpacing: "0.12em", textTransform: "uppercase", color: "var(--text-muted)" }}>
        整體健康度
      </span>
    </div>
  );
}

function CategoryBar({ label, score, max }: { label: string; score: string; max: number }) {
  const n = Number(score);
  const pct = (n / max) * 100;
  const color = scoreColor(n, max);
  return (
    <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 10 }}>
      <span style={{ width: 64, fontSize: 10, color: "var(--text-muted)", fontWeight: 600, flexShrink: 0 }}>{label}</span>
      <div style={{ flex: 1, height: 5, background: "var(--border-subtle)", borderRadius: 9999, overflow: "hidden" }}>
        <div style={{ width: `${pct}%`, height: "100%", background: color, boxShadow: `0 0 6px ${color}40`, borderRadius: 9999 }} />
      </div>
      <span style={{ width: 40, fontSize: 10, fontWeight: 700, textAlign: "right", color, fontVariantNumeric: "tabular-nums" }}>
        {n.toFixed(1)}/{max}
      </span>
    </div>
  );
}

function TrendChart({ data, dataKey, color, label }: {
  data: { period: string; value: number }[];
  dataKey: string;
  color: string;
  label: string;
}) {
  const latest = data[data.length - 1]?.value;
  return (
    <div style={{ background: "var(--bg-secondary)", border: "1px solid var(--border-subtle)", padding: "12px 14px" }}>
      <div style={{ fontSize: 9, fontWeight: 700, letterSpacing: "0.12em", textTransform: "uppercase", color: "var(--text-muted)", marginBottom: 4 }}>
        {label}
      </div>
      <div style={{ fontSize: 18, fontWeight: 700, fontVariantNumeric: "tabular-nums", color, marginBottom: 8 }}>
        {latest != null ? `${(latest * 100).toFixed(1)}%` : "N/A"}
      </div>
      <ResponsiveContainer width="100%" height={56}>
        <AreaChart data={data} margin={{ top: 2, right: 2, left: 2, bottom: 2 }}>
          <defs>
            <linearGradient id={`grad-${label}`} x1="0" y1="0" x2="0" y2="1">
              <stop offset="5%" stopColor={color} stopOpacity={0.25} />
              <stop offset="95%" stopColor={color} stopOpacity={0} />
            </linearGradient>
          </defs>
          <XAxis dataKey="period" hide />
          <Tooltip
            contentStyle={{ background: "var(--bg-secondary)", border: "1px solid var(--border-subtle)", fontSize: 11 }}
            formatter={(v: number) => [`${(v * 100).toFixed(1)}%`, label]}
          />
          <Area type="monotone" dataKey="value" stroke={color} strokeWidth={1.5} fill={`url(#grad-${label})`} dot={false} />
        </AreaChart>
      </ResponsiveContainer>
    </div>
  );
}

function FCFTrendChart({ data }: { data: { period: string; value: number }[] }) {
  const latest = data[data.length - 1]?.value;
  const color = latest != null && latest >= 0 ? "#22c55e" : "#ef4444";
  const fmtBillion = (n: number) => {
    const b = n / 1e9;
    return `${b >= 0 ? "" : ""}${b.toFixed(1)}B`;
  };
  return (
    <div style={{ background: "var(--bg-secondary)", border: "1px solid var(--border-subtle)", padding: "12px 14px" }}>
      <div style={{ fontSize: 9, fontWeight: 700, letterSpacing: "0.12em", textTransform: "uppercase", color: "var(--text-muted)", marginBottom: 4 }}>
        自由現金流趨勢
      </div>
      <div style={{ fontSize: 18, fontWeight: 700, fontVariantNumeric: "tabular-nums", color, marginBottom: 8 }}>
        {latest != null ? fmtBillion(latest) : "N/A"}
      </div>
      <ResponsiveContainer width="100%" height={56}>
        <AreaChart data={data} margin={{ top: 2, right: 2, left: 2, bottom: 2 }}>
          <defs>
            <linearGradient id="grad-fcf" x1="0" y1="0" x2="0" y2="1">
              <stop offset="5%" stopColor={color} stopOpacity={0.25} />
              <stop offset="95%" stopColor={color} stopOpacity={0} />
            </linearGradient>
          </defs>
          <XAxis dataKey="period" hide />
          <Tooltip
            contentStyle={{ background: "var(--bg-secondary)", border: "1px solid var(--border-subtle)", fontSize: 11 }}
            formatter={(v: number) => [fmtBillion(v), "FCF"]}
          />
          <Area type="monotone" dataKey="value" stroke={color} strokeWidth={1.5} fill="url(#grad-fcf)" dot={false} />
        </AreaChart>
      </ResponsiveContainer>
    </div>
  );
}

export function OverviewTab({ ratios, healthScores, cashFlows }: OverviewTabProps) {
  const latest = ratios[0];
  const latestHealth = healthScores[0];

  // Build sorted time-series for trend charts (oldest → newest)
  const sorted = [...ratios].sort((a, b) => a.period.localeCompare(b.period));

  const grossData = sorted.map((r) => ({ period: r.period, value: Number(r.gross_margin ?? 0) }));
  const netData = sorted.map((r) => ({ period: r.period, value: Number(r.net_margin ?? 0) }));
  const roeData = sorted.map((r) => ({ period: r.period, value: Number(r.roe ?? 0) }));

  // FCF from cash_flows (oldest → newest)
  const fcfData = [...cashFlows]
    .sort((a, b) => a.period.localeCompare(b.period))
    .map((s) => ({ period: s.period, value: Number(s.data["Free Cash Flow"] ?? 0) }));

  // For KPI: revenue growth
  const revenueGrowth = latest?.revenue_growth ? Number(latest.revenue_growth) : null;
  const growthDir = revenueGrowth == null ? "flat" : revenueGrowth >= 0 ? "up" : "down";

  if (!latest) {
    return (
      <GlassPanel>
        <div style={{ padding: "40px 0", textAlign: "center", color: "var(--text-muted)" }}>暫無財務資料</div>
      </GlassPanel>
    );
  }

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 16 }}>
      {/* KPI Row */}
      <div style={{ display: "grid", gridTemplateColumns: "repeat(4, 1fr)", gap: 12 }}>
        <KpiCard
          label="毛利率"
          value={formatPct(latest.gross_margin)}
          delta={latest.period}
          direction="flat"
        />
        <KpiCard
          label="淨利率"
          value={formatPct(latest.net_margin)}
          delta={latest.period}
          direction="flat"
        />
        <KpiCard
          label="ROE"
          value={formatPct(latest.roe)}
          delta={latest.period}
          direction="flat"
        />
        <KpiCard
          label="營收成長率"
          value={formatPct(latest.revenue_growth)}
          delta={latest.period}
          direction={growthDir}
        />
      </div>

      {/* Health + Trend Grid */}
      <div style={{ display: "grid", gridTemplateColumns: "280px 1fr", gap: 16 }}>
        {/* Health Score Panel */}
        <GlassPanel title="財務健康評分">
          {latestHealth ? (
            <>
              <div style={{ display: "flex", justifyContent: "center", marginBottom: 20 }}>
                <CircularScore score={Number(latestHealth.total_score)} />
              </div>
              <CategoryBar label="獲利能力" score={latestHealth.profitability_score} max={25} />
              <CategoryBar label="營運效率" score={latestHealth.efficiency_score} max={25} />
              <CategoryBar label="財務槓桿" score={latestHealth.leverage_score} max={25} />
              <CategoryBar label="成長動能" score={latestHealth.growth_score} max={25} />
            </>
          ) : (
            <div style={{ color: "var(--text-muted)", fontSize: 12 }}>暫無健康評分</div>
          )}
        </GlassPanel>

        {/* 2×2 Trend Charts */}
        <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gridTemplateRows: "1fr 1fr", gap: 10 }}>
          <TrendChart data={grossData} dataKey="value" color="#22c55e" label="毛利率趨勢" />
          <TrendChart data={netData} dataKey="value" color="#22c55e" label="淨利率趨勢" />
          <TrendChart data={roeData} dataKey="value" color={Number(latest.roe ?? 0) >= 0.15 ? "#22c55e" : "#eab308"} label="ROE 趨勢" />
          <FCFTrendChart data={fcfData} />
        </div>
      </div>
    </div>
  );
}
```

- [ ] **Step 3: TypeScript 檢查**

```bash
cd frontend && npx tsc --noEmit 2>&1 | grep -A2 "OverviewTab"
```

Expected: 無錯誤輸出（或只有其他不相關的錯誤）

- [ ] **Step 4: Commit**

```bash
cd frontend && git add src/app/stocks/\[symbol\]/financials/components/OverviewTab.tsx
git commit -m "feat: add OverviewTab component for financials page"
```

---

## Task 2: 建立 StatementTab 組件

**Files:**
- Create: `frontend/src/app/stocks/[symbol]/financials/components/StatementTab.tsx`

### 完整實作

- [ ] **Step 1: 建立 StatementTab.tsx**

```tsx
"use client";

import type { FinancialStatement } from "@/lib/api-client";
import { GlassPanel } from "@/components/stratos/primitives";

interface StatementTabProps {
  statements: FinancialStatement[];
  type: "income" | "balance" | "cashflow";
}

// 各報表要顯示的科目（yfinance 欄位名稱）
const INCOME_KEYS = [
  "Total Revenue",
  "Gross Profit",
  "Operating Income",
  "Net Income",
  "Basic EPS",
  "EBITDA",
];

const BALANCE_KEYS = [
  "Total Assets",
  "Total Liabilities Net Minority Interest",
  "Stockholders Equity",
  "Cash And Cash Equivalents",
  "Total Debt",
  "Current Assets",
  "Current Liabilities",
];

const CASHFLOW_KEYS = [
  "Operating Cash Flow",
  "Investing Cash Flow",
  "Financing Cash Flow",
  "Free Cash Flow",
  "Capital Expenditure",
];

const KEY_MAP: Record<StatementTabProps["type"], string[]> = {
  income: INCOME_KEYS,
  balance: BALANCE_KEYS,
  cashflow: CASHFLOW_KEYS,
};

const LABEL_MAP: Record<string, string> = {
  "Total Revenue": "營業收入",
  "Gross Profit": "營業毛利",
  "Operating Income": "營業利益",
  "Net Income": "稅後淨利",
  "Basic EPS": "EPS",
  "EBITDA": "EBITDA",
  "Total Assets": "總資產",
  "Total Liabilities Net Minority Interest": "總負債",
  "Stockholders Equity": "股東權益",
  "Cash And Cash Equivalents": "現金及約當現金",
  "Total Debt": "總債務",
  "Current Assets": "流動資產",
  "Current Liabilities": "流動負債",
  "Operating Cash Flow": "營業現金流",
  "Investing Cash Flow": "投資現金流",
  "Financing Cash Flow": "融資現金流",
  "Free Cash Flow": "自由現金流",
  "Capital Expenditure": "資本支出",
};

function fmtVal(v: string | undefined): string {
  if (!v) return "—";
  const n = Number(v);
  if (!isFinite(n)) return "—";
  if (Math.abs(n) >= 1e12) return `${(n / 1e12).toFixed(2)}T`;
  if (Math.abs(n) >= 1e9) return `${(n / 1e9).toFixed(2)}B`;
  if (Math.abs(n) >= 1e6) return `${(n / 1e6).toFixed(2)}M`;
  return n.toLocaleString("en-US", { maximumFractionDigits: 2 });
}

function Sparkline({ values }: { values: number[] }) {
  if (values.length < 2) return <span style={{ color: "var(--text-muted)", fontSize: 10 }}>—</span>;
  const min = Math.min(...values);
  const max = Math.max(...values);
  const range = max - min || 1;
  const W = 80;
  const H = 28;
  const step = W / (values.length - 1);
  const pts = values
    .map((v, i) => `${i * step},${H - ((v - min) / range) * (H - 4) - 2}`)
    .join(" ");
  const last = values[values.length - 1];
  const prev = values[values.length - 2];
  const color = last >= prev ? "#22c55e" : "#ef4444";
  return (
    <svg width={W} height={H} viewBox={`0 0 ${W} ${H}`}>
      <polyline points={pts} fill="none" stroke={color} strokeWidth="1.5" strokeLinejoin="round" />
      <circle
        cx={(values.length - 1) * step}
        cy={H - ((last - min) / range) * (H - 4) - 2}
        r="2.5"
        fill={color}
      />
    </svg>
  );
}

export function StatementTab({ statements, type }: StatementTabProps) {
  if (!statements || statements.length === 0) {
    return (
      <GlassPanel>
        <div style={{ padding: "40px 0", textAlign: "center", color: "var(--text-muted)" }}>
          暫無報表資料
        </div>
      </GlassPanel>
    );
  }

  // 最近 4 期，最新在左
  const periods = statements.slice(0, 4);
  const keys = KEY_MAP[type];

  return (
    <GlassPanel noPadding>
      <div style={{ overflowX: "auto" }}>
        <table style={{ width: "100%", fontSize: 12, borderCollapse: "collapse" }}>
          <thead>
            <tr style={{ borderBottom: "1px solid var(--border-subtle)" }}>
              <th style={{ padding: "10px 16px", textAlign: "left", fontSize: 10, fontWeight: 700, letterSpacing: "0.1em", textTransform: "uppercase", color: "var(--text-muted)" }}>
                科目
              </th>
              {periods.map((s) => (
                <th key={s.period} style={{ padding: "10px 16px", textAlign: "right", fontSize: 10, fontWeight: 700, letterSpacing: "0.1em", textTransform: "uppercase", color: "var(--text-muted)", fontVariantNumeric: "tabular-nums" }}>
                  {s.period}
                </th>
              ))}
              <th style={{ padding: "10px 16px", textAlign: "center", fontSize: 10, fontWeight: 700, letterSpacing: "0.1em", textTransform: "uppercase", color: "var(--text-muted)" }}>
                趨勢
              </th>
            </tr>
          </thead>
          <tbody>
            {keys.map((key, i) => {
              const values = periods.map((s) => Number(s.data[key] ?? ""));
              const validValues = periods
                .slice()
                .reverse()
                .map((s) => Number(s.data[key] ?? ""))
                .filter((v) => isFinite(v));

              return (
                <tr
                  key={key}
                  style={{
                    borderBottom: "1px solid var(--border-subtle)",
                    background: i % 2 === 0 ? "transparent" : "rgba(255,255,255,0.01)",
                  }}
                >
                  <td style={{ padding: "10px 16px", fontWeight: 700, color: "var(--foreground)" }}>
                    {LABEL_MAP[key] ?? key}
                    <span style={{ display: "block", fontSize: 9, color: "var(--text-muted)", fontWeight: 400, marginTop: 1 }}>
                      {key}
                    </span>
                  </td>
                  {periods.map((s) => {
                    const v = s.data[key];
                    const n = Number(v ?? "");
                    const isNeg = isFinite(n) && n < 0;
                    return (
                      <td key={s.period} style={{ padding: "10px 16px", textAlign: "right", fontVariantNumeric: "tabular-nums", fontFamily: "monospace", color: isNeg ? "var(--stock-down)" : "var(--foreground)" }}>
                        {fmtVal(v)}
                      </td>
                    );
                  })}
                  <td style={{ padding: "10px 16px", textAlign: "center" }}>
                    <Sparkline values={validValues} />
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </GlassPanel>
  );
}
```

- [ ] **Step 2: TypeScript 檢查**

```bash
cd frontend && npx tsc --noEmit 2>&1 | grep -A2 "StatementTab"
```

Expected: 無相關錯誤

- [ ] **Step 3: Commit**

```bash
git add src/app/stocks/\[symbol\]/financials/components/StatementTab.tsx
git commit -m "feat: add StatementTab component with sparklines for financials page"
```

---

## Task 3: 改寫 page.tsx — tab 整合

**Files:**
- Modify: `frontend/src/app/stocks/[symbol]/financials/page.tsx`

### 完整實作

- [ ] **Step 1: 改寫 page.tsx**

用以下內容完整取代 `frontend/src/app/stocks/[symbol]/financials/page.tsx`：

```tsx
"use client";

import { useState } from "react";
import { useParams } from "next/navigation";
import { LoadingSpinner } from "@/components/ui/loading";
import { ErrorState } from "@/components/ui/empty-state";
import { getErrorMessage } from "@/lib/type-guards";
import { useFinancialAnalysis } from "@/hooks/use-market-data";
import { AmbientBackground } from "@/components/stratos/ambient";
import { OverviewTab } from "./components/OverviewTab";
import { StatementTab } from "./components/StatementTab";

type TabId = "overview" | "income" | "balance" | "cashflow";

const TABS: { id: TabId; label: string }[] = [
  { id: "overview", label: "總覽" },
  { id: "income", label: "損益表" },
  { id: "balance", label: "資產負債表" },
  { id: "cashflow", label: "現金流量表" },
];

export default function FinancialsPage() {
  const params = useParams<{ symbol: string }>();
  const symbol = decodeURIComponent(params.symbol);
  const { data, isLoading, error: queryError } = useFinancialAnalysis(symbol);
  const error = queryError ? getErrorMessage(queryError) : null;
  const [activeTab, setActiveTab] = useState<TabId>("overview");

  if (isLoading) return <LoadingSpinner text="載入財務資料中..." fullPage />;
  if (error) return <div className="p-6 max-w-md mx-auto"><ErrorState message={error} /></div>;
  if (!data) return <div className="p-6 text-center text-[var(--text-muted)] text-sm">無資料</div>;

  return (
    <div className="relative flex-1 overflow-y-auto">
      <AmbientBackground />

      {/* Inner Tabs */}
      <div
        style={{
          display: "flex",
          gap: 2,
          padding: "12px 24px 0",
          borderBottom: "1px solid var(--border-subtle)",
          background: "var(--bg-secondary)",
        }}
      >
        {TABS.map((tab) => (
          <button
            key={tab.id}
            onClick={() => setActiveTab(tab.id)}
            style={{
              padding: "6px 18px",
              fontSize: 11,
              fontWeight: 700,
              letterSpacing: "0.08em",
              textTransform: "uppercase",
              border: "none",
              cursor: "pointer",
              background: activeTab === tab.id ? "var(--accent-cyan)" : "transparent",
              color: activeTab === tab.id ? "#09090b" : "var(--text-muted)",
              transition: "all 0.15s",
            }}
          >
            {tab.label}
          </button>
        ))}
      </div>

      {/* Content */}
      <div style={{ padding: 24 }}>
        {activeTab === "overview" && (
          <OverviewTab ratios={data.ratios} healthScores={data.health_scores} cashFlows={data.financials.cash_flows} />
        )}
        {activeTab === "income" && (
          <StatementTab statements={data.financials.income_statements} type="income" />
        )}
        {activeTab === "balance" && (
          <StatementTab statements={data.financials.balance_sheets} type="balance" />
        )}
        {activeTab === "cashflow" && (
          <StatementTab statements={data.financials.cash_flows} type="cashflow" />
        )}
      </div>
    </div>
  );
}
```

- [ ] **Step 2: TypeScript 全域檢查**

```bash
cd frontend && npx tsc --noEmit 2>&1
```

Expected: 0 errors（或只有與本次改動無關的現有錯誤）

- [ ] **Step 3: 啟動 dev server 驗證**

```bash
cd frontend && npm run dev
```

開啟 `http://localhost:3000/stocks/2330/financials`，確認：
1. 頁面有 4 個 tab 按鈕（總覽 / 損益表 / 資產負債表 / 現金流量表）
2. 總覽 tab：4 KpiCard 顯示比率、健康評分圓圈 + 4 bar、2×2 趨勢圖
3. 損益表 tab：表格有科目名稱、4 期數字、右側 sparkline
4. 資產負債表 / 現金流量表 tab 同上格式，科目不同
5. 無 console error

- [ ] **Step 4: Commit**

```bash
git add src/app/stocks/\[symbol\]/financials/page.tsx
git commit -m "feat: financials page STRATOS migration with 4-tab layout"
```

---

## 自我驗證清單（每個 Task 完成後執行）

- [ ] `cd frontend && npx tsc --noEmit` — 無新增 TypeScript 錯誤
- [ ] 瀏覽器開啟 `/stocks/2330/financials` — 頁面正常載入
- [ ] 4 個 tab 均可切換，無空白頁或 crash
- [ ] 報表 tab 的 sparkline SVG 正確顯示（非空、顏色正確）
- [ ] 無 `console.error` 輸出
