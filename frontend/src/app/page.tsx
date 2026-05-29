"use client";

import React, { useMemo, useState, useEffect } from "react";
import Link from "next/link";
import { KpiCard, GlassPanel } from "@/components/stratos/primitives";
import { SectorHeatmap } from "@/components/stratos/charts";
import { AmbientBackground } from "@/components/stratos/ambient";
import { QuoteRow } from "@/components/quote-row";
import {
  useMarketIndices,
  useMarketMovers,
  useHeatmap,
} from "@/hooks/use-market-data";
import { LoadingSpinner } from "@/components/ui/loading";
import type {
  MarketIndex,
  MarketMover,
  HeatmapSector,
} from "@/lib/api-client";

// ---------------------------------------------------------------------------
// Region classification helpers (single-screen dashboard splits TW vs US into
// two columns; we still receive one merged payload per hook).
// ---------------------------------------------------------------------------

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

function moverRegion(m: MarketMover): "TW" | "US" | "Other" {
  if (m.market?.startsWith("TW_")) return "TW";
  if (m.market?.startsWith("US_")) return "US";
  return "Other";
}

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

/**
 * Pick a fixed 5-tile KPI row: 加權指數 → 櫃買 → NASDAQ → DJIA → S&P 500.
 * Falls back to the first available TW / US index when a preferred symbol
 * is missing so the row never collapses below the user's intent.
 *
 * Per-tile label normalization happens at render time (see ``displayLabel``)
 * to drop the "TAIEX" prefix from the 加權指數 tile.
 */
function pickKpiRow(indices: MarketIndex[]): MarketIndex[] {
  const tw = indices.filter((i) => classifyIndexRegion(i) === "TW");
  const us = indices.filter((i) => classifyIndexRegion(i) === "US");

  const pick = (pool: MarketIndex[], patterns: RegExp[]): MarketIndex | undefined => {
    for (const re of patterns) {
      const hit = pool.find((i) => re.test(i.symbol) || re.test(i.name));
      if (hit) return hit;
    }
    return undefined;
  };

  const taiex = pick(tw, [/^\^TWII$/i, /TAIEX|加權/i]) ?? tw[0];
  const otc = pick(tw, [/櫃買|OTC|TPEX/i]) ?? tw.find((i) => i.symbol !== taiex?.symbol);
  const nasdaq = pick(us, [/^\^IXIC$/i, /NASDAQ/i]) ?? us[0];
  const dow = pick(us, [/^\^DJI$/i, /Dow|DJIA|道瓊/i]) ?? us.find((i) => i.symbol !== nasdaq?.symbol);
  const sp = pick(us, [/^SPY$/i, /^\^GSPC$/i, /S&P|標準普爾|標普/i]);

  return [taiex, otc, nasdaq, dow, sp].filter(
    (i): i is MarketIndex => i !== undefined,
  );
}

/**
 * Normalize KPI tile labels — drop the "TAIEX" English prefix from the
 * 加權指數 tile, prefer the canonical Chinese index name everywhere else.
 */
function displayIndexLabel(idx: MarketIndex): string {
  const raw = idx.name ?? idx.symbol;
  // "TAIEX (加權指數)" → "加權指數" (drop the English prefix, keep the bracketed Chinese name).
  const stripped = raw.replace(/^\s*TAIEX\s*\(?\s*/i, "").replace(/\)\s*$/, "").trim();
  return stripped || raw;
}

// ---------------------------------------------------------------------------
// Market Status Bar (single-line, compact)
// ---------------------------------------------------------------------------

function getMarketStatus(): {
  tw: { label: string; status: "open" | "closed" | "pre" };
  us: { label: string; status: "open" | "closed" | "pre" };
  dateStr: string;
} {
  const now = new Date();
  const tstOffset = 8 * 60;
  const localOffset = now.getTimezoneOffset();
  const tst = new Date(now.getTime() + (tstOffset + localOffset) * 60000);
  const h = tst.getHours();
  const m = tst.getMinutes();
  const mins = h * 60 + m;
  const day = tst.getDay();
  const isWeekday = day >= 1 && day <= 5;

  let twStatus: "open" | "closed" | "pre" = "closed";
  if (isWeekday) {
    if (mins >= 540 && mins < 810) twStatus = "open";
    else if (mins >= 480 && mins < 540) twStatus = "pre";
  }

  let usStatus: "open" | "closed" | "pre" = "closed";
  if (mins >= 1290 || mins < 240) {
    const isUsDay =
      (mins >= 1290 && day >= 1 && day <= 5) ||
      (mins < 240 && day >= 2 && day <= 6);
    if (isUsDay) usStatus = "open";
  } else if (mins >= 1260 && mins < 1290 && isWeekday) {
    usStatus = "pre";
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
        height: 28,
        background: "var(--bg-secondary, rgba(255,255,255,0.03))",
        borderBottom: "1px solid var(--border-color, rgba(255,255,255,0.06))",
        display: "flex",
        alignItems: "center",
        justifyContent: "space-between",
        padding: "0 12px",
        fontSize: 11,
        fontFamily: "var(--font-mono, monospace)",
        color: "var(--text-muted, #9CA3AF)",
        borderRadius: "var(--glass-radius, 0)",
        flexShrink: 0,
      }}
    >
      <div style={{ display: "flex", alignItems: "center", gap: 16 }}>
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
// Column header (sits above each per-market grid track, replacing the old
// red/cyan full-width MarketSectionHeader bar that broke single-screen fit).
// ---------------------------------------------------------------------------

function ColumnHeader({
  region,
  label,
}: {
  region: "TW" | "US";
  label: string;
}) {
  const accent =
    region === "TW" ? "var(--accent-primary)" : "var(--accent-cyan)";
  return (
    <div className="flex items-center gap-2" style={{ height: 18 }}>
      <span
        aria-hidden="true"
        style={{
          width: 3,
          height: 14,
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
        className="text-[12px] font-semibold uppercase tracking-[0.04em]"
        style={{ color: "var(--foreground)" }}
      >
        {label}
      </span>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Sector heatmap panel (fixed-height container so the inner heatmap fills,
// not overflows). Heatmap is clickable → /heatmap.
// ---------------------------------------------------------------------------

function SectorHeatmapPanel({
  sectors,
  title,
}: {
  sectors: HeatmapSector[];
  title: string;
}) {
  const heatmapData = useMemo(
    () =>
      sectors.map((s) => ({
        name: s.industry,
        change: parseFloat(s.avg_change_percent),
        marketCap: s.total_volume,
      })),
    [sectors],
  );

  return (
    <GlassPanel
      title={title}
      className="h-full"
      style={{ padding: 16, display: "flex", flexDirection: "column", minHeight: 0 }}
    >
      <div style={{ flex: 1, minHeight: 0, overflow: "hidden" }}>
        {heatmapData.length === 0 ? (
          <div style={{ color: "var(--text-secondary)", fontSize: 12 }}>
            No sector data available
          </div>
        ) : (
          <Link
            href="/heatmap"
            style={{ display: "block", textDecoration: "none", color: "inherit", height: "100%" }}
          >
            <SectorHeatmap data={heatmapData} />
          </Link>
        )}
      </div>
    </GlassPanel>
  );
}

// ---------------------------------------------------------------------------
// Market movers panel — tabbed (Gainers / Losers / Most Active), top 5 only.
// Full list lives on /scanner; a See-all link is rendered in the panel header.
// ---------------------------------------------------------------------------

function MarketMoversPanel({
  movers,
  title,
}: {
  movers: { gainers: MarketMover[]; losers: MarketMover[]; most_active: MarketMover[] };
  title: string;
}) {
  const [activeTab, setActiveTab] = useState<"gainers" | "losers" | "most_active">("gainers");

  const tabs: { key: typeof activeTab; label: string }[] = [
    { key: "gainers", label: "漲幅" },
    { key: "losers", label: "跌幅" },
    { key: "most_active", label: "成交量" },
  ];

  const items = movers[activeTab].slice(0, 5);

  return (
    <GlassPanel
      className="h-full"
      style={{ padding: 16, display: "flex", flexDirection: "column", minHeight: 0 }}
    >
      {/* Title + See-all link row */}
      <div
        style={{
          display: "flex",
          alignItems: "center",
          justifyContent: "space-between",
          marginBottom: 8,
        }}
      >
        <span
          style={{
            fontSize: 14,
            fontWeight: 700,
            textTransform: "uppercase",
            letterSpacing: "-0.04em",
            color: "#9CA3AF",
          }}
        >
          {title}
        </span>
        <Link
          href="/scanner"
          style={{
            fontSize: 11,
            color: "var(--accent-cyan)",
            textDecoration: "none",
            textTransform: "uppercase",
            letterSpacing: "0.08em",
          }}
        >
          See all →
        </Link>
      </div>

      {/* Tab bar */}
      <div
        style={{
          display: "flex",
          gap: 0,
          marginBottom: 6,
          borderBottom: "1px solid rgba(255,255,255,0.06)",
          flexShrink: 0,
        }}
      >
        {tabs.map((tab) => (
          <button
            key={tab.key}
            onClick={() => setActiveTab(tab.key)}
            style={{
              flex: 1,
              padding: "4px 0",
              fontSize: 11,
              fontWeight: activeTab === tab.key ? 700 : 500,
              textTransform: "uppercase",
              letterSpacing: "0.04em",
              color: activeTab === tab.key ? "var(--accent-cyan, #00E5FF)" : "#6B7280",
              background: "none",
              border: "none",
              borderBottom:
                activeTab === tab.key
                  ? "2px solid var(--accent-cyan, #00E5FF)"
                  : "2px solid transparent",
              cursor: "pointer",
              transition: "color 0.15s, border-color 0.15s",
            }}
          >
            {tab.label}
          </button>
        ))}
      </div>

      {/* Active tab content — top 5 only, fills remaining height */}
      <div style={{ flex: 1, minHeight: 0, overflow: "hidden" }}>
        {items.length === 0 ? (
          <div style={{ fontSize: 12, color: "#6B7280", padding: "8px 0" }}>No data</div>
        ) : (
          <div style={{ display: "flex", flexDirection: "column" }}>
            {items.map((m, i) => (
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
        )}
      </div>
    </GlassPanel>
  );
}

// ---------------------------------------------------------------------------
// Main single-screen dashboard
//
// Layout budget @ 1440x900 viewport:
//   - StratosHeader (sticky)          64px  (layout-owned)
//   - TickerStrip   (sticky)          40px  (layout-owned)
//   ─────────────────────────────────────  remaining ≈ 796px for this page
//   - py-4 padding                    32px
//   - MarketStatusBar                 28px
//   - KPI row (4 tiles, h-[104px])   104px
//   - gap (3 between blocks: 12*3)    36px
//   - Body grid (2-col TW | US)
//       ColumnHeader                  18px
//       Heatmap panel                280px
//       Movers panel                 260px
//   - Total ≈ 758px  ✓ fits inside 796px on desktop ≥ lg.
//
// Hard rule: root flex column owns the screen height (h-screen on the outer
// wrapper is provided via the layout's flex-col + flex-1); within this page
// nothing scrolls vertically on desktop. Mobile / <lg drops to grid-cols-1
// and is allowed to scroll (per spec).
// ---------------------------------------------------------------------------

export default function HomePage() {
  const { data: indices = [], isLoading: indicesLoading } = useMarketIndices();
  const { data: movers, isLoading: moversLoading } = useMarketMovers();
  const { data: heatmapData, isLoading: heatmapLoading } = useHeatmap();

  const kpiRow = useMemo(() => pickKpiRow(indices), [indices]);

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
      most_active: (movers?.most_active ?? []).filter((m) => moverRegion(m) === "TW"),
    }),
    [movers],
  );
  const usMovers = useMemo(
    () => ({
      gainers: (movers?.gainers ?? []).filter((m) => moverRegion(m) === "US"),
      losers: (movers?.losers ?? []).filter((m) => moverRegion(m) === "US"),
      most_active: (movers?.most_active ?? []).filter((m) => moverRegion(m) === "US"),
    }),
    [movers],
  );

  const isLoading = indicesLoading || moversLoading || heatmapLoading;

  return (
    // The inline `--page-h` var pins this page to the viewport minus the
    // sticky StratosHeader (64px) + TickerStrip (40px). Without this, the
    // outer body is `min-h-full flex-col` which lets the page grow past
    // the viewport and forces a body-level scroll. The cap only applies
    // on lg+ (desktop) — mobile is allowed to scroll per spec.
    <div
      className="flex-1 flex flex-col min-h-0 relative lg:max-h-[var(--page-h)] lg:h-[var(--page-h)]"
      style={{ ["--page-h" as string]: "calc(100vh - 104px)" } as React.CSSProperties}
    >
      <AmbientBackground />

      <main
        className="flex-1 relative z-10 max-w-[1440px] mx-auto w-full px-4 md:px-6 py-3 flex flex-col min-h-0 overflow-x-hidden lg:overflow-y-hidden overflow-y-auto"
      >
        {/* -- 0. Market Status Bar (single line) -- */}
        <MarketStatusBar />

        {isLoading ? (
          <div className="flex items-center justify-center flex-1">
            <LoadingSpinner size="lg" />
          </div>
        ) : (
          <div className="flex flex-col flex-1 min-h-0 gap-3 mt-3">
            {/* -- 1. KPI Row: 5 indices (加權指數 / 櫃買 / NASDAQ / DJIA / S&P), identical tile size -- */}
            <div
              className="grid grid-cols-2 lg:grid-cols-5 gap-3"
              style={{ flexShrink: 0 }}
            >
              {kpiRow.map((idx) => {
                const val = parseFloat(idx.value);
                const cp = parseFloat(idx.change_percent);
                // abs change = value * change_percent / 100, derived since
                // the index payload may not carry an explicit absolute change.
                const absChange = (val * cp) / 100;
                return (
                  <div key={idx.symbol} className="lg:h-[104px]">
                    <KpiCard
                      label={displayIndexLabel(idx)}
                      value={val.toLocaleString(undefined, {
                        maximumFractionDigits: 2,
                      })}
                      delta={`${absChange >= 0 ? "+" : ""}${absChange.toFixed(2)} (${cp >= 0 ? "+" : ""}${cp.toFixed(2)}%)`}
                      direction={cp > 0 ? "up" : cp < 0 ? "down" : "flat"}
                    />
                  </div>
                );
              })}
            </div>

            {/* -- 2. Body: 2-col TW | US, each col = heatmap + movers stacked -- */}
            <div
              className="grid grid-cols-1 lg:grid-cols-2 gap-3 flex-1 min-h-0"
            >
              {/* TW column */}
              <div className="flex flex-col gap-2 min-h-0">
                <ColumnHeader region="TW" label="Taiwan Market" />
                <div className="grid grid-rows-[280px_minmax(0,1fr)] gap-3 flex-1 min-h-0">
                  <SectorHeatmapPanel
                    sectors={twSectors}
                    title="TW SECTOR HEATMAP"
                  />
                  <MarketMoversPanel
                    movers={twMovers}
                    title="TW MARKET MOVERS"
                  />
                </div>
              </div>

              {/* US column */}
              <div className="flex flex-col gap-2 min-h-0">
                <ColumnHeader region="US" label="US Market" />
                <div className="grid grid-rows-[280px_minmax(0,1fr)] gap-3 flex-1 min-h-0">
                  <SectorHeatmapPanel
                    sectors={usSectors}
                    title="US SECTOR HEATMAP"
                  />
                  <MarketMoversPanel
                    movers={usMovers}
                    title="US MARKET MOVERS"
                  />
                </div>
              </div>
            </div>
          </div>
        )}
      </main>
    </div>
  );
}
