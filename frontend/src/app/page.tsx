"use client";

import React, { useMemo, useState } from "react";
import Link from "next/link";
import {
  AreaChart,
  Area,
  ResponsiveContainer,
} from "recharts";
import { GlassPanel } from "@/components/stratos/primitives";
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
    time: "2h ago",
    tag: "Macro",
  },
  {
    id: 2,
    title: "TSMC beats Q1 estimates on strong AI chip demand",
    source: "Bloomberg",
    time: "4h ago",
    tag: "Earnings",
  },
  {
    id: 3,
    title: "Taiwan export orders rise 12% YoY in March",
    source: "MOEA",
    time: "6h ago",
    tag: "Data",
  },
  {
    id: 4,
    title: "Nvidia announces next-gen GPU architecture",
    source: "TechCrunch",
    time: "8h ago",
    tag: "Tech",
  },
  {
    id: 5,
    title: "USD/TWD slips below 30.5 on trade surplus data",
    source: "FX Street",
    time: "10h ago",
    tag: "FX",
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
  // Ensure the last point is close to the actual value
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

  // If fewer than 4 matched, fill from remaining indices
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
      style={{
        display: "grid",
        gridTemplateColumns: "repeat(4, 1fr)",
        gap: 12,
      }}
    >
      {majorIndices.map((idx) => (
        <IndexCell key={idx.symbol} idx={idx} />
      ))}
    </div>
  );
}

function IndexCell({ idx }: { idx: MarketIndex }) {
  const isUp = idx.change >= 0;
  const color = isUp ? "var(--stock-up)" : "var(--stock-down)";
  const trendData = useMemo(() => generateMockTrend(idx.value), [idx.value]);
  const gradientId = `idx-grad-${idx.symbol.replace(/[^a-zA-Z0-9]/g, "")}`;

  return (
    <GlassPanel>
      <div
        style={{
          fontSize: 11,
          fontWeight: 600,
          textTransform: "uppercase",
          color: "#9CA3AF",
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
        {idx.value.toLocaleString(undefined, { maximumFractionDigits: 2 })}
      </div>
      <div
        style={{
          fontSize: 13,
          fontWeight: 600,
          color,
          marginBottom: 6,
        }}
      >
        {isUp ? "\u25B2" : "\u25BC"}{" "}
        {isUp ? "+" : ""}
        {idx.change_percent.toFixed(2)}%
      </div>
      <div style={{ height: 80 }}>
        <ResponsiveContainer width="100%" height="100%">
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
      icon={
        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
          <path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z" />
          <circle cx="12" cy="12" r="3" />
        </svg>
      }
    >
      {items.length === 0 ? (
        <div
          style={{
            color: "var(--text-secondary)",
            fontSize: 13,
            textAlign: "center",
            padding: "32px 0",
          }}
        >
          No stocks tracked
        </div>
      ) : (
        <div style={{ display: "flex", flexDirection: "column", gap: 2 }}>
          {items.map((item) => (
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

  return (
    <Link
      href={`/stocks/${encodeURIComponent(item.symbol)}`}
      style={{
        display: "flex",
        alignItems: "center",
        gap: 12,
        padding: "8px 4px",
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
    { key: "most_active", label: "\u6210\u4EA4\u91CF" },
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
      {items.slice(0, 8).map((m, i) => {
        const isUp = m.change >= 0;
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
              borderBottom: i < 7 ? "1px solid rgba(255,255,255,0.03)" : "none",
            }}
          >
            <span
              style={{
                color: "#6B7280",
                fontVariantNumeric: "tabular-nums",
                width: 16,
                fontSize: 10,
              }}
            >
              {i + 1}
            </span>
            <span
              style={{
                fontWeight: 600,
                color: "var(--foreground)",
                flex: 1,
              }}
            >
              {m.symbol.replace(".TW", "").replace(".TWO", "")}
            </span>
            <span
              style={{
                fontVariantNumeric: "tabular-nums",
                color: "var(--foreground)",
              }}
            >
              {m.close.toFixed(2)}
            </span>
            <span
              style={{
                fontVariantNumeric: "tabular-nums",
                fontWeight: 600,
                color: isUp ? "var(--stock-up)" : "var(--stock-down)",
                minWidth: 56,
                textAlign: "right",
              }}
            >
              {isUp ? "+" : ""}
              {m.change_percent.toFixed(2)}%
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
        change: s.avg_change_percent,
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
        <SectorHeatmap data={heatmapData} />
      )}
    </GlassPanel>
  );
}

// ---------------------------------------------------------------------------
// Section: News Feed
// ---------------------------------------------------------------------------

function NewsFeedPanel() {
  return (
    <GlassPanel title="NEWS FEED">
      <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
        {NEWS_ITEMS.map((item) => (
          <div
            key={item.id}
            style={{
              borderBottom: "1px solid rgba(255,255,255,0.04)",
              paddingBottom: 10,
            }}
          >
            <div
              style={{
                display: "flex",
                alignItems: "center",
                gap: 8,
                marginBottom: 4,
              }}
            >
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
              <span style={{ fontSize: 10, color: "#6B7280" }}>
                {item.time}
              </span>
            </div>
            <div
              style={{
                fontSize: 13,
                color: "var(--foreground)",
                lineHeight: 1.4,
              }}
            >
              {item.title}
            </div>
            <div style={{ fontSize: 10, color: "#6B7280", marginTop: 2 }}>
              {item.source}
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

  const isLoading = indicesLoading || moversLoading || heatmapLoading;

  return (
    <>
      <AmbientBackground />

      <div
        style={{
          position: "relative",
          zIndex: 1,
          maxWidth: 1440,
          margin: "0 auto",
          padding: "16px 16px",
        }}
        className="md:px-6"
      >
        {isLoading ? (
          <div style={{ display: "flex", justifyContent: "center", padding: 48 }}>
            <LoadingSpinner size="lg" />
          </div>
        ) : (
          <>
            {/* -- 1. Index Cards (full width, 4 equal columns) -- */}
            <div style={{ marginBottom: 20 }}>
              <IndexRow indices={indices} />
            </div>

            {/* -- 2. Watchlist (5col) + Market Movers (7col) -- */}
            <div
              style={{
                display: "grid",
                gridTemplateColumns: "5fr 7fr",
                gap: 16,
                marginBottom: 20,
              }}
            >
              <WatchlistPanel />
              <MarketMoversPanel
                movers={{
                  gainers: movers?.gainers ?? [],
                  losers: movers?.losers ?? [],
                  most_active: movers?.most_active ?? [],
                }}
              />
            </div>

            {/* -- 3. Sector Heatmap (5col) + News Feed (7col) -- */}
            <div
              style={{
                display: "grid",
                gridTemplateColumns: "5fr 7fr",
                gap: 16,
              }}
            >
              <SectorHeatmapPanel
                sectors={heatmapData?.sectors ?? []}
              />
              <NewsFeedPanel />
            </div>
          </>
        )}
      </div>
    </>
  );
}
