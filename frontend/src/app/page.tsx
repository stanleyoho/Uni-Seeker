"use client";

import React, { useMemo, useState, useEffect } from "react";
import Link from "next/link";
import {
  AreaChart,
  Area,
  ResponsiveContainer,
} from "recharts";
import { Eye } from "lucide-react";
import { KpiCard, GlassPanel } from "@/components/stratos/primitives";
import { Sparkline, SectorHeatmap } from "@/components/stratos/charts";
import { AmbientBackground } from "@/components/stratos/ambient";
import {
  useMarketIndices,
  useMarketMovers,
  useHeatmap,
} from "@/hooks/use-market-data";
import { useWatchlist } from "@/hooks/use-watchlist";
import { useI18n } from "@/i18n/context";
import { LoadingSpinner } from "@/components/ui/loading";
import type {
  MarketIndex,
  MarketMover,
  HeatmapSector,
} from "@/lib/api-client";

// ---------------------------------------------------------------------------
// Mock news data (no news API available yet)
// ---------------------------------------------------------------------------

const NEWS_ITEMS = [
  {
    id: 1,
    title: "Fed holds rates steady, signals potential cuts in Q3",
    source: "Reuters",
    time: "14:32",
    tag: "Macro",
    severity: "gray" as const,
  },
  {
    id: 2,
    title: "TSMC beats Q1 estimates on strong AI chip demand",
    source: "Bloomberg",
    time: "14:15",
    tag: "Earnings",
    severity: "green" as const,
  },
  {
    id: 3,
    title: "Taiwan export orders rise 12% YoY in March",
    source: "MOEA",
    time: "13:58",
    tag: "Data",
    severity: "green" as const,
  },
  {
    id: 4,
    title: "Nvidia announces next-gen GPU architecture",
    source: "TechCrunch",
    time: "13:42",
    tag: "Tech",
    severity: "green" as const,
  },
  {
    id: 5,
    title: "USD/TWD slips below 30.5 on trade surplus data",
    source: "FX Street",
    time: "13:20",
    tag: "FX",
    severity: "red" as const,
  },
  {
    id: 6,
    title: "China PMI contracts for second consecutive month",
    source: "Caixin",
    time: "12:45",
    tag: "Macro",
    severity: "red" as const,
  },
  {
    id: 7,
    title: "MediaTek revenue guidance raised on 5G demand",
    source: "DigiTimes",
    time: "11:30",
    tag: "Earnings",
    severity: "green" as const,
  },
];

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

/** Generate a mock 20-point sparkline from a single value */
function generateMockTrend(base: number): { v: number }[] {
  const points: { v: number }[] = [];
  let val = base * 0.97;
  for (let i = 0; i < 20; i++) {
    val += (base * 0.003) * (Math.sin(i * 0.8) + 0.5 * Math.cos(i * 1.3));
    points.push({ v: val });
  }
  points[points.length - 1] = { v: base };
  return points;
}

/** Filter indices to show major markets */
function filterMajorIndices(indices: MarketIndex[]): MarketIndex[] {
  const matchers = [
    (n: string) => /TAIEX|加權|0050/i.test(n),
    (n: string) => /SPY|S&P/i.test(n),
    (n: string) => /NASDAQ|QQQ|那斯達克/i.test(n),
    (n: string) => /SOX|費半|Semiconductor|半導體/i.test(n),
  ];

  const matched: MarketIndex[] = [];
  for (const matcher of matchers) {
    const found = indices.find(
      (idx) => matcher(idx.name) || matcher(idx.symbol)
    );
    if (found && !matched.some((m) => m.symbol === found.symbol)) {
      matched.push(found);
    }
  }

  if (matched.length < 4) {
    for (const idx of indices) {
      if (matched.length >= 4) break;
      if (!matched.some((m) => m.symbol === idx.symbol)) {
        matched.push(idx);
      }
    }
  }

  return matched.slice(0, 4);
}

function IndexChartCell({ idx }: { idx: MarketIndex }) {
  const value = parseFloat(idx.value);
  const change = parseFloat(idx.change);
  const changePercent = parseFloat(idx.change_percent);
  const isUp = change >= 0;
  const trendData = useMemo(() => generateMockTrend(value), [value]);
  const gradientId = `idx-grad-${idx.symbol.replace(/[^a-zA-Z0-9]/g, "")}`;

  return (
    <GlassPanel title={idx.name} className="h-[180px]">
      <div className="flex items-end justify-between mb-2">
        <div>
          <div className="text-2xl font-bold tabular-nums text-[var(--foreground)]">
            {value.toLocaleString(undefined, { maximumFractionDigits: 2 })}
          </div>
          <div className={`text-sm font-semibold ${isUp ? "text-[var(--stock-up)]" : "text-[var(--stock-down)]"}`}>
            {isUp ? "+" : ""}{change.toFixed(2)} ({isUp ? "+" : ""}{changePercent.toFixed(2)}%)
          </div>
        </div>
      </div>
      <div className="h-[80px] -mx-2">
        <ResponsiveContainer
          width="100%"
          height="100%"
          minWidth={0}
          minHeight={80}
          initialDimension={{ width: 200, height: 80 }}
        >
          <AreaChart data={trendData}>
            <defs>
              <linearGradient id={gradientId} x1="0" y1="0" x2="0" y2="1">
                <stop offset="0%" stopColor={isUp ? "var(--stock-up)" : "var(--stock-down)"} stopOpacity={0.2} />
                <stop offset="100%" stopColor={isUp ? "var(--stock-up)" : "var(--stock-down)"} stopOpacity={0} />
              </linearGradient>
            </defs>
            <Area
              type="monotone"
              dataKey="v"
              stroke={isUp ? "var(--stock-up)" : "var(--stock-down)"}
              strokeWidth={2}
              fill={`url(#${gradientId})`}
              isAnimationActive={false}
            />
          </AreaChart>
        </ResponsiveContainer>
      </div>
    </GlassPanel>
  );
}

// ---------------------------------------------------------------------------
// Market Status Bar
// ---------------------------------------------------------------------------

function getMarketStatus(): {
  tw: { label: string; status: "open" | "closed" | "pre" };
  us: { label: string; status: "open" | "closed" | "pre" };
  dateStr: string;
} {
  const now = new Date();
  // Convert to TST (UTC+8)
  const tstOffset = 8 * 60;
  const localOffset = now.getTimezoneOffset();
  const tst = new Date(now.getTime() + (tstOffset + localOffset) * 60000);
  const h = tst.getHours();
  const m = tst.getMinutes();
  const mins = h * 60 + m;
  const day = tst.getDay();
  const isWeekday = day >= 1 && day <= 5;

  // TW market: 09:00-13:30 TST weekdays
  let twStatus: "open" | "closed" | "pre" = "closed";
  if (isWeekday) {
    if (mins >= 540 && mins < 810) twStatus = "open";        // 09:00-13:30
    else if (mins >= 480 && mins < 540) twStatus = "pre";    // 08:00-09:00
  }

  // US market: 21:30-04:00 TST (next day) weekdays
  // In TST: open Mon night to Fri night (21:30), close next morning (04:00)
  let usStatus: "open" | "closed" | "pre" = "closed";
  if (mins >= 1290 || mins < 240) {
    // 21:30-04:00 window
    const isUsDay =
      (mins >= 1290 && day >= 1 && day <= 5) ||
      (mins < 240 && day >= 2 && day <= 6);
    if (isUsDay) usStatus = "open";
  } else if (mins >= 1260 && mins < 1290 && isWeekday) {
    usStatus = "pre"; // 21:00-21:30
  }

  const dateStr = tst.toLocaleDateString("zh-TW", {
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    weekday: "short",
  });

  return {
    tw: { label: "台股 09:00-13:30", status: twStatus },
    us: { label: "美股 21:30-04:00", status: usStatus },
    dateStr,
  };
}

const statusDotColors = {
  open: "#10B981",
  closed: "#EF4444",
  pre: "#F59E0B",
};
const statusLabels = {
  open: "盤中",
  closed: "休市",
  pre: "盤前",
};

function MarketStatusBar() {
  const [status, setStatus] = useState(getMarketStatus);

  useEffect(() => {
    const timer = setInterval(() => setStatus(getMarketStatus()), 30_000);
    return () => clearInterval(timer);
  }, []);

  return (
    <div
      style={{
        height: 32,
        background: "var(--bg-secondary, rgba(255,255,255,0.03))",
        borderBottom: "1px solid var(--border-color, rgba(255,255,255,0.06))",
        display: "flex",
        alignItems: "center",
        justifyContent: "space-between",
        padding: "0 16px",
        fontSize: 11,
        fontFamily: "var(--font-mono, monospace)",
        color: "var(--text-muted, #9CA3AF)",
        borderRadius: "var(--glass-radius, 0)",
        marginBottom: 12,
      }}
    >
      <div style={{ display: "flex", alignItems: "center", gap: 20 }}>
        <span style={{ display: "flex", alignItems: "center", gap: 6 }}>
          <span
            style={{
              width: 6,
              height: 6,
              borderRadius: "50%",
              background: statusDotColors[status.tw.status],
              display: "inline-block",
              boxShadow: `0 0 4px ${statusDotColors[status.tw.status]}`,
            }}
          />
          {statusLabels[status.tw.status]} {status.tw.label}
        </span>
        <span style={{ display: "flex", alignItems: "center", gap: 6 }}>
          <span
            style={{
              width: 6,
              height: 6,
              borderRadius: "50%",
              background: statusDotColors[status.us.status],
              display: "inline-block",
              boxShadow: `0 0 4px ${statusDotColors[status.us.status]}`,
            }}
          />
          {statusLabels[status.us.status]} {status.us.label}
        </span>
      </div>
      <span>{status.dateStr}</span>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Section: Index Cards (full-width 4-column row)
// ---------------------------------------------------------------------------

function IndexRow({ indices }: { indices: MarketIndex[] }) {
  const majorIndices = useMemo(() => filterMajorIndices(indices), [indices]);

  if (majorIndices.length === 0) {
    return (
      <GlassPanel title="MARKET INDICES">
        <div style={{ color: "var(--text-secondary)", fontSize: 13 }}>
          No index data available
        </div>
      </GlassPanel>
    );
  }

  return (
    <div
      className="grid grid-cols-2 lg:grid-cols-4 gap-3"
    >
      {majorIndices.map((idx) => (
        <IndexCell key={idx.symbol} idx={idx} />
      ))}
    </div>
  );
}

function IndexCell({ idx }: { idx: MarketIndex }) {
  const value = parseFloat(idx.value);
  const changePercent = parseFloat(idx.change_percent);
  const isUp = changePercent >= 0;
  const color = isUp ? "var(--stock-up)" : "var(--stock-down)";
  const trendData = useMemo(() => generateMockTrend(value), [value]);
  const gradientId = `idx-grad-${idx.symbol.replace(/[^a-zA-Z0-9]/g, "")}`;

  return (
    <GlassPanel>
      <div
        style={{
          fontSize: 11,
          fontWeight: 600,
          textTransform: "uppercase",
          color: "var(--text-muted, #9CA3AF)",
          letterSpacing: "0.04em",
          marginBottom: 4,
        }}
      >
        {idx.name}
      </div>
      <div
        style={{
          fontSize: 28,
          fontWeight: 700,
          color: "var(--foreground)",
          fontVariantNumeric: "tabular-nums",
          lineHeight: 1.2,
        }}
      >
        {value.toLocaleString(undefined, { maximumFractionDigits: 2 })}
      </div>
      <div
        style={{
          fontSize: 14,
          fontWeight: 600,
          color,
          marginBottom: 6,
        }}
      >
        {isUp ? "\u25B2" : "\u25BC"}{" "}
        {isUp ? "+" : ""}
        {changePercent.toFixed(2)}%
      </div>
      <div style={{ height: 80 }}>
        <ResponsiveContainer
          width="100%"
          height="100%"
          minWidth={0}
          minHeight={80}
          initialDimension={{ width: 200, height: 80 }}
        >
          <AreaChart data={trendData}>
            <defs>
              <linearGradient id={gradientId} x1="0" y1="0" x2="0" y2="1">
                <stop offset="0%" stopColor={isUp ? "#10B981" : "#EF4444"} stopOpacity={0.3} />
                <stop offset="100%" stopColor={isUp ? "#10B981" : "#EF4444"} stopOpacity={0} />
              </linearGradient>
            </defs>
            <Area
              type="monotone"
              dataKey="v"
              stroke={isUp ? "#10B981" : "#EF4444"}
              strokeWidth={1.5}
              fill={`url(#${gradientId})`}
              isAnimationActive={false}
            />
          </AreaChart>
        </ResponsiveContainer>
      </div>
    </GlassPanel>
  );
}

// ---------------------------------------------------------------------------
// Section: Watchlist Panel
// ---------------------------------------------------------------------------

function WatchlistPanel() {
  const { items } = useWatchlist();

  return (
    <GlassPanel
      title="WATCHLIST"
      icon={<Eye size={16} strokeWidth={2} />}
    >
      {items.length === 0 ? (
        <div
          style={{
            color: "var(--text-secondary, #6B7280)",
            fontSize: 13,
            textAlign: "center",
            padding: "32px 0",
          }}
        >
          按 F 搜尋股票加入自選
        </div>
      ) : (
        <div
          style={{
            display: "flex",
            flexDirection: "column",
            gap: 2,
            maxHeight: 360,
            overflowY: "auto",
          }}
        >
          {items.slice(0, 10).map((item) => (
            <WatchlistRow key={item.symbol} item={item} />
          ))}
        </div>
      )}
    </GlassPanel>
  );
}

function WatchlistRow({
  item,
}: {
  item: { symbol: string; name: string };
}) {
  const sparkData = useMemo(() => {
    const base = 100;
    const data: number[] = [];
    let v = base;
    for (let i = 0; i < 15; i++) {
      v += (Math.random() - 0.48) * 3;
      data.push(v);
    }
    return data;
  }, []);

  // Mock price/change for display density
  const mockPrice = useMemo(() => (80 + Math.random() * 820).toFixed(2), []);
  const mockChange = useMemo(() => ((Math.random() - 0.45) * 8).toFixed(2), []);
  const isUp = parseFloat(mockChange) >= 0;

  return (
    <Link
      href={`/stocks/${encodeURIComponent(item.symbol)}`}
      style={{
        display: "flex",
        alignItems: "center",
        gap: 8,
        padding: "6px 4px",
        borderRadius: 6,
        textDecoration: "none",
        color: "inherit",
        transition: "background 0.15s",
      }}
      onMouseEnter={(e) => {
        (e.currentTarget as HTMLAnchorElement).style.background =
          "rgba(255,255,255,0.04)";
      }}
      onMouseLeave={(e) => {
        (e.currentTarget as HTMLAnchorElement).style.background = "transparent";
      }}
    >
      <div style={{ flex: 1, minWidth: 0 }}>
        <div
          style={{
            fontWeight: 700,
            fontSize: 13,
            color: "var(--foreground)",
          }}
        >
          {item.symbol}
        </div>
        <div
          style={{
            fontSize: 11,
            color: "#9CA3AF",
            overflow: "hidden",
            textOverflow: "ellipsis",
            whiteSpace: "nowrap",
          }}
        >
          {item.name}
        </div>
      </div>
      <div
        style={{
          fontSize: 13,
          fontVariantNumeric: "tabular-nums",
          color: "var(--foreground)",
          textAlign: "right",
          minWidth: 55,
        }}
      >
        {mockPrice}
      </div>
      <div
        style={{
          fontSize: 13,
          fontVariantNumeric: "tabular-nums",
          fontWeight: 600,
          color: isUp ? "var(--stock-up)" : "var(--stock-down)",
          textAlign: "right",
          minWidth: 52,
        }}
      >
        {isUp ? "\u25B2" : "\u25BC"}
        {isUp ? "+" : ""}
        {mockChange}%
      </div>
      <Sparkline data={sparkData} width={60} height={20} />
    </Link>
  );
}

// ---------------------------------------------------------------------------
// Section: Market Movers (tabbed: Gainers / Losers / Most Active)
// ---------------------------------------------------------------------------

function MarketMoversPanel({
  movers,
}: {
  movers: { gainers: MarketMover[]; losers: MarketMover[]; most_active: MarketMover[] };
}) {
  const [activeTab, setActiveTab] = useState<"gainers" | "losers" | "most_active">("gainers");

  const tabs: { key: typeof activeTab; label: string }[] = [
    { key: "gainers", label: "\u6F32\u5E45\u6392\u884C" },
    { key: "losers", label: "\u8DCC\u5E45\u6392\u884C" },
    { key: "most_active", label: "\u6210\u4EA4\u91CF\u6392\u884C" },
  ];

  return (
    <GlassPanel title="MARKET MOVERS">
      {/* Tab bar */}
      <div
        style={{
          display: "flex",
          gap: 0,
          marginBottom: 12,
          borderBottom: "1px solid rgba(255,255,255,0.06)",
        }}
      >
        {tabs.map((tab) => (
          <button
            key={tab.key}
            onClick={() => setActiveTab(tab.key)}
            style={{
              flex: 1,
              padding: "6px 0",
              fontSize: 11,
              fontWeight: activeTab === tab.key ? 700 : 500,
              textTransform: "uppercase",
              letterSpacing: "0.04em",
              color: activeTab === tab.key ? "var(--accent-cyan, #00E5FF)" : "#6B7280",
              background: "none",
              border: "none",
              borderBottom: activeTab === tab.key ? "2px solid var(--accent-cyan, #00E5FF)" : "2px solid transparent",
              cursor: "pointer",
              transition: "color 0.15s, border-color 0.15s",
            }}
          >
            {tab.label}
          </button>
        ))}
      </div>

      {/* Active tab content */}
      <MoverList items={movers[activeTab]} />
    </GlassPanel>
  );
}

function MoverList({ items }: { items: MarketMover[] }) {
  if (items.length === 0) {
    return <div style={{ fontSize: 12, color: "#6B7280" }}>No data</div>;
  }

  return (
    <div style={{ display: "flex", flexDirection: "column" }}>
      {items.slice(0, 10).map((m, i) => {
        const close = parseFloat(m.close);
        const changePercent = parseFloat(m.change_percent);
        const isUp = changePercent >= 0;
        return (
          <Link
            key={m.symbol}
            href={`/stocks/${encodeURIComponent(m.symbol)}`}
            style={{
              display: "flex",
              alignItems: "center",
              gap: 8,
              padding: "5px 2px",
              textDecoration: "none",
              color: "inherit",
              fontSize: 12,
              borderBottom: i < 9 ? "1px solid rgba(255,255,255,0.03)" : "none",
            }}
          >
            <span
              style={{
                color: "#6B7280",
                fontVariantNumeric: "tabular-nums",
                width: 18,
                fontSize: 10,
                textAlign: "right",
              }}
            >
              {i + 1}
            </span>
            <span
              style={{
                fontWeight: 600,
                color: "var(--foreground)",
                minWidth: 48,
              }}
            >
              {m.symbol.replace(".TW", "").replace(".TWO", "")}
            </span>
            <span
              style={{
                flex: 1,
                fontSize: 11,
                color: "#9CA3AF",
                overflow: "hidden",
                textOverflow: "ellipsis",
                whiteSpace: "nowrap",
              }}
            >
              {m.name}
            </span>
            <span
              style={{
                fontVariantNumeric: "tabular-nums",
                color: "var(--foreground)",
                minWidth: 52,
                textAlign: "right",
              }}
            >
              {close.toFixed(2)}
            </span>
            <span
              style={{
                fontVariantNumeric: "tabular-nums",
                fontWeight: 600,
                color: isUp ? "var(--stock-up)" : "var(--stock-down)",
                minWidth: 60,
                textAlign: "right",
              }}
            >
              {isUp ? "+" : ""}
              {changePercent.toFixed(2)}%
            </span>
          </Link>
        );
      })}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Section: Sector Heatmap Wrapper
// ---------------------------------------------------------------------------

function SectorHeatmapPanel({
  sectors,
}: {
  sectors: HeatmapSector[];
}) {
  const heatmapData = useMemo(
    () =>
      sectors.map((s) => ({
        name: s.industry,
        change: parseFloat(s.avg_change_percent),
        marketCap: s.total_volume,
      })),
    [sectors]
  );

  return (
    <GlassPanel title="SECTOR HEATMAP">
      {heatmapData.length === 0 ? (
        <div style={{ color: "var(--text-secondary)", fontSize: 13 }}>
          No sector data available
        </div>
      ) : (
        <Link href="/heatmap" style={{ display: "block", textDecoration: "none", color: "inherit" }}>
          <SectorHeatmap data={heatmapData} />
        </Link>
      )}
    </GlassPanel>
  );
}

// ---------------------------------------------------------------------------
// Section: News Feed
// ---------------------------------------------------------------------------

const severityColors = {
  green: "#10B981",
  red: "#EF4444",
  gray: "#6B7280",
};

function NewsFeedPanel() {
  return (
    <GlassPanel title="NEWS FEED">
      <div style={{ display: "flex", flexDirection: "column", gap: 0 }}>
        {NEWS_ITEMS.map((item, i) => (
          <div
            key={item.id}
            style={{
              display: "flex",
              alignItems: "flex-start",
              gap: 10,
              padding: "8px 0",
              borderBottom:
                i < NEWS_ITEMS.length - 1
                  ? "1px solid rgba(255,255,255,0.04)"
                  : "none",
            }}
          >
            {/* Severity dot */}
            <span
              style={{
                width: 6,
                height: 6,
                borderRadius: "50%",
                background: severityColors[item.severity],
                marginTop: 5,
                flexShrink: 0,
              }}
            />
            {/* Time */}
            <span
              style={{
                fontSize: 11,
                color: "#6B7280",
                fontVariantNumeric: "tabular-nums",
                minWidth: 32,
                flexShrink: 0,
              }}
            >
              {item.time}
            </span>
            {/* Content */}
            <div style={{ flex: 1, minWidth: 0 }}>
              <div
                style={{
                  fontSize: 13,
                  color: "var(--foreground)",
                  lineHeight: 1.4,
                }}
              >
                {item.title}
              </div>
              <div
                style={{
                  display: "flex",
                  alignItems: "center",
                  gap: 8,
                  marginTop: 2,
                }}
              >
                <span
                  style={{
                    fontSize: 10,
                    color: "#6B7280",
                  }}
                >
                  {item.source}
                </span>
                <span
                  style={{
                    fontSize: 10,
                    fontWeight: 600,
                    textTransform: "uppercase",
                    color: "var(--accent-cyan, #00E5FF)",
                    letterSpacing: "0.04em",
                  }}
                >
                  {item.tag}
                </span>
              </div>
            </div>
          </div>
        ))}
      </div>
    </GlassPanel>
  );
}

// ---------------------------------------------------------------------------
// Main Dashboard
// ---------------------------------------------------------------------------

export default function HomePage() {
  const { t } = useI18n();
  const { data: indices = [], isLoading: indicesLoading } = useMarketIndices();
  const { data: movers, isLoading: moversLoading } = useMarketMovers();
  const { data: heatmapData, isLoading: heatmapLoading } = useHeatmap();

  const majorIndices = useMemo(() => filterMajorIndices(indices), [indices]);
  const isLoading = indicesLoading || moversLoading || heatmapLoading;

  return (
    <div className="flex-1 flex flex-col min-h-0">
      <AmbientBackground />

      <main className="flex-1 relative z-10 max-w-[1440px] mx-auto w-full px-4 md:px-6 py-4 overflow-y-auto overflow-x-hidden">
        {/* -- 0. Market Status Bar -- */}
        <MarketStatusBar />

        {isLoading ? (
          <div className="flex items-center justify-center h-64">
            <LoadingSpinner size="lg" />
          </div>
        ) : (
          <div className="space-y-4">
            {/* -- 1. Top KPI Row (Indices) -- */}
            <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
              {majorIndices.map((idx) => {
                const val = parseFloat(idx.value);
                const cp = parseFloat(idx.change_percent);
                return (
                  <KpiCard
                    key={idx.symbol}
                    label={idx.name}
                    value={val.toLocaleString(undefined, { maximumFractionDigits: 2 })}
                    delta={`${cp >= 0 ? "+" : ""}${cp.toFixed(2)}%`}
                    direction={cp > 0 ? "up" : cp < 0 ? "down" : "flat"}
                  />
                );
              })}
            </div>

            {/* -- 2. Main Grid: Index Charts (8col) + Watchlist (4col) -- */}
            <div className="grid grid-cols-1 lg:grid-cols-12 gap-4">
              <div className="lg:col-span-8 space-y-4">
                <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                  {majorIndices.slice(0, 2).map((idx) => (
                    <IndexChartCell key={idx.symbol} idx={idx} />
                  ))}
                </div>
                <SectorHeatmapPanel sectors={heatmapData?.sectors ?? []} />
              </div>

              <div className="lg:col-span-4 h-full">
                <WatchlistPanel />
              </div>
            </div>

            {/* -- 3. Bottom Grid: Movers (6col) + News (6col) -- */}
            <div className="grid grid-cols-1 lg:grid-cols-12 gap-4 pb-8">
              <div className="lg:col-span-6">
                <MarketMoversPanel
                  movers={{
                    gainers: movers?.gainers ?? [],
                    losers: movers?.losers ?? [],
                    most_active: movers?.most_active ?? [],
                  }}
                />
              </div>
              <div className="lg:col-span-6">
                <NewsFeedPanel />
              </div>
            </div>
          </div>
        )}
      </main>
    </div>
  );
}
