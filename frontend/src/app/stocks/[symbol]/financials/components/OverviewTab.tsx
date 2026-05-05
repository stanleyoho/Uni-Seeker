"use client";

import { useId } from "react";
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
  if (v == null) return "N/A";
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

function TrendChart({ data, color, label }: {
  data: { period: string; value: number }[];
  color: string;
  label: string;
}) {
  const uid = useId();
  const gradId = `grad-${uid}`;
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
            <linearGradient id={gradId} x1="0" y1="0" x2="0" y2="1">
              <stop offset="5%" stopColor={color} stopOpacity={0.25} />
              <stop offset="95%" stopColor={color} stopOpacity={0} />
            </linearGradient>
          </defs>
          <XAxis dataKey="period" hide />
          <Tooltip
            contentStyle={{ background: "var(--bg-secondary)", border: "1px solid var(--border-subtle)", fontSize: 11 }}
            formatter={(v) => [`${(Number(v) * 100).toFixed(1)}%`, label]}
          />
          <Area type="monotone" dataKey="value" stroke={color} strokeWidth={1.5} fill={`url(#${gradId})`} dot={false} />
        </AreaChart>
      </ResponsiveContainer>
    </div>
  );
}

function FCFTrendChart({ data }: { data: { period: string; value: number }[] }) {
  const uid = useId();
  const gradId = `grad-${uid}`;
  const latest = data[data.length - 1]?.value;
  const color = latest != null && latest >= 0 ? "#22c55e" : "#ef4444";
  const fmtBillion = (n: number) => {
    const b = n / 1e9;
    return `${b.toFixed(1)}B`;
  };
  return (
    <div style={{ background: "var(--bg-secondary)", border: "1px solid var(--border-subtle)", padding: "12px 14px" }}>
      <div style={{ fontSize: 9, fontWeight: 700, letterSpacing: "0.12em", textTransform: "uppercase", color: "var(--text-muted)", marginBottom: 4 }}>
        自由現金流趨勢
      </div>
      <div style={{ fontSize: 18, fontWeight: 700, fontVariantNumeric: "tabular-nums", color, marginBottom: 8 }}>
        {latest != null && isFinite(latest) ? fmtBillion(latest) : "N/A"}
      </div>
      <ResponsiveContainer width="100%" height={56}>
        <AreaChart data={data} margin={{ top: 2, right: 2, left: 2, bottom: 2 }}>
          <defs>
            <linearGradient id={gradId} x1="0" y1="0" x2="0" y2="1">
              <stop offset="5%" stopColor={color} stopOpacity={0.25} />
              <stop offset="95%" stopColor={color} stopOpacity={0} />
            </linearGradient>
          </defs>
          <XAxis dataKey="period" hide />
          <Tooltip
            contentStyle={{ background: "var(--bg-secondary)", border: "1px solid var(--border-subtle)", fontSize: 11 }}
            formatter={(v) => [fmtBillion(Number(v)), "FCF"]}
          />
          <Area type="monotone" dataKey="value" stroke={color} strokeWidth={1.5} fill={`url(#${gradId})`} dot={false} />
        </AreaChart>
      </ResponsiveContainer>
    </div>
  );
}

export function OverviewTab({ ratios, healthScores, cashFlows }: OverviewTabProps) {
  const latest = ratios[0];
  const latestHealth = healthScores[0];

  if (!latest) {
    return (
      <GlassPanel>
        <div style={{ padding: "40px 0", textAlign: "center", color: "var(--text-muted)" }}>暫無財務資料</div>
      </GlassPanel>
    );
  }

  // Build sorted time-series for trend charts (oldest → newest)
  const sorted = [...ratios].sort((a, b) => a.period.localeCompare(b.period));

  const grossData = sorted.map((r) => ({ period: r.period, value: Number(r.gross_margin ?? 0) }));
  const netData = sorted.map((r) => ({ period: r.period, value: Number(r.net_margin ?? 0) }));
  const roeData = sorted.map((r) => ({ period: r.period, value: Number(r.roe ?? 0) }));

  // FCF from cash_flows (oldest → newest)
  const fcfData = [...cashFlows]
    .sort((a, b) => a.period.localeCompare(b.period))
    .map((s) => ({ period: s.period, value: Number(s.data["Free Cash Flow"] ?? 0) }));

  const revenueGrowth = latest.revenue_growth ? Number(latest.revenue_growth) : null;
  const growthDir = revenueGrowth == null ? "flat" : revenueGrowth >= 0 ? "up" : "down";

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
          <TrendChart data={grossData} color="#22c55e" label="毛利率趨勢" />
          <TrendChart data={netData} color="#22c55e" label="淨利率趨勢" />
          <TrendChart data={roeData} color={Number(latest.roe ?? 0) >= 0.15 ? "#22c55e" : "#eab308"} label="ROE 趨勢" />
          <FCFTrendChart data={fcfData} />
        </div>
      </div>
    </div>
  );
}
