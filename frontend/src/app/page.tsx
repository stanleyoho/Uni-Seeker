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
import { QuoteRow } from "@/components/quote-row";
import {
  useMarketIndices,
  useMarketMovers,
  useHeatmap,
} from "@/hooks/use-market-data";
import { useWatchlist } from "@/hooks/use-watchlist";
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

/** Classify an index as TW / US / Other from symbol + name patterns. */
function classifyIndexRegion(idx: MarketIndex): "TW" | "US" | "Other" {
  const s = idx.symbol || "";
  const n = idx.name || "";
  if (
    /\.TW$/i.test(s) ||
    /\.TWO$/i.test(s) ||
    /^\^TWII$/i.test(s) ||
    /^\^TPEX$/i.test(s) ||
    /TAIEX|加權|櫃買|OTC/i.test(n)
  ) {
    return "TW";
  }
  if (
    /^SPY$|^QQQ$|^DIA$|^IWM$/i.test(s) ||
    /^\^(GSPC|IXIC|DJI|NDX|SOX|RUT)$/i.test(s) ||
    /S&P|NASDAQ|Dow Jones|Russell|Philadelphia|Semiconductor|費半/i.test(n)
  ) {
    return "US";
  }
  return "Other";
}

/** Classify a mover row by its backend market enum. */
function moverRegion(m: MarketMover): "TW" | "US" | "Other" {
  if (m.market?.startsWith("TW_")) return "TW";
  if (m.market?.startsWith("US_")) return "US";
  return "Other";
}

/** Classify a heatmap sector by majority region of its constituents. */
function sectorRegion(s: HeatmapSector): "TW" | "US" | "Other" {
  let tw = 0;
  let us = 0;
  for (const st of s.stocks) {
    if (/\.TW$|\.TWO$|^\d{4,5}$/i.test(st.symbol)) tw++;
    else if (/^[A-Z]{1,5}$/.test(st.symbol)) us++;
  }
  if (tw === 0 && us === 0) return "Other";
  return tw >= us ? "TW" : "US";
}

/** Pick the headline index per market (first matching well-known symbol). */
function pickHeadline(
  indices: MarketIndex[],
  preferred: RegExp[],
): MarketIndex | undefined {
  for (const re of preferred) {
    const m = indices.find((i) => re.test(i.symbol) || re.test(i.name));
    if (m) return m;
  }
  return indices[0];
}

/** Filter indices to show major markets — first TW, then US, up to 4. */
function filterMajorIndices(indices: MarketIndex[]): MarketIndex[] {
  const tw = indices.filter((i) => classifyIndexRegion(i) === "TW");
  const us = indices.filter((i) => classifyIndexRegion(i) === "US");
  const ordered = [...tw, ...us];
  return ordered.slice(0, 4);
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

// Deterministic pseudo-random generator seeded by symbol. Used purely
// for placeholder visualisation in the watchlist row -- not for any
// security-sensitive purpose. Keeps render pure (react-hooks/purity).
function makeSeededRand(seedStr: string): () => number {
  let h = 2166136261 >>> 0;
  for (let i = 0; i < seedStr.length; i++) {
    h ^= seedStr.charCodeAt(i);
    h = Math.imul(h, 16777619);
  }
  return () => {
    h += 0x6d2b79f5;
    let t = h;
    t = Math.imul(t ^ (t >>> 15), t | 1);
    t ^= t + Math.imul(t ^ (t >>> 7), t | 61);
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

function WatchlistRow({
  item,
}: {
  item: { symbol: string; name: string };
}) {
  const sparkData = useMemo(() => {
    const rand = makeSeededRand(`spark:${item.symbol}`);
    const base = 100;
    const data: number[] = [];
    let v = base;
    for (let i = 0; i < 15; i++) {
      v += (rand() - 0.48) * 3;
      data.push(v);
    }
    return data;
  }, [item.symbol]);

  // Mock price/change for display density -- seeded by symbol so each row
  // renders the same value across renders (otherwise React Compiler
  // flags `Math.random` as impure during render).
  const mockPrice = useMemo(() => {
    const rand = makeSeededRand(`price:${item.symbol}`);
    return (80 + rand() * 820).toFixed(2);
  }, [item.symbol]);
  const mockChange = useMemo(() => {
    const rand = makeSeededRand(`change:${item.symbol}`);
    return ((rand() - 0.45) * 8).toFixed(2);
  }, [item.symbol]);
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
  title = "MARKET MOVERS",
}: {
  movers: { gainers: MarketMover[]; losers: MarketMover[]; most_active: MarketMover[] };
  title?: string;
}) {
  const [activeTab, setActiveTab] = useState<"gainers" | "losers" | "most_active">("gainers");

  const tabs: { key: typeof activeTab; label: string }[] = [
    { key: "gainers", label: "\u6F32\u5E45\u6392\u884C" },
    { key: "losers", label: "\u8DCC\u5E45\u6392\u884C" },
    { key: "most_active", label: "\u6210\u4EA4\u91CF\u6392\u884C" },
  ];

  return (
    <GlassPanel title={title}>
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

  // Delegate the full quote-card shape to the canonical QuoteRow so this
  // panel matches every other stock-listing surface (heatmap, search,
  // signals). MarketMover ships every field we need (symbol, name,
  // close, change, change_percent) so no derivation is required.
  return (
    <div style={{ display: "flex", flexDirection: "column" }}>
      {items.slice(0, 10).map((m, i) => (
        <QuoteRow
          key={m.symbol}
          rank={i + 1}
          symbol={m.symbol}
          name={m.name}
          price={m.close}
          change={m.change}
          changePercent={m.change_percent}
          market={m.market}
          href={`/stocks/${encodeURIComponent(m.symbol)}`}
        />
      ))}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Section: Sector Heatmap Wrapper
// ---------------------------------------------------------------------------

function SectorHeatmapPanel({
  sectors,
  title = "SECTOR HEATMAP",
}: {
  sectors: HeatmapSector[];
  title?: string;
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
    <GlassPanel title={title}>
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
// Section: Market Section Header (TAIWAN MARKET / US MARKET divider)
// ---------------------------------------------------------------------------

function MarketSectionHeader({
  region,
  label,
  sublabel,
}: {
  region: "TW" | "US";
  label: string;
  sublabel?: string;
}) {
  const accent =
    region === "TW" ? "var(--accent-primary)" : "var(--accent-cyan)";
  return (
    <div
      className="flex items-center gap-3 pt-2 pb-1"
      role="heading"
      aria-level={2}
    >
      <span
        aria-hidden="true"
        style={{
          width: 4,
          height: 18,
          background: accent,
          borderRadius: 1,
        }}
      />
      <span
        className="text-[11px] font-bold uppercase tracking-[0.18em] tabular-nums"
        style={{ color: accent }}
      >
        {region}
      </span>
      <span
        className="text-[15px] font-semibold uppercase tracking-[0.04em]"
        style={{ color: "var(--foreground)" }}
      >
        {label}
      </span>
      {sublabel && (
        <span
          className="text-[11px] uppercase tracking-[0.08em]"
          style={{ color: "var(--text-muted)" }}
        >
          {sublabel}
        </span>
      )}
      <span
        aria-hidden="true"
        className="flex-1 ml-2"
        style={{
          height: 1,
          background:
            "linear-gradient(to right, var(--border-color), transparent)",
        }}
      />
    </div>
  );
}

// ---------------------------------------------------------------------------
// Section: Per-market block (Headline tile + chart + heatmap + movers)
// ---------------------------------------------------------------------------

function MarketSection({
  region,
  label,
  sublabel,
  headline,
  chartIndex,
  sectors,
  movers,
}: {
  region: "TW" | "US";
  label: string;
  sublabel?: string;
  headline?: MarketIndex;
  chartIndex?: MarketIndex;
  sectors: HeatmapSector[];
  movers: { gainers: MarketMover[]; losers: MarketMover[]; most_active: MarketMover[] };
}) {
  const heatmapTitle = region === "TW" ? "TW SECTOR HEATMAP" : "US SECTOR HEATMAP";
  const moversTitle = region === "TW" ? "TW MARKET MOVERS" : "US MARKET MOVERS";
  return (
    <section className="space-y-3" aria-label={`${label} dashboard`}>
      <MarketSectionHeader region={region} label={label} sublabel={sublabel} />

      <div className="grid grid-cols-1 lg:grid-cols-12 gap-4">
        {/* Headline KPI tile */}
        {headline && (
          <div className="lg:col-span-3">
            <KpiCard
              label={headline.name}
              value={parseFloat(headline.value).toLocaleString(undefined, {
                maximumFractionDigits: 2,
              })}
              delta={`${parseFloat(headline.change_percent) >= 0 ? "+" : ""}${parseFloat(
                headline.change_percent,
              ).toFixed(2)}%`}
              direction={
                parseFloat(headline.change_percent) > 0
                  ? "up"
                  : parseFloat(headline.change_percent) < 0
                  ? "down"
                  : "flat"
              }
            />
          </div>
        )}
        {/* Sparkline chart for the same headline (or second index) */}
        {chartIndex && (
          <div className={headline ? "lg:col-span-9" : "lg:col-span-12"}>
            <IndexChartCell idx={chartIndex} />
          </div>
        )}
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-12 gap-4">
        <div className="lg:col-span-7">
          <SectorHeatmapPanel sectors={sectors} title={heatmapTitle} />
        </div>
        <div className="lg:col-span-5">
          <MarketMoversPanel movers={movers} title={moversTitle} />
        </div>
      </div>
    </section>
  );
}

// ---------------------------------------------------------------------------
// Main Dashboard
// ---------------------------------------------------------------------------

export default function HomePage() {
  const { data: indices = [], isLoading: indicesLoading } = useMarketIndices();
  const { data: movers, isLoading: moversLoading } = useMarketMovers();
  const { data: heatmapData, isLoading: heatmapLoading } = useHeatmap();

  const majorIndices = useMemo(() => filterMajorIndices(indices), [indices]);

  // Split indices, movers, sectors by region — single API call, client-side
  // routing. Avoids extra backend round-trips (per scope: preserve data flow).
  const twIndices = useMemo(
    () => indices.filter((i) => classifyIndexRegion(i) === "TW"),
    [indices],
  );
  const usIndices = useMemo(
    () => indices.filter((i) => classifyIndexRegion(i) === "US"),
    [indices],
  );

  const twHeadline = useMemo(
    () =>
      pickHeadline(twIndices, [
        /^\^TWII$/i,
        /TAIEX|加權/i,
        /0050/i,
      ]),
    [twIndices],
  );
  const twChartIndex = useMemo(
    () =>
      pickHeadline(twIndices, [
        /0050/i,
        /^\^TPEX$/i,
        /OTC|櫃買/i,
      ]) ?? twIndices.find((i) => i.symbol !== twHeadline?.symbol),
    [twIndices, twHeadline?.symbol],
  );

  const usHeadline = useMemo(
    () =>
      pickHeadline(usIndices, [
        /^SPY$/i,
        /S&P/i,
        /^\^GSPC$/i,
      ]),
    [usIndices],
  );
  const usChartIndex = useMemo(
    () =>
      pickHeadline(usIndices, [
        /^QQQ$/i,
        /NASDAQ/i,
        /^\^IXIC$/i,
        /^\^SOX$/i,
        /^\^DJI$/i,
      ]) ?? usIndices.find((i) => i.symbol !== usHeadline?.symbol),
    [usIndices, usHeadline?.symbol],
  );

  const twSectors = useMemo(
    () => (heatmapData?.sectors ?? []).filter((s) => sectorRegion(s) === "TW"),
    [heatmapData?.sectors],
  );
  const usSectors = useMemo(
    () => (heatmapData?.sectors ?? []).filter((s) => sectorRegion(s) === "US"),
    [heatmapData?.sectors],
  );

  const twMovers = useMemo(
    () => ({
      gainers: (movers?.gainers ?? []).filter((m) => moverRegion(m) === "TW"),
      losers: (movers?.losers ?? []).filter((m) => moverRegion(m) === "TW"),
      most_active: (movers?.most_active ?? []).filter(
        (m) => moverRegion(m) === "TW",
      ),
    }),
    [movers],
  );
  const usMovers = useMemo(
    () => ({
      gainers: (movers?.gainers ?? []).filter((m) => moverRegion(m) === "US"),
      losers: (movers?.losers ?? []).filter((m) => moverRegion(m) === "US"),
      most_active: (movers?.most_active ?? []).filter(
        (m) => moverRegion(m) === "US",
      ),
    }),
    [movers],
  );

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
          <div className="space-y-6">
            {/* -- 1. Top KPI Row (mixed indices, ordered TW then US) -- */}
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

            {/* -- 2. TAIWAN MARKET section -- */}
            <MarketSection
              region="TW"
              label="Taiwan Market"
              sublabel="台股總覽"
              headline={twHeadline}
              chartIndex={twChartIndex}
              sectors={twSectors}
              movers={twMovers}
            />

            {/* -- 3. US MARKET section -- */}
            <MarketSection
              region="US"
              label="US Market"
              sublabel="美股總覽"
              headline={usHeadline}
              chartIndex={usChartIndex}
              sectors={usSectors}
              movers={usMovers}
            />

            {/* -- 4. Footer Grid: Watchlist + News (global, market-agnostic) -- */}
            <div className="grid grid-cols-1 lg:grid-cols-12 gap-4 pb-8">
              <div className="lg:col-span-5">
                <WatchlistPanel />
              </div>
              <div className="lg:col-span-7">
                <NewsFeedPanel />
              </div>
            </div>
          </div>
        )}
      </main>
    </div>
  );
}
