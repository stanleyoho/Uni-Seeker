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
                formatter={(v: unknown) => [fmt(Number(v)), "市值"]}
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
