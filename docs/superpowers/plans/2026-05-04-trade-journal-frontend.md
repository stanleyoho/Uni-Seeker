# Trade Journal — Frontend Implementation Plan (Plan B)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build all frontend pages for the Trade Journal module — Dashboard, Account Detail, Trade History, Group View, and a global Add Trade Modal — connected to the backend API built in Plan A.

**Architecture:** Next.js App Router, TanStack Query for data fetching, STRATOS dark theme (GlassPanel, ClippedButton, KpiCard), recharts for AreaChart, inline CSS via CSS variables. No new dependencies required.

**Tech Stack:** Next.js 15 (App Router), TypeScript, TanStack Query v5, recharts, CSS variables, lucide-react icons

---

## File Map

| Action | Path | Responsibility |
|--------|------|----------------|
| Modify | `frontend/src/lib/api-client.ts` | Add journal types + API functions |
| Modify | `frontend/src/lib/query-keys.ts` | Add `journal` namespace |
| Create | `frontend/src/hooks/use-journal.ts` | All React Query hooks for journal |
| Modify | `frontend/src/components/stratos/header.tsx` | Add 交易日誌 nav link |
| Modify | `frontend/src/i18n/locales/zh-TW.json` | Add `journal` translation key |
| Modify | `frontend/src/i18n/locales/en.json` | Add `journal` translation key |
| Create | `frontend/src/app/journal/layout.tsx` | SubTabs: 總覽/帳戶/群組 |
| Create | `frontend/src/app/journal/page.tsx` | Dashboard: KPI row + chart + alerts + account cards |
| Create | `frontend/src/components/journal/add-trade-modal.tsx` | Global add-trade modal |
| Create | `frontend/src/app/journal/accounts/page.tsx` | Account list page |
| Create | `frontend/src/app/journal/accounts/[id]/page.tsx` | Account detail: holdings table |
| Create | `frontend/src/app/journal/accounts/[id]/trades/page.tsx` | Trade history table |
| Create | `frontend/src/app/journal/groups/page.tsx` | Group list page |
| Create | `frontend/src/app/journal/groups/[id]/page.tsx` | Group detail: merged holdings + rebalance |

---

## Task 0: API Layer — Types, Client Functions, Query Keys, Hooks

**Files:**
- Modify: `frontend/src/lib/api-client.ts`
- Modify: `frontend/src/lib/query-keys.ts`
- Create: `frontend/src/hooks/use-journal.ts`

- [ ] **Step 1: Add journal types and API functions to `api-client.ts`**

Append to the end of `frontend/src/lib/api-client.ts`:

```typescript
// ---------------------------------------------------------------------------
// Journal — Types
// ---------------------------------------------------------------------------

export interface JournalAccount {
  id: number;
  name: string;
  broker: string | null;
  market: "TW" | "US" | "CRYPTO";
  currency: string;
  description: string | null;
  created_at: string;
}

export interface JournalPosition {
  id: number;
  account_id: number;
  symbol: string;
  market: string;
  currency: string;
  quantity: string;        // Decimal as string from backend
  avg_cost_fifo: string | null;
  total_cost: string | null;
  realized_pnl: string;
  is_closed: boolean;
}

export interface JournalAccountDetail {
  account: JournalAccount;
  positions: JournalPosition[];
}

export interface JournalTrade {
  id: number;
  account_id: number;
  symbol: string;
  market: string;
  action: "BUY" | "SELL" | "DIVIDEND" | "SPLIT";
  date: string;
  price: string | null;
  quantity: string | null;
  fee: string;
  tax: string;
  trade_fx_rate: string | null;
  tags: string[];
  note: string | null;
  created_at: string;
}

export interface JournalTradeListResponse {
  total: number;
  items: JournalTrade[];
}

export interface JournalTradeCreate {
  symbol: string;
  market: "TW" | "US" | "CRYPTO";
  action: "BUY" | "SELL" | "DIVIDEND" | "SPLIT";
  date: string;
  price?: string | null;
  quantity?: string | null;
  fee?: string;
  tax?: string;
  trade_fx_rate?: string | null;
  tags?: string[];
  note?: string | null;
  split_ratio?: string | null;
}

export interface JournalAccountCreate {
  name: string;
  broker?: string | null;
  market: "TW" | "US" | "CRYPTO";
  currency: "TWD" | "USD" | "USDT" | "BTC" | "ETH";
  description?: string | null;
}

export interface JournalGroupMember {
  account_id: number;
  target_weight: string | null;
  account: JournalAccount;
}

export interface JournalGroup {
  id: number;
  name: string;
  description: string | null;
  base_currency: string;
  members: JournalGroupMember[];
}

export interface JournalAllocationRule {
  id: number;
  symbol: string;
  target_weight: string;
  lower_threshold: string;
  upper_threshold: string;
  is_active: boolean;
}

export interface JournalRebalanceAlert {
  scope: "account" | "group";
  scope_id: number;
  scope_name: string;
  symbol: string;
  current_weight: string;
  target_weight: string;
  deviation: string;    // positive = over, negative = under
  direction: "over" | "under";
}

export interface JournalAlertsResponse {
  alerts: JournalRebalanceAlert[];
}

// ---------------------------------------------------------------------------
// Journal — API functions
// ---------------------------------------------------------------------------

export async function fetchJournalAccounts(): Promise<JournalAccount[]> {
  return apiFetch<JournalAccount[]>(`${API_BASE}/journal/accounts`);
}

export async function fetchJournalAccount(id: number): Promise<JournalAccountDetail> {
  return apiFetch<JournalAccountDetail>(`${API_BASE}/journal/accounts/${id}`);
}

export async function createJournalAccount(body: JournalAccountCreate): Promise<JournalAccount> {
  return apiFetch<JournalAccount>(`${API_BASE}/journal/accounts`, {
    method: "POST",
    body: JSON.stringify(body),
  });
}

export async function fetchJournalTrades(
  accountId: number,
  params?: { symbol?: string; page?: number; page_size?: number },
): Promise<JournalTradeListResponse> {
  const qs = new URLSearchParams();
  if (params?.symbol) qs.set("symbol", params.symbol);
  if (params?.page) qs.set("page", String(params.page));
  if (params?.page_size) qs.set("page_size", String(params.page_size));
  const query = qs.toString() ? `?${qs.toString()}` : "";
  return apiFetch<JournalTradeListResponse>(
    `${API_BASE}/journal/accounts/${accountId}/trades${query}`,
  );
}

export async function createJournalTrade(
  accountId: number,
  body: JournalTradeCreate,
): Promise<JournalTrade> {
  return apiFetch<JournalTrade>(`${API_BASE}/journal/accounts/${accountId}/trades`, {
    method: "POST",
    body: JSON.stringify(body),
  });
}

export async function fetchJournalGroups(): Promise<JournalGroup[]> {
  return apiFetch<JournalGroup[]>(`${API_BASE}/journal/groups`);
}

export async function fetchJournalGroup(id: number): Promise<JournalGroup> {
  return apiFetch<JournalGroup>(`${API_BASE}/journal/groups/${id}`);
}

export async function createJournalGroup(body: {
  name: string;
  description?: string | null;
  base_currency?: string;
  members?: { account_id: number; target_weight?: string | null }[];
}): Promise<JournalGroup> {
  return apiFetch<JournalGroup>(`${API_BASE}/journal/groups`, {
    method: "POST",
    body: JSON.stringify(body),
  });
}

export async function fetchJournalAlerts(): Promise<JournalAlertsResponse> {
  return apiFetch<JournalAlertsResponse>(`${API_BASE}/journal/alerts`);
}
```

- [ ] **Step 2: Add `journal` namespace to `query-keys.ts`**

In `frontend/src/lib/query-keys.ts`, add before the closing `} as const;`:

```typescript
  journal: {
    all: ["journal"] as const,
    accounts: () => [...queryKeys.journal.all, "accounts"] as const,
    account: (id: number) => [...queryKeys.journal.all, "account", id] as const,
    trades: (accountId: number, symbol?: string, page?: number) =>
      [...queryKeys.journal.all, "trades", accountId, symbol, page] as const,
    groups: () => [...queryKeys.journal.all, "groups"] as const,
    group: (id: number) => [...queryKeys.journal.all, "group", id] as const,
    alerts: () => [...queryKeys.journal.all, "alerts"] as const,
  },
```

- [ ] **Step 3: Create `frontend/src/hooks/use-journal.ts`**

```typescript
"use client";

import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import {
  fetchJournalAccounts,
  fetchJournalAccount,
  createJournalAccount,
  fetchJournalTrades,
  createJournalTrade,
  fetchJournalGroups,
  fetchJournalGroup,
  createJournalGroup,
  fetchJournalAlerts,
  type JournalAccountCreate,
  type JournalTradeCreate,
} from "@/lib/api-client";
import { queryKeys } from "@/lib/query-keys";

export function useJournalAccounts() {
  return useQuery({
    queryKey: queryKeys.journal.accounts(),
    queryFn: fetchJournalAccounts,
    staleTime: 30 * 1000,
    placeholderData: [],
  });
}

export function useJournalAccount(id: number) {
  return useQuery({
    queryKey: queryKeys.journal.account(id),
    queryFn: () => fetchJournalAccount(id),
    staleTime: 15 * 1000,
    enabled: id > 0,
  });
}

export function useCreateJournalAccount() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: JournalAccountCreate) => createJournalAccount(body),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: queryKeys.journal.accounts() });
    },
  });
}

export function useJournalTrades(
  accountId: number,
  opts?: { symbol?: string; page?: number; page_size?: number },
) {
  return useQuery({
    queryKey: queryKeys.journal.trades(accountId, opts?.symbol, opts?.page),
    queryFn: () => fetchJournalTrades(accountId, opts),
    staleTime: 15 * 1000,
    enabled: accountId > 0,
    placeholderData: { total: 0, items: [] },
  });
}

export function useCreateJournalTrade(accountId: number) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: JournalTradeCreate) => createJournalTrade(accountId, body),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: queryKeys.journal.account(accountId) });
      qc.invalidateQueries({ queryKey: queryKeys.journal.trades(accountId) });
      qc.invalidateQueries({ queryKey: queryKeys.journal.alerts() });
    },
  });
}

export function useJournalGroups() {
  return useQuery({
    queryKey: queryKeys.journal.groups(),
    queryFn: fetchJournalGroups,
    staleTime: 60 * 1000,
    placeholderData: [],
  });
}

export function useJournalGroup(id: number) {
  return useQuery({
    queryKey: queryKeys.journal.group(id),
    queryFn: () => fetchJournalGroup(id),
    staleTime: 30 * 1000,
    enabled: id > 0,
  });
}

export function useJournalAlerts() {
  return useQuery({
    queryKey: queryKeys.journal.alerts(),
    queryFn: fetchJournalAlerts,
    staleTime: 60 * 1000,
    placeholderData: { alerts: [] },
  });
}
```

- [ ] **Step 4: Verify TypeScript compiles (no errors in new files)**

```bash
cd /Users/stanley/Uni-Seeker/frontend && npx tsc --noEmit 2>&1 | grep -E "journal|query-keys" | head -20
```
Expected: no journal-related errors.

- [ ] **Step 5: Commit**

```bash
cd /Users/stanley/Uni-Seeker && git add frontend/src/lib/api-client.ts frontend/src/lib/query-keys.ts frontend/src/hooks/use-journal.ts
git commit -m "feat(journal-fe): API client types, query keys, React Query hooks"
```

---

## Task 1: Navigation — Add 交易日誌 Link

**Files:**
- Modify: `frontend/src/components/stratos/header.tsx`
- Modify: `frontend/src/i18n/locales/zh-TW.json`
- Modify: `frontend/src/i18n/locales/en.json`

- [ ] **Step 1: Add translation key to zh-TW.json**

In the `nav` object, add:
```json
"journal": "交易日誌"
```

- [ ] **Step 2: Add translation key to en.json**

In the `nav` object, add:
```json
"journal": "Journal"
```

- [ ] **Step 3: Add nav link to header.tsx**

Find the `navLinks` array in `frontend/src/components/stratos/header.tsx`:
```typescript
const navLinks = [
  { href: "/", label: t.nav.markets ?? "Markets" },
  { href: "/research", label: t.nav.research ?? "Research" },
  { href: "/portfolio", label: t.nav.portfolio ?? "Portfolio" },
];
```

Change to:
```typescript
const navLinks = [
  { href: "/", label: t.nav.markets ?? "Markets" },
  { href: "/research", label: t.nav.research ?? "Research" },
  { href: "/portfolio", label: t.nav.portfolio ?? "Portfolio" },
  { href: "/journal", label: t.nav.journal ?? "Journal" },
];
```

- [ ] **Step 4: Commit**

```bash
cd /Users/stanley/Uni-Seeker && git add frontend/src/components/stratos/header.tsx frontend/src/i18n/locales/zh-TW.json frontend/src/i18n/locales/en.json
git commit -m "feat(journal-fe): add 交易日誌 nav link"
```

---

## Task 2: Journal Layout + Dashboard Page

**Files:**
- Create: `frontend/src/app/journal/layout.tsx`
- Create: `frontend/src/app/journal/page.tsx`

- [ ] **Step 1: Create `frontend/src/app/journal/layout.tsx`**

```typescript
"use client";

import { SubTabs } from "@/components/stratos/sub-tabs";

export default function JournalLayout({ children }: { children: React.ReactNode }) {
  const tabs = [
    { href: "/journal", label: "總覽" },
    { href: "/journal/accounts", label: "帳戶" },
    { href: "/journal/groups", label: "群組" },
  ];

  return (
    <div className="flex-1 flex flex-col min-h-0 bg-[var(--background)]">
      <SubTabs tabs={tabs} />
      {children}
    </div>
  );
}
```

- [ ] **Step 2: Create `frontend/src/app/journal/page.tsx`**

```typescript
"use client";

import { AmbientBackground } from "@/components/stratos/ambient";
import { GlassPanel, KpiCard } from "@/components/stratos/primitives";
import {
  useJournalAccounts,
  useJournalAlerts,
} from "@/hooks/use-journal";
import Link from "next/link";
import {
  AreaChart,
  Area,
  ResponsiveContainer,
  XAxis,
  YAxis,
  Tooltip,
} from "recharts";

/* Dummy asset curve for Phase 1 (real snapshots in Plan C) */
const DUMMY_CURVE = [
  { date: "01/01", value: 3000000 },
  { date: "01/15", value: 3050000 },
  { date: "02/01", value: 3020000 },
  { date: "02/15", value: 3180000 },
  { date: "03/01", value: 3240000 },
  { date: "03/15", value: 3200000 },
  { date: "04/01", value: 3350000 },
];

function fmt(n: number, decimals = 0) {
  return n.toLocaleString("zh-TW", { maximumFractionDigits: decimals });
}

export default function JournalDashboard() {
  const { data: accounts = [] } = useJournalAccounts();
  const { data: alertsData } = useJournalAlerts();
  const alerts = alertsData?.alerts ?? [];

  /* Aggregate totals from account positions (cost-based, Phase 1) */
  const totalValue = 0; // Phase 2: from portfolio_snapshots
  const unrealizedPnl = 0;
  const realizedPnl = 0;

  return (
    <div className="relative flex-1 overflow-y-auto p-6 space-y-6">
      <AmbientBackground />

      {/* KPI Row */}
      <div className="grid grid-cols-2 md:grid-cols-5 gap-4">
        <KpiCard
          label="總市值 (TWD)"
          value={totalValue === 0 ? "—" : fmt(totalValue)}
          delta="新增交易後計算"
          direction="flat"
        />
        <KpiCard
          label="未實現損益"
          value={unrealizedPnl === 0 ? "—" : fmt(unrealizedPnl)}
          delta="成本加權"
          direction="flat"
        />
        <KpiCard
          label="已實現損益"
          value={realizedPnl === 0 ? "—" : fmt(realizedPnl)}
          delta="本年度"
          direction="flat"
        />
        <KpiCard label="週增幅" value="—" delta="需快照資料" direction="flat" />
        <KpiCard label="年增幅" value="—" delta="需快照資料" direction="flat" />
      </div>

      {/* Asset Curve (placeholder until snapshot cron is implemented) */}
      <GlassPanel title="資產曲線" noPadding>
        <div style={{ padding: "16px 20px 4px" }}>
          <span style={{ fontSize: 11, color: "var(--text-muted)" }}>
            Phase 1 示意圖 — 日快照啟用後顯示真實資料
          </span>
        </div>
        <div style={{ height: 140, padding: "0 8px 16px" }}>
          <ResponsiveContainer width="100%" height="100%">
            <AreaChart data={DUMMY_CURVE}>
              <defs>
                <linearGradient id="jGrad" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="5%" stopColor="var(--accent-cyan)" stopOpacity={0.25} />
                  <stop offset="95%" stopColor="var(--accent-cyan)" stopOpacity={0} />
                </linearGradient>
              </defs>
              <XAxis
                dataKey="date"
                tick={{ fill: "var(--text-muted)", fontSize: 10 }}
                axisLine={false}
                tickLine={false}
              />
              <YAxis hide />
              <Tooltip
                contentStyle={{
                  background: "var(--bg-secondary)",
                  border: "1px solid var(--border-subtle)",
                  fontSize: 12,
                  color: "var(--foreground)",
                }}
                formatter={(v: number) => [fmt(v), "市值"]}
              />
              <Area
                type="monotone"
                dataKey="value"
                stroke="var(--accent-cyan)"
                strokeWidth={1.5}
                fill="url(#jGrad)"
              />
            </AreaChart>
          </ResponsiveContainer>
        </div>
      </GlassPanel>

      {/* Bottom Grid: Alerts + Account Cards */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">

        {/* Rebalance Alerts */}
        <GlassPanel title="再平衡警示">
          {alerts.length === 0 ? (
            <div style={{ fontSize: 13, color: "var(--text-muted)", padding: "8px 0" }}>
              所有持倉均在目標區間內
            </div>
          ) : (
            <div className="space-y-2">
              {alerts.map((a, i) => {
                const dev = Number(a.deviation);
                const isOver = a.direction === "over";
                return (
                  <div
                    key={i}
                    style={{
                      display: "flex",
                      justifyContent: "space-between",
                      alignItems: "center",
                      padding: "8px 12px",
                      background: isOver ? "rgba(239,68,68,0.07)" : "rgba(245,158,11,0.07)",
                      borderLeft: `3px solid ${isOver ? "var(--stock-down)" : "#f59e0b"}`,
                      fontSize: 12,
                    }}
                  >
                    <div>
                      <span style={{ fontWeight: 700, color: "var(--foreground)" }}>
                        {a.symbol}
                      </span>
                      <span style={{ color: "var(--text-muted)", marginLeft: 8, fontSize: 11 }}>
                        {a.scope_name}
                      </span>
                    </div>
                    <span
                      style={{
                        color: isOver ? "var(--stock-down)" : "#f59e0b",
                        fontFamily: "monospace",
                        fontWeight: 700,
                      }}
                    >
                      {isOver ? "+" : ""}{(dev * 100).toFixed(1)}%
                    </span>
                  </div>
                );
              })}
            </div>
          )}
        </GlassPanel>

        {/* Account Cards */}
        <GlassPanel title="帳戶總覽">
          {accounts.length === 0 ? (
            <div style={{ fontSize: 13, color: "var(--text-muted)" }}>
              尚未新增帳戶。前往「帳戶」標籤新增第一個帳戶。
            </div>
          ) : (
            <div className="space-y-2">
              {accounts.map((acc) => (
                <Link key={acc.id} href={`/journal/accounts/${acc.id}`}>
                  <div
                    style={{
                      display: "grid",
                      gridTemplateColumns: "1fr auto",
                      alignItems: "center",
                      padding: "10px 14px",
                      background: "var(--bg-secondary)",
                      border: "1px solid var(--border-subtle)",
                      cursor: "pointer",
                      transition: "border-color 0.15s",
                    }}
                    onMouseEnter={(e) =>
                      (e.currentTarget.style.borderColor = "var(--accent-cyan)")
                    }
                    onMouseLeave={(e) =>
                      (e.currentTarget.style.borderColor = "var(--border-subtle)")
                    }
                  >
                    <div>
                      <div style={{ fontWeight: 700, fontSize: 13, color: "var(--foreground)" }}>
                        {acc.name}
                      </div>
                      <div style={{ fontSize: 11, color: "var(--text-muted)", marginTop: 2 }}>
                        {acc.broker && `${acc.broker} · `}{acc.market} · {acc.currency}
                      </div>
                    </div>
                    <span style={{ color: "var(--text-muted)", fontSize: 12 }}>→</span>
                  </div>
                </Link>
              ))}
            </div>
          )}
        </GlassPanel>
      </div>
    </div>
  );
}
```

- [ ] **Step 3: Verify pages load without build errors**

```bash
cd /Users/stanley/Uni-Seeker/frontend && npx tsc --noEmit 2>&1 | grep -i "journal" | head -20
```
Expected: no errors.

- [ ] **Step 4: Commit**

```bash
cd /Users/stanley/Uni-Seeker && git add frontend/src/app/journal/
git commit -m "feat(journal-fe): layout with SubTabs + dashboard with KPI, chart, alerts, account cards"
```

---

## Task 3: AddTradeModal Component

**Files:**
- Create: `frontend/src/components/journal/add-trade-modal.tsx`

- [ ] **Step 1: Create `frontend/src/components/journal/add-trade-modal.tsx`**

```typescript
"use client";

import { useState } from "react";
import { ClippedButton } from "@/components/stratos/primitives";
import { useCreateJournalTrade } from "@/hooks/use-journal";
import type { JournalAccount } from "@/lib/api-client";

interface AddTradeModalProps {
  accounts: JournalAccount[];
  defaultAccountId?: number;
  onClose: () => void;
}

const inputCls =
  "w-full px-3 py-2 bg-[var(--bg-secondary)] border border-[var(--border-subtle)] text-sm text-[var(--foreground)] placeholder-[var(--text-muted)] focus:border-[var(--accent-cyan)] outline-none tabular-nums";

const labelCls =
  "text-[10px] font-bold uppercase tracking-[0.1em] text-[var(--text-muted)] mb-1 block";

type Action = "BUY" | "SELL" | "DIVIDEND" | "SPLIT";

const ACTION_COLORS: Record<Action, string> = {
  BUY: "var(--stock-up)",
  SELL: "var(--stock-down)",
  DIVIDEND: "#f59e0b",
  SPLIT: "var(--accent-cyan)",
};

export function AddTradeModal({ accounts, defaultAccountId, onClose }: AddTradeModalProps) {
  const [action, setAction] = useState<Action>("BUY");
  const [accountId, setAccountId] = useState<number>(defaultAccountId ?? accounts[0]?.id ?? 0);
  const [symbol, setSymbol] = useState("");
  const [market, setMarket] = useState<"TW" | "US" | "CRYPTO">("TW");
  const [date, setDate] = useState(new Date().toISOString().slice(0, 10));
  const [price, setPrice] = useState("");
  const [quantity, setQuantity] = useState("");
  const [fee, setFee] = useState("0");
  const [tax, setTax] = useState("0");
  const [note, setNote] = useState("");
  const [splitRatio, setSplitRatio] = useState("");
  const [error, setError] = useState<string | null>(null);

  const createTrade = useCreateJournalTrade(accountId);

  const selectedAccount = accounts.find((a) => a.id === accountId);

  /* Live preview calculation */
  const previewCost =
    action === "BUY" && price && quantity
      ? (Number(price) * Number(quantity) + Number(fee || 0)).toLocaleString("zh-TW", {
          maximumFractionDigits: 2,
        })
      : null;

  async function handleSubmit() {
    setError(null);
    if (!symbol.trim()) { setError("請輸入標的代碼"); return; }
    if ((action === "BUY" || action === "SELL") && (!price || !quantity)) {
      setError("買賣交易需填寫價格與數量");
      return;
    }
    if (action === "SPLIT" && !splitRatio) {
      setError("請填寫分割比例 (如 2 表示 2:1)");
      return;
    }
    try {
      await createTrade.mutateAsync({
        symbol: symbol.trim().toUpperCase(),
        market,
        action,
        date,
        price: price || null,
        quantity: quantity || null,
        fee: fee || "0",
        tax: tax || "0",
        note: note || null,
        split_ratio: action === "SPLIT" ? splitRatio : null,
      });
      onClose();
    } catch (e: unknown) {
      const msg = e instanceof Error ? e.message : "新增失敗，請檢查欄位";
      setError(msg);
    }
  }

  return (
    /* Backdrop */
    <div
      style={{
        position: "fixed",
        inset: 0,
        background: "rgba(0,0,0,0.7)",
        backdropFilter: "blur(4px)",
        zIndex: 1000,
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        padding: 16,
      }}
      onClick={(e) => e.target === e.currentTarget && onClose()}
    >
      <div
        style={{
          background: "var(--glass-bg)",
          border: "1px solid var(--border-color)",
          width: "100%",
          maxWidth: 480,
          padding: 24,
          boxShadow: "var(--glass-shadow)",
        }}
      >
        {/* Header */}
        <div style={{ display: "flex", justifyContent: "space-between", marginBottom: 20 }}>
          <span style={{ fontSize: 14, fontWeight: 700, color: "var(--foreground)", letterSpacing: "-0.04em" }}>
            新增交易
          </span>
          <button
            onClick={onClose}
            style={{ color: "var(--text-muted)", background: "none", border: "none", cursor: "pointer", fontSize: 18 }}
          >
            ×
          </button>
        </div>

        {/* Action Toggle */}
        <div style={{ display: "flex", marginBottom: 16, border: "1px solid var(--border-subtle)" }}>
          {(["BUY", "SELL", "DIVIDEND", "SPLIT"] as Action[]).map((a) => (
            <button
              key={a}
              onClick={() => setAction(a)}
              style={{
                flex: 1,
                padding: "8px 4px",
                fontSize: 11,
                fontWeight: 700,
                border: "none",
                cursor: "pointer",
                background: action === a ? ACTION_COLORS[a] : "transparent",
                color: action === a ? (a === "BUY" ? "#000" : "#fff") : "var(--text-muted)",
                transition: "all 0.15s",
              }}
            >
              {a}
            </button>
          ))}
        </div>

        <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>

          {/* Account selector */}
          <div>
            <label className={labelCls}>帳戶</label>
            <select
              className={inputCls}
              value={accountId}
              onChange={(e) => setAccountId(Number(e.target.value))}
            >
              {accounts.map((acc) => (
                <option key={acc.id} value={acc.id}>{acc.name}</option>
              ))}
            </select>
          </div>

          {/* Symbol + Market */}
          <div style={{ display: "grid", gridTemplateColumns: "1.5fr 1fr", gap: 8 }}>
            <div>
              <label className={labelCls}>標的代碼</label>
              <input
                className={inputCls}
                placeholder="2330.TW / AAPL / BTC"
                value={symbol}
                onChange={(e) => setSymbol(e.target.value)}
              />
            </div>
            <div>
              <label className={labelCls}>市場</label>
              <select
                className={inputCls}
                value={market}
                onChange={(e) => setMarket(e.target.value as "TW" | "US" | "CRYPTO")}
              >
                <option value="TW">TW 台股</option>
                <option value="US">US 美股</option>
                <option value="CRYPTO">CRYPTO</option>
              </select>
            </div>
          </div>

          {/* Date */}
          <div>
            <label className={labelCls}>交易日期</label>
            <input
              type="date"
              className={inputCls}
              value={date}
              onChange={(e) => setDate(e.target.value)}
            />
          </div>

          {/* Price + Quantity (BUY/SELL only) */}
          {(action === "BUY" || action === "SELL") && (
            <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 8 }}>
              <div>
                <label className={labelCls}>成交價格 ({selectedAccount?.currency ?? "—"})</label>
                <input
                  className={inputCls}
                  placeholder="0.00"
                  value={price}
                  onChange={(e) => setPrice(e.target.value)}
                  inputMode="decimal"
                />
              </div>
              <div>
                <label className={labelCls}>數量（股/單位）</label>
                <input
                  className={inputCls}
                  placeholder="0"
                  value={quantity}
                  onChange={(e) => setQuantity(e.target.value)}
                  inputMode="decimal"
                />
              </div>
            </div>
          )}

          {/* Fee + Tax (BUY/SELL only) */}
          {(action === "BUY" || action === "SELL") && (
            <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 8 }}>
              <div>
                <label className={labelCls}>手續費</label>
                <input
                  className={inputCls}
                  placeholder="0"
                  value={fee}
                  onChange={(e) => setFee(e.target.value)}
                  inputMode="decimal"
                />
              </div>
              <div>
                <label className={labelCls}>稅（證交稅）</label>
                <input
                  className={inputCls}
                  placeholder="0"
                  value={tax}
                  onChange={(e) => setTax(e.target.value)}
                  inputMode="decimal"
                />
              </div>
            </div>
          )}

          {/* Split ratio (SPLIT only) */}
          {action === "SPLIT" && (
            <div>
              <label className={labelCls}>分割比例（新股/舊股，如 2 = 2:1）</label>
              <input
                className={inputCls}
                placeholder="2"
                value={splitRatio}
                onChange={(e) => setSplitRatio(e.target.value)}
                inputMode="decimal"
              />
            </div>
          )}

          {/* Note */}
          <div>
            <label className={labelCls}>備註 / 標籤</label>
            <input
              className={inputCls}
              placeholder="策略理由、標籤..."
              value={note}
              onChange={(e) => setNote(e.target.value)}
            />
          </div>

          {/* Preview */}
          {previewCost && (
            <div
              style={{
                padding: "10px 12px",
                background: "rgba(34,197,94,0.06)",
                border: "1px solid rgba(34,197,94,0.15)",
                fontSize: 12,
                color: "var(--text-muted)",
                lineHeight: 1.8,
              }}
            >
              <span style={{ color: "var(--stock-up)", fontWeight: 700 }}>即時預覽 </span>
              總成本 ≈{" "}
              <span style={{ color: "var(--foreground)", fontFamily: "monospace" }}>
                {previewCost} {selectedAccount?.currency ?? ""}
              </span>
            </div>
          )}

          {/* Error */}
          {error && (
            <div style={{ fontSize: 12, color: "var(--stock-down)", padding: "6px 0" }}>{error}</div>
          )}

          {/* Buttons */}
          <div style={{ display: "flex", gap: 8, marginTop: 4 }}>
            <ClippedButton
              variant="green-solid"
              size="md"
              onClick={handleSubmit}
              disabled={createTrade.isPending}
            >
              {createTrade.isPending ? "處理中..." : "確認新增"}
            </ClippedButton>
            <ClippedButton variant="cyan-ghost" size="md" onClick={onClose}>
              取消
            </ClippedButton>
          </div>
        </div>
      </div>
    </div>
  );
}
```

- [ ] **Step 2: Commit**

```bash
cd /Users/stanley/Uni-Seeker && git add frontend/src/components/journal/
git commit -m "feat(journal-fe): AddTradeModal with BUY/SELL/SPLIT/DIVIDEND support and live preview"
```

---

## Task 4: Account List + Account Detail Pages

**Files:**
- Create: `frontend/src/app/journal/accounts/page.tsx`
- Create: `frontend/src/app/journal/accounts/[id]/page.tsx`

- [ ] **Step 1: Create `frontend/src/app/journal/accounts/page.tsx`**

```typescript
"use client";

import { useState } from "react";
import Link from "next/link";
import { AmbientBackground } from "@/components/stratos/ambient";
import { GlassPanel, ClippedButton } from "@/components/stratos/primitives";
import { useJournalAccounts, useCreateJournalAccount } from "@/hooks/use-journal";
import type { JournalAccountCreate } from "@/lib/api-client";

const inputCls =
  "w-full px-3 py-2 bg-[var(--bg-secondary)] border border-[var(--border-subtle)] text-sm text-[var(--foreground)] focus:border-[var(--accent-cyan)] outline-none";
const labelCls =
  "text-[10px] font-bold uppercase tracking-[0.1em] text-[var(--text-muted)] mb-1 block";

function CreateAccountForm({ onDone }: { onDone: () => void }) {
  const [name, setName] = useState("");
  const [broker, setBroker] = useState("");
  const [market, setMarket] = useState<"TW" | "US" | "CRYPTO">("TW");
  const [currency, setCurrency] = useState<"TWD" | "USD" | "USDT" | "BTC" | "ETH">("TWD");
  const [error, setError] = useState<string | null>(null);
  const createAccount = useCreateJournalAccount();

  async function handleCreate() {
    if (!name.trim()) { setError("請輸入帳戶名稱"); return; }
    try {
      await createAccount.mutateAsync({
        name: name.trim(),
        broker: broker || null,
        market,
        currency,
      } as JournalAccountCreate);
      onDone();
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "建立失敗");
    }
  }

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 10, maxWidth: 420 }}>
      <div>
        <label className={labelCls}>帳戶名稱</label>
        <input className={inputCls} value={name} onChange={(e) => setName(e.target.value)} placeholder="元大證券" />
      </div>
      <div>
        <label className={labelCls}>券商（選填）</label>
        <input className={inputCls} value={broker} onChange={(e) => setBroker(e.target.value)} placeholder="元大" />
      </div>
      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 8 }}>
        <div>
          <label className={labelCls}>市場</label>
          <select className={inputCls} value={market} onChange={(e) => setMarket(e.target.value as "TW" | "US" | "CRYPTO")}>
            <option value="TW">TW 台股</option>
            <option value="US">US 美股</option>
            <option value="CRYPTO">加密貨幣</option>
          </select>
        </div>
        <div>
          <label className={labelCls}>計價幣別</label>
          <select className={inputCls} value={currency} onChange={(e) => setCurrency(e.target.value as "TWD" | "USD" | "USDT" | "BTC" | "ETH")}>
            <option value="TWD">TWD</option>
            <option value="USD">USD</option>
            <option value="USDT">USDT</option>
          </select>
        </div>
      </div>
      {error && <div style={{ fontSize: 12, color: "var(--stock-down)" }}>{error}</div>}
      <div style={{ display: "flex", gap: 8 }}>
        <ClippedButton variant="green-solid" size="sm" onClick={handleCreate} disabled={createAccount.isPending}>
          {createAccount.isPending ? "建立中..." : "建立帳戶"}
        </ClippedButton>
        <ClippedButton variant="cyan-ghost" size="sm" onClick={onDone}>取消</ClippedButton>
      </div>
    </div>
  );
}

export default function AccountsPage() {
  const { data: accounts = [], isLoading } = useJournalAccounts();
  const [showForm, setShowForm] = useState(false);

  return (
    <div className="relative flex-1 overflow-y-auto p-6 space-y-6">
      <AmbientBackground />
      <GlassPanel
        title="帳戶列表"
        icon={<span style={{ color: "var(--accent-cyan)" }}>🏦</span>}
      >
        <div style={{ display: "flex", justifyContent: "flex-end", marginBottom: 16 }}>
          {!showForm && (
            <ClippedButton variant="cyan-ghost" size="sm" onClick={() => setShowForm(true)}>
              + 新增帳戶
            </ClippedButton>
          )}
        </div>

        {showForm && <CreateAccountForm onDone={() => setShowForm(false)} />}

        {isLoading ? (
          <div style={{ color: "var(--text-muted)", fontSize: 13 }}>載入中...</div>
        ) : accounts.length === 0 ? (
          <div style={{ color: "var(--text-muted)", fontSize: 13 }}>尚未建立任何帳戶</div>
        ) : (
          <div style={{ display: "flex", flexDirection: "column", gap: 8, marginTop: showForm ? 20 : 0 }}>
            {accounts.map((acc) => (
              <Link key={acc.id} href={`/journal/accounts/${acc.id}`}>
                <div
                  style={{
                    display: "grid",
                    gridTemplateColumns: "1fr auto auto",
                    alignItems: "center",
                    gap: 16,
                    padding: "12px 16px",
                    background: "var(--bg-secondary)",
                    border: "1px solid var(--border-subtle)",
                    cursor: "pointer",
                  }}
                  onMouseEnter={(e) => (e.currentTarget.style.borderColor = "var(--accent-cyan)")}
                  onMouseLeave={(e) => (e.currentTarget.style.borderColor = "var(--border-subtle)")}
                >
                  <div>
                    <div style={{ fontWeight: 700, fontSize: 14, color: "var(--foreground)" }}>
                      {acc.name}
                    </div>
                    <div style={{ fontSize: 11, color: "var(--text-muted)", marginTop: 2 }}>
                      {acc.broker ? `${acc.broker} · ` : ""}{acc.market} · {acc.currency}
                    </div>
                  </div>
                  <div style={{ fontSize: 11, color: "var(--text-muted)" }}>
                    {new Date(acc.created_at).toLocaleDateString("zh-TW")}
                  </div>
                  <span style={{ color: "var(--text-muted)" }}>→</span>
                </div>
              </Link>
            ))}
          </div>
        )}
      </GlassPanel>
    </div>
  );
}
```

- [ ] **Step 2: Create `frontend/src/app/journal/accounts/[id]/page.tsx`**

```typescript
"use client";

import { useState } from "react";
import { useParams } from "next/navigation";
import Link from "next/link";
import { AmbientBackground } from "@/components/stratos/ambient";
import { GlassPanel, ClippedButton } from "@/components/stratos/primitives";
import { useJournalAccount, useJournalAccounts } from "@/hooks/use-journal";
import { AddTradeModal } from "@/components/journal/add-trade-modal";

function pnlColor(val: number) {
  if (val > 0) return "var(--stock-up)";
  if (val < 0) return "var(--stock-down)";
  return "var(--foreground)";
}

function fmt(n: number, dec = 0) {
  return n.toLocaleString("zh-TW", { maximumFractionDigits: dec });
}

export default function AccountDetailPage() {
  const { id } = useParams<{ id: string }>();
  const accountId = Number(id);
  const { data, isLoading } = useJournalAccount(accountId);
  const { data: accounts = [] } = useJournalAccounts();
  const [showModal, setShowModal] = useState(false);

  if (isLoading) {
    return (
      <div className="flex-1 flex items-center justify-center">
        <span style={{ color: "var(--text-muted)" }}>載入中...</span>
      </div>
    );
  }

  if (!data) {
    return (
      <div className="flex-1 flex items-center justify-center">
        <span style={{ color: "var(--stock-down)" }}>帳戶不存在</span>
      </div>
    );
  }

  const { account, positions } = data;
  const totalCost = positions.reduce((s, p) => s + Number(p.total_cost ?? 0), 0);
  const totalRealized = positions.reduce((s, p) => s + Number(p.realized_pnl), 0);

  return (
    <div className="relative flex-1 overflow-y-auto p-6 space-y-4">
      <AmbientBackground />

      {/* Header */}
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start" }}>
        <div>
          <h2 style={{ fontSize: 20, fontWeight: 700, color: "var(--foreground)", letterSpacing: "-0.04em" }}>
            {account.name}
          </h2>
          <div style={{ fontSize: 12, color: "var(--text-muted)", marginTop: 2 }}>
            {account.broker && `${account.broker} · `}{account.market} · {account.currency}
          </div>
        </div>
        <div style={{ display: "flex", gap: 8 }}>
          <Link href={`/journal/accounts/${accountId}/trades`}>
            <ClippedButton variant="cyan-ghost" size="sm">交易記錄</ClippedButton>
          </Link>
          <ClippedButton variant="green-solid" size="sm" onClick={() => setShowModal(true)}>
            + 新增交易
          </ClippedButton>
        </div>
      </div>

      {/* Account KPI */}
      <div style={{ display: "grid", gridTemplateColumns: "repeat(3, 1fr)", gap: 12 }}>
        {[
          { label: "持倉成本", value: fmt(totalCost) },
          { label: "已實現損益", value: fmt(totalRealized), color: pnlColor(totalRealized) },
          { label: "持倉數量", value: `${positions.length} 檔` },
        ].map(({ label, value, color }) => (
          <div
            key={label}
            style={{
              padding: "12px 16px",
              background: "var(--glass-bg)",
              border: "1px solid var(--border-color)",
            }}
          >
            <div style={{ fontSize: 10, fontWeight: 700, color: "var(--text-muted)", letterSpacing: "0.08em", marginBottom: 4 }}>
              {label}
            </div>
            <div style={{ fontSize: 20, fontWeight: 700, color: color ?? "var(--foreground)", fontVariantNumeric: "tabular-nums" }}>
              {value}
            </div>
          </div>
        ))}
      </div>

      {/* Holdings Table */}
      <GlassPanel title="持倉明細" noPadding>
        {positions.length === 0 ? (
          <div style={{ padding: 20, color: "var(--text-muted)", fontSize: 13 }}>
            尚無持倉。點擊右上角「＋ 新增交易」開始記錄。
          </div>
        ) : (
          <div style={{ overflowX: "auto" }}>
            <table style={{ width: "100%", fontSize: 12, borderCollapse: "collapse" }}>
              <thead>
                <tr style={{ borderBottom: "1px solid var(--border-subtle)" }}>
                  {["標的", "數量", "FIFO均價", "持倉成本", "已實現損益"].map((h) => (
                    <th
                      key={h}
                      style={{
                        padding: "8px 14px",
                        textAlign: h === "標的" ? "left" : "right",
                        color: "var(--text-muted)",
                        fontWeight: 700,
                        letterSpacing: "0.06em",
                        fontSize: 10,
                        textTransform: "uppercase",
                      }}
                    >
                      {h}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {positions.map((pos, i) => {
                  const realized = Number(pos.realized_pnl);
                  const avgCost = Number(pos.avg_cost_fifo ?? 0);
                  const cost = Number(pos.total_cost ?? 0);
                  return (
                    <tr
                      key={pos.id}
                      style={{
                        borderBottom: "1px solid var(--border-subtle)",
                        background: i % 2 === 0 ? "transparent" : "rgba(255,255,255,0.015)",
                      }}
                    >
                      <td style={{ padding: "10px 14px", fontWeight: 700, color: "var(--foreground)" }}>
                        {pos.symbol}
                        <span style={{ fontSize: 10, color: "var(--text-muted)", marginLeft: 6 }}>
                          {pos.market}
                        </span>
                      </td>
                      <td style={{ padding: "10px 14px", textAlign: "right", fontFamily: "monospace" }}>
                        {fmt(Number(pos.quantity), 4)}
                      </td>
                      <td style={{ padding: "10px 14px", textAlign: "right", fontFamily: "monospace", color: "var(--text-muted)" }}>
                        {avgCost > 0 ? fmt(avgCost, 2) : "—"}
                      </td>
                      <td style={{ padding: "10px 14px", textAlign: "right", fontFamily: "monospace" }}>
                        {cost > 0 ? fmt(cost) : "—"}
                      </td>
                      <td style={{ padding: "10px 14px", textAlign: "right", fontFamily: "monospace", color: pnlColor(realized) }}>
                        {realized !== 0 ? (realized > 0 ? "+" : "") + fmt(realized) : "—"}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </GlassPanel>

      {showModal && (
        <AddTradeModal
          accounts={accounts}
          defaultAccountId={accountId}
          onClose={() => setShowModal(false)}
        />
      )}
    </div>
  );
}
```

- [ ] **Step 3: Verify TypeScript compiles**

```bash
cd /Users/stanley/Uni-Seeker/frontend && npx tsc --noEmit 2>&1 | grep -i "journal" | head -20
```
Expected: no errors.

- [ ] **Step 4: Commit**

```bash
cd /Users/stanley/Uni-Seeker && git add frontend/src/app/journal/accounts/
git commit -m "feat(journal-fe): account list + account detail pages with holdings table"
```

---

## Task 5: Trades List Page

**Files:**
- Create: `frontend/src/app/journal/accounts/[id]/trades/page.tsx`

- [ ] **Step 1: Create `frontend/src/app/journal/accounts/[id]/trades/page.tsx`**

```typescript
"use client";

import { useState } from "react";
import { useParams } from "next/navigation";
import { AmbientBackground } from "@/components/stratos/ambient";
import { GlassPanel, ClippedButton } from "@/components/stratos/primitives";
import { useJournalTrades, useJournalAccounts } from "@/hooks/use-journal";
import { AddTradeModal } from "@/components/journal/add-trade-modal";

const ACTION_COLOR: Record<string, string> = {
  BUY: "var(--stock-up)",
  SELL: "var(--stock-down)",
  DIVIDEND: "#f59e0b",
  SPLIT: "var(--accent-cyan)",
};

function fmt(n: number, dec = 2) {
  return n.toLocaleString("zh-TW", { maximumFractionDigits: dec });
}

export default function TradesPage() {
  const { id } = useParams<{ id: string }>();
  const accountId = Number(id);
  const [page, setPage] = useState(1);
  const [showModal, setShowModal] = useState(false);
  const { data = { total: 0, items: [] }, isLoading } = useJournalTrades(accountId, { page, page_size: 50 });
  const { data: accounts = [] } = useJournalAccounts();

  const totalPages = Math.ceil(data.total / 50);

  return (
    <div className="relative flex-1 overflow-y-auto p-6 space-y-4">
      <AmbientBackground />

      <GlassPanel title="交易記錄" noPadding>
        <div style={{ padding: "12px 16px", display: "flex", justifyContent: "space-between", alignItems: "center", borderBottom: "1px solid var(--border-subtle)" }}>
          <span style={{ fontSize: 12, color: "var(--text-muted)" }}>共 {data.total} 筆記錄</span>
          <ClippedButton variant="green-solid" size="sm" onClick={() => setShowModal(true)}>
            + 新增交易
          </ClippedButton>
        </div>

        {isLoading ? (
          <div style={{ padding: 20, color: "var(--text-muted)", fontSize: 13 }}>載入中...</div>
        ) : data.items.length === 0 ? (
          <div style={{ padding: 20, color: "var(--text-muted)", fontSize: 13 }}>尚無交易記錄</div>
        ) : (
          <div style={{ overflowX: "auto" }}>
            <table style={{ width: "100%", fontSize: 12, borderCollapse: "collapse" }}>
              <thead>
                <tr style={{ borderBottom: "1px solid var(--border-subtle)" }}>
                  {["日期", "動作", "標的", "價格", "數量", "手續費", "稅", "備註"].map((h) => (
                    <th
                      key={h}
                      style={{
                        padding: "8px 12px",
                        textAlign: h === "日期" || h === "動作" || h === "標的" || h === "備註" ? "left" : "right",
                        color: "var(--text-muted)",
                        fontWeight: 700,
                        fontSize: 10,
                        textTransform: "uppercase",
                        letterSpacing: "0.06em",
                      }}
                    >
                      {h}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {data.items.map((trade, i) => (
                  <tr
                    key={trade.id}
                    style={{
                      borderBottom: "1px solid var(--border-subtle)",
                      background: i % 2 === 0 ? "transparent" : "rgba(255,255,255,0.015)",
                    }}
                  >
                    <td style={{ padding: "9px 12px", color: "var(--text-muted)" }}>{trade.date}</td>
                    <td style={{ padding: "9px 12px" }}>
                      <span style={{ color: ACTION_COLOR[trade.action] ?? "var(--foreground)", fontWeight: 700 }}>
                        {trade.action}
                      </span>
                    </td>
                    <td style={{ padding: "9px 12px", fontWeight: 700, color: "var(--foreground)" }}>
                      {trade.symbol}
                    </td>
                    <td style={{ padding: "9px 12px", textAlign: "right", fontFamily: "monospace", color: "var(--text-muted)" }}>
                      {trade.price ? fmt(Number(trade.price), 4) : "—"}
                    </td>
                    <td style={{ padding: "9px 12px", textAlign: "right", fontFamily: "monospace" }}>
                      {trade.quantity ? fmt(Number(trade.quantity), 4) : "—"}
                    </td>
                    <td style={{ padding: "9px 12px", textAlign: "right", fontFamily: "monospace", color: "var(--text-muted)" }}>
                      {Number(trade.fee) > 0 ? fmt(Number(trade.fee)) : "—"}
                    </td>
                    <td style={{ padding: "9px 12px", textAlign: "right", fontFamily: "monospace", color: "var(--text-muted)" }}>
                      {Number(trade.tax) > 0 ? fmt(Number(trade.tax)) : "—"}
                    </td>
                    <td style={{ padding: "9px 12px", color: "var(--text-muted)", maxWidth: 160, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                      {trade.note ?? ""}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}

        {/* Pagination */}
        {totalPages > 1 && (
          <div style={{ padding: "12px 16px", display: "flex", gap: 8, justifyContent: "center" }}>
            <ClippedButton variant="cyan-ghost" size="sm" onClick={() => setPage((p) => Math.max(1, p - 1))} disabled={page === 1}>
              ← 上一頁
            </ClippedButton>
            <span style={{ fontSize: 12, color: "var(--text-muted)", alignSelf: "center" }}>
              {page} / {totalPages}
            </span>
            <ClippedButton variant="cyan-ghost" size="sm" onClick={() => setPage((p) => Math.min(totalPages, p + 1))} disabled={page === totalPages}>
              下一頁 →
            </ClippedButton>
          </div>
        )}
      </GlassPanel>

      {showModal && (
        <AddTradeModal
          accounts={accounts}
          defaultAccountId={accountId}
          onClose={() => setShowModal(false)}
        />
      )}
    </div>
  );
}
```

- [ ] **Step 2: Commit**

```bash
cd /Users/stanley/Uni-Seeker && git add frontend/src/app/journal/accounts/
git commit -m "feat(journal-fe): trade history page with pagination and add trade modal"
```

---

## Task 6: Groups Pages

**Files:**
- Create: `frontend/src/app/journal/groups/page.tsx`
- Create: `frontend/src/app/journal/groups/[id]/page.tsx`

- [ ] **Step 1: Create `frontend/src/app/journal/groups/page.tsx`**

```typescript
"use client";

import { useState } from "react";
import Link from "next/link";
import { AmbientBackground } from "@/components/stratos/ambient";
import { GlassPanel, ClippedButton } from "@/components/stratos/primitives";
import { useJournalGroups, useJournalAccounts, useCreateJournalGroup } from "@/hooks/use-journal";

const inputCls =
  "w-full px-3 py-2 bg-[var(--bg-secondary)] border border-[var(--border-subtle)] text-sm text-[var(--foreground)] focus:border-[var(--accent-cyan)] outline-none";
const labelCls =
  "text-[10px] font-bold uppercase tracking-[0.1em] text-[var(--text-muted)] mb-1 block";

function CreateGroupForm({ onDone }: { onDone: () => void }) {
  const [name, setName] = useState("");
  const [error, setError] = useState<string | null>(null);
  const { data: accounts = [] } = useJournalAccounts();
  const createGroup = useCreateJournalGroup();

  async function handleCreate() {
    if (!name.trim()) { setError("請輸入群組名稱"); return; }
    try {
      await createGroup.mutateAsync({ name: name.trim() });
      onDone();
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "建立失敗");
    }
  }

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 10, maxWidth: 400, marginBottom: 20 }}>
      <div>
        <label className={labelCls}>群組名稱</label>
        <input className={inputCls} value={name} onChange={(e) => setName(e.target.value)} placeholder="我的投資組合" />
      </div>
      {error && <div style={{ fontSize: 12, color: "var(--stock-down)" }}>{error}</div>}
      <div style={{ display: "flex", gap: 8 }}>
        <ClippedButton variant="green-solid" size="sm" onClick={handleCreate} disabled={createGroup.isPending}>
          {createGroup.isPending ? "建立中..." : "建立群組"}
        </ClippedButton>
        <ClippedButton variant="cyan-ghost" size="sm" onClick={onDone}>取消</ClippedButton>
      </div>
    </div>
  );
}

export default function GroupsPage() {
  const { data: groups = [], isLoading } = useJournalGroups();
  const [showForm, setShowForm] = useState(false);

  return (
    <div className="relative flex-1 overflow-y-auto p-6">
      <AmbientBackground />
      <GlassPanel title="投資組合群組">
        <div style={{ display: "flex", justifyContent: "flex-end", marginBottom: 16 }}>
          {!showForm && (
            <ClippedButton variant="cyan-ghost" size="sm" onClick={() => setShowForm(true)}>
              + 新增群組
            </ClippedButton>
          )}
        </div>
        {showForm && <CreateGroupForm onDone={() => setShowForm(false)} />}

        {isLoading ? (
          <div style={{ color: "var(--text-muted)", fontSize: 13 }}>載入中...</div>
        ) : groups.length === 0 ? (
          <div style={{ color: "var(--text-muted)", fontSize: 13 }}>
            尚未建立任何群組。群組可將多個帳戶合併追蹤，並設定再平衡目標。
          </div>
        ) : (
          <div style={{ display: "flex", flexDirection: "column", gap: 8, marginTop: showForm ? 8 : 0 }}>
            {groups.map((g) => (
              <Link key={g.id} href={`/journal/groups/${g.id}`}>
                <div
                  style={{
                    padding: "12px 16px",
                    background: "var(--bg-secondary)",
                    border: "1px solid var(--border-subtle)",
                    display: "grid",
                    gridTemplateColumns: "1fr auto",
                    alignItems: "center",
                    cursor: "pointer",
                  }}
                  onMouseEnter={(e) => (e.currentTarget.style.borderColor = "var(--accent-cyan)")}
                  onMouseLeave={(e) => (e.currentTarget.style.borderColor = "var(--border-subtle)")}
                >
                  <div>
                    <div style={{ fontWeight: 700, fontSize: 14, color: "var(--foreground)" }}>{g.name}</div>
                    <div style={{ fontSize: 11, color: "var(--text-muted)", marginTop: 2 }}>
                      {g.members.length} 個帳戶 · {g.base_currency}
                    </div>
                  </div>
                  <span style={{ color: "var(--text-muted)" }}>→</span>
                </div>
              </Link>
            ))}
          </div>
        )}
      </GlassPanel>
    </div>
  );
}
```

- [ ] **Step 2: Create `frontend/src/app/journal/groups/[id]/page.tsx`**

```typescript
"use client";

import { useParams } from "next/navigation";
import Link from "next/link";
import { AmbientBackground } from "@/components/stratos/ambient";
import { GlassPanel } from "@/components/stratos/primitives";
import { useJournalGroup, useJournalAlerts } from "@/hooks/use-journal";

export default function GroupDetailPage() {
  const { id } = useParams<{ id: string }>();
  const groupId = Number(id);
  const { data: group, isLoading } = useJournalGroup(groupId);
  const { data: alertsData } = useJournalAlerts();
  const groupAlerts = (alertsData?.alerts ?? []).filter(
    (a) => a.scope === "group" && a.scope_id === groupId,
  );

  if (isLoading) {
    return (
      <div className="flex-1 flex items-center justify-center">
        <span style={{ color: "var(--text-muted)" }}>載入中...</span>
      </div>
    );
  }

  if (!group) {
    return (
      <div className="flex-1 flex items-center justify-center">
        <span style={{ color: "var(--stock-down)" }}>群組不存在</span>
      </div>
    );
  }

  return (
    <div className="relative flex-1 overflow-y-auto p-6 space-y-4">
      <AmbientBackground />

      <div>
        <h2 style={{ fontSize: 20, fontWeight: 700, color: "var(--foreground)", letterSpacing: "-0.04em" }}>
          {group.name}
        </h2>
        <div style={{ fontSize: 12, color: "var(--text-muted)", marginTop: 2 }}>
          基準幣別：{group.base_currency} · {group.members.length} 個帳戶
        </div>
      </div>

      {/* Member Accounts */}
      <GlassPanel title="成員帳戶">
        {group.members.length === 0 ? (
          <div style={{ fontSize: 13, color: "var(--text-muted)" }}>尚無帳戶成員</div>
        ) : (
          <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
            {group.members.map((m) => (
              <Link key={m.account_id} href={`/journal/accounts/${m.account_id}`}>
                <div
                  style={{
                    display: "grid",
                    gridTemplateColumns: "1fr auto auto",
                    alignItems: "center",
                    gap: 16,
                    padding: "10px 14px",
                    background: "var(--bg-secondary)",
                    border: "1px solid var(--border-subtle)",
                    cursor: "pointer",
                  }}
                  onMouseEnter={(e) => (e.currentTarget.style.borderColor = "var(--accent-cyan)")}
                  onMouseLeave={(e) => (e.currentTarget.style.borderColor = "var(--border-subtle)")}
                >
                  <div>
                    <div style={{ fontWeight: 700, fontSize: 13, color: "var(--foreground)" }}>
                      {m.account.name}
                    </div>
                    <div style={{ fontSize: 11, color: "var(--text-muted)" }}>
                      {m.account.market} · {m.account.currency}
                    </div>
                  </div>
                  {m.target_weight && (
                    <div style={{ fontSize: 12, color: "var(--accent-cyan)", fontFamily: "monospace" }}>
                      目標 {(Number(m.target_weight) * 100).toFixed(0)}%
                    </div>
                  )}
                  <span style={{ color: "var(--text-muted)" }}>→</span>
                </div>
              </Link>
            ))}
          </div>
        )}
      </GlassPanel>

      {/* Group-level Rebalance Alerts */}
      {groupAlerts.length > 0 && (
        <GlassPanel title="群組再平衡警示">
          <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
            {groupAlerts.map((a, i) => {
              const dev = Number(a.deviation);
              const isOver = a.direction === "over";
              return (
                <div
                  key={i}
                  style={{
                    display: "flex",
                    justifyContent: "space-between",
                    padding: "8px 12px",
                    background: isOver ? "rgba(239,68,68,0.07)" : "rgba(245,158,11,0.07)",
                    borderLeft: `3px solid ${isOver ? "var(--stock-down)" : "#f59e0b"}`,
                    fontSize: 12,
                  }}
                >
                  <span style={{ fontWeight: 700, color: "var(--foreground)" }}>{a.symbol}</span>
                  <span style={{ color: isOver ? "var(--stock-down)" : "#f59e0b", fontFamily: "monospace" }}>
                    {isOver ? "+" : ""}{(dev * 100).toFixed(1)}% 偏差
                  </span>
                </div>
              );
            })}
          </div>
        </GlassPanel>
      )}

      {/* Placeholder for future group performance chart */}
      <GlassPanel title="群組績效圖">
        <div style={{ fontSize: 13, color: "var(--text-muted)" }}>
          群組資產曲線將在日快照 cron job 啟用後顯示（Plan C）
        </div>
      </GlassPanel>
    </div>
  );
}
```

- [ ] **Step 3: Add `useCreateJournalGroup` hook (missing from Task 0)**

In `frontend/src/hooks/use-journal.ts`, add:
```typescript
export function useCreateJournalGroup() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: Parameters<typeof createJournalGroup>[0]) => createJournalGroup(body),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: queryKeys.journal.groups() });
    },
  });
}
```

Also add `createJournalGroup` to the import from `@/lib/api-client` in the hooks file.

- [ ] **Step 4: Verify TypeScript compiles**

```bash
cd /Users/stanley/Uni-Seeker/frontend && npx tsc --noEmit 2>&1 | grep -i "journal" | head -30
```
Expected: no errors.

- [ ] **Step 5: Commit**

```bash
cd /Users/stanley/Uni-Seeker && git add frontend/src/app/journal/groups/ frontend/src/hooks/use-journal.ts
git commit -m "feat(journal-fe): groups list + group detail pages"
```

---

## Task 7: Dev Server Verification

- [ ] **Step 1: Start dev server and verify all journal pages load**

```bash
cd /Users/stanley/Uni-Seeker/frontend && npm run dev &
sleep 5 && curl -s http://localhost:3000/journal | grep -i "journal\|500\|Error" | head -5
```

- [ ] **Step 2: Check browser (manual)**

Open browser to:
- `http://localhost:3000/journal` — Dashboard shows KPI row, chart, accounts section
- `http://localhost:3000/journal/accounts` — Account list with "+ 新增帳戶" button
- `http://localhost:3000/journal/groups` — Group list

- [ ] **Step 3: Commit if all good**

```bash
cd /Users/stanley/Uni-Seeker && git add -A
git commit -m "feat(journal-fe): complete Trade Journal frontend — Phase 1 all pages"
```

---

## Self-Review Checklist

- [x] **Spec coverage:** All 6 pages from spec implemented: Dashboard, Accounts list, Account detail, Trades, Groups list, Group detail. AddTradeModal accessible from account detail and trades pages.
- [x] **No placeholders:** All pages have real code, not "TODO" stubs.
- [x] **Type consistency:** `JournalPosition.quantity` is `string` (DecimalStr from backend) — all usages call `Number()` before arithmetic.
- [x] **STRATOS style:** GlassPanel, ClippedButton, KpiCard, AmbientBackground used throughout. CSS variables used for colors (no hardcoded hex except alerts).
- [x] **Missing hook:** `useCreateJournalGroup` added in Task 6 Step 3 since it was needed by Groups page but not in Task 0.
- [x] **fetchJournalGroups GET /groups endpoint:** Backend has POST /groups and GET /groups/{id} but NOT GET /groups (list all). Task 0 adds `fetchJournalGroups()` but backend needs a GET /groups endpoint. **Action required:** Either add `GET /journal/groups` to backend (quick, 3 lines in `journal.py`), or the groups list page falls back gracefully. The plan assumes backend will be patched.

> **Backend patch needed (do before frontend Task 6):** In `backend/app/api/v1/journal.py`, add:
> ```python
> @router.get("/groups", response_model=list[GroupResponse])
> async def list_groups(db: DbDep) -> list[GroupResponse]:
>     groups = (await db.execute(select(AccountGroup))).scalars().all()
>     return [await _build_group_response(db, g) for g in groups]
> ```

---

> Plan C (future): `snapshot_job.py` cron → real D/W/M/Y chart data; CSV import; FX rate sync from external API.
