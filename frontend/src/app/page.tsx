"use client";

import React, { useMemo, useState, useEffect } from "react";
import Link from "next/link";
import { KpiCard, GlassPanel } from "@/components/stratos/primitives";
import { AmbientBackground } from "@/components/stratos/ambient";
import {
  useMarketIndices,
  useHeatmap,
} from "@/hooks/use-market-data";
import { LoadingSpinner } from "@/components/ui/loading";
import {
  PreMarketSignalRow,
  TwInstitutionalRow,
} from "@/components/home/signal-and-flow-row";
import type {
  MarketIndex,
  HeatmapSector,
  HeatmapStock,
} from "@/lib/api-client";
import { SectorNarrativePopover } from "@/components/sector-narrative-popover";
import {
  getSectorNarrative,
  getSectorLeadSentence,
  hasSectorNarrative,
} from "@/lib/sector-narratives";

// ---------------------------------------------------------------------------
// Region classification helpers (KPI row still needs TW vs US picking; the
// sector grid below is region-agnostic — we render whatever the heatmap hook
// returns, sorted by avg %).
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
// Sector aggregate model — derives from useHeatmap's `HeatmapSector`.
//
// Backend ships per-sector aggregates (`avg_change_percent`, `stock_count`)
// already, so we trust those. We additionally compute the top-3 movers by
// |change_percent| inside the sector for the focus tiles' callout chips.
// ---------------------------------------------------------------------------

interface SectorAggregate {
  sector: string;
  companyCount: number;
  avgChangePercent: number;
  topMovers: HeatmapStock[]; // sorted by |change_percent| desc, max 3
  rawSector: HeatmapSector;
}

function aggregateSectors(sectors: HeatmapSector[]): SectorAggregate[] {
  return sectors
    .map((s) => {
      const avg = parseFloat(s.avg_change_percent);
      // Highest |change %| movers first — this matches the "today's biggest
      // contributors" expectation in the focus tiles.
      const topMovers = [...s.stocks]
        .sort(
          (a, b) =>
            Math.abs(parseFloat(b.change_percent)) -
            Math.abs(parseFloat(a.change_percent)),
        )
        .slice(0, 3);
      return {
        sector: s.industry,
        companyCount: s.stock_count ?? s.stocks.length,
        avgChangePercent: Number.isFinite(avg) ? avg : 0,
        topMovers,
        rawSector: s,
      };
    })
    .filter((s) => s.companyCount > 0);
}

function sectorHref(sectorName: string): string {
  // TODO(stanley): wire dedicated sector detail. /heatmap currently shows
  // every sector — `?focus=` lets that page scroll/highlight when wired.
  return `/heatmap?focus=${encodeURIComponent(sectorName)}`;
}

function formatPct(pct: number): string {
  return `${pct >= 0 ? "+" : ""}${pct.toFixed(2)}%`;
}

// ---------------------------------------------------------------------------
// HotSectorsRow — aistockmap "今日焦點" strip.
//
// Top 3 sectors by avg change %, shown as wide horizontal tiles. Each tile
// is a `<Link>` to the sector detail (currently /heatmap?focus=…). Skeletons
// have identical dimensions so the row never reflows when data arrives.
// ---------------------------------------------------------------------------

function FocusTileSkeleton() {
  return (
    <div
      style={{
        height: 120,
        background: "var(--glass-bg, rgba(255,255,255,0.03))",
        border: "1px solid var(--border-color, rgba(255,255,255,0.06))",
        borderRadius: "var(--glass-radius, 0)",
        backgroundImage: "var(--glass-gradient)",
      }}
    />
  );
}

function FocusTile({ rank, agg }: { rank: number; agg: SectorAggregate }) {
  const isUp = agg.avgChangePercent >= 0;
  const accent = isUp ? "var(--stock-up)" : "var(--stock-down)";
  const arrow = isUp ? "▲" : "▼";

  return (
    <Link
      href={sectorHref(agg.sector)}
      style={{
        display: "block",
        height: 120,
        padding: "12px 16px",
        background: "var(--glass-bg, rgba(255,255,255,0.03))",
        border: "1px solid var(--border-color, rgba(255,255,255,0.06))",
        borderTop: `2px solid ${accent}`,
        backgroundImage: "var(--glass-gradient)",
        boxShadow: "var(--glass-shadow)",
        borderRadius: "var(--glass-radius, 0)",
        color: "inherit",
        textDecoration: "none",
        position: "relative",
        overflow: "hidden",
      }}
    >
      {/* rank chip + Ⓘ popover. The popover stops click propagation so it
          doesn't accidentally trigger the FocusTile's parent <Link>
          navigation when the user opens / closes the narrative. */}
      <div
        style={{
          position: "absolute",
          top: 8,
          right: 10,
          display: "flex",
          alignItems: "center",
          gap: 6,
        }}
      >
        <SectorNarrativePopover
          sectorName={agg.sector}
          narrative={getSectorNarrative(agg.sector)}
          href={sectorHref(agg.sector)}
          side="bottom"
        />
        <span
          style={{
            fontSize: 10,
            fontWeight: 700,
            letterSpacing: "0.08em",
            color: "var(--text-muted, #9CA3AF)",
          }}
        >
          #{rank}
        </span>
      </div>

      {/* big % */}
      <div
        style={{
          fontSize: 28,
          fontWeight: 700,
          lineHeight: 1.1,
          color: accent,
          fontVariantNumeric: "tabular-nums",
        }}
      >
        {arrow} {formatPct(agg.avgChangePercent)}
      </div>

      {/* sector label + count */}
      <div style={{ display: "flex", alignItems: "center", gap: 8, marginTop: 6 }}>
        <span
          style={{
            fontSize: 13,
            fontWeight: 600,
            color: "var(--foreground)",
            textOverflow: "ellipsis",
            overflow: "hidden",
            whiteSpace: "nowrap",
            maxWidth: 220,
          }}
        >
          {agg.sector}
        </span>
        <span
          style={{
            fontSize: 10,
            fontWeight: 700,
            padding: "2px 6px",
            color: "var(--text-muted)",
            border: "1px solid var(--border-color, rgba(255,255,255,0.08))",
            letterSpacing: "0.04em",
          }}
        >
          {agg.companyCount} 家
        </span>
      </div>

      {/* Top mover sub-headline — per Stanley's brief: one line, prominent.
          Layout: 領漲: <symbol> <name truncated> <abs+pct>. Falls back to
          the prior 3-symbol strip when name data is missing on the top
          mover, so older heatmap fixtures still render something useful. */}
      <FocusTileTopMover agg={agg} />
      {/* Theme lead sentence — only when we have a real narrative entry
          (skip generic fallback to avoid teasing a placeholder). One line,
          ellipsis-clamped to keep the FocusTile bounded; full text is in
          the popover. */}
      {hasSectorNarrative(agg.sector) && (
        <div
          title={getSectorLeadSentence(agg.sector)}
          style={{
            marginTop: 6,
            fontSize: 10.5,
            lineHeight: 1.4,
            color: "var(--text-muted, #9CA3AF)",
            overflow: "hidden",
            textOverflow: "ellipsis",
            whiteSpace: "nowrap",
          }}
        >
          {getSectorLeadSentence(agg.sector)}
        </div>
      )}
    </Link>
  );
}

/**
 * Sub-headline row for the FocusTile. Shows the top mover by |change %|
 * in a single line: "領漲: SYMBOL NAME +ABS (+PCT%)". The line is sized
 * to keep the FocusTile under the 130px height budget.
 */
function FocusTileTopMover({ agg }: { agg: SectorAggregate }) {
  const top = agg.topMovers[0];
  if (!top) return null;

  const cp = parseFloat(top.change_percent);
  const close = parseFloat(top.close);
  // Backend only ships `close` + `change_percent` — derive abs change so
  // the user sees a real number (mirrors the QuoteRow convention).
  const absChange =
    Number.isFinite(close) && Number.isFinite(cp) ? (close * cp) / 100 : null;
  const moverColor = cp >= 0 ? "var(--stock-up)" : "var(--stock-down)";
  const absText =
    absChange === null
      ? ""
      : `${absChange >= 0 ? "+" : ""}${absChange.toFixed(2)} `;

  return (
    <div
      style={{
        display: "flex",
        alignItems: "center",
        gap: 6,
        marginTop: 10,
        fontSize: 11,
        fontFamily: "var(--font-mono, monospace)",
        color: "var(--text-secondary, #9CA3AF)",
        minHeight: 16,
      }}
    >
      <span
        style={{
          fontSize: 10,
          fontWeight: 700,
          letterSpacing: "0.08em",
          color: "var(--text-muted)",
          textTransform: "uppercase",
        }}
      >
        領漲
      </span>
      <span
        style={{
          color: "var(--foreground)",
          fontWeight: 600,
          fontVariantNumeric: "tabular-nums",
        }}
      >
        {top.symbol}
      </span>
      <span
        style={{
          color: "var(--text-secondary)",
          overflow: "hidden",
          textOverflow: "ellipsis",
          whiteSpace: "nowrap",
          flex: 1,
          minWidth: 0,
        }}
      >
        {top.name}
      </span>
      <span
        style={{
          color: moverColor,
          fontVariantNumeric: "tabular-nums",
          fontWeight: 700,
          flexShrink: 0,
        }}
      >
        {absText}
        {formatPct(cp)}
      </span>
    </div>
  );
}

function HotSectorsRow({
  aggregates,
  isLoading,
}: {
  aggregates: SectorAggregate[];
  isLoading: boolean;
}) {
  const top3 = useMemo(
    () =>
      [...aggregates]
        .sort((a, b) => b.avgChangePercent - a.avgChangePercent)
        .slice(0, 3),
    [aggregates],
  );

  return (
    <section style={{ flexShrink: 0 }}>
      <div
        style={{
          display: "flex",
          alignItems: "center",
          gap: 8,
          marginBottom: 8,
        }}
      >
        <span
          aria-hidden="true"
          style={{
            width: 3,
            height: 14,
            background: "var(--accent-primary)",
            borderRadius: 1,
          }}
        />
        <span
          className="text-[11px] font-bold uppercase tracking-[0.18em] tabular-nums"
          style={{ color: "var(--accent-primary)" }}
        >
          今日焦點
        </span>
        <span
          className="text-[11px] font-semibold uppercase tracking-[0.04em]"
          style={{ color: "var(--text-muted)" }}
        >
          Top Hot Sectors
        </span>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-3">
        {isLoading || top3.length === 0
          ? Array.from({ length: 3 }).map((_, i) => <FocusTileSkeleton key={i} />)
          : top3.map((agg, i) => (
              <FocusTile key={agg.sector} rank={i + 1} agg={agg} />
            ))}
      </div>
    </section>
  );
}

// ---------------------------------------------------------------------------
// SectorCardGrid — aistockmap "產業/類別" grid.
//
// All sectors as a 4-col x N-row tile grid. Each tile is a `<Link>`; the avg
// % is color-coded green-up / red-down per the STRATOS palette. Skeletons
// fill the same slots when the hook is still loading so nothing reflows.
// ---------------------------------------------------------------------------

function SectorTileSkeleton() {
  return (
    <div
      style={{
        height: 96,
        background: "var(--glass-bg, rgba(255,255,255,0.03))",
        border: "1px solid var(--border-color, rgba(255,255,255,0.06))",
        borderRadius: "var(--glass-radius, 0)",
        backgroundImage: "var(--glass-gradient)",
      }}
    />
  );
}

function SectorTile({ agg }: { agg: SectorAggregate }) {
  const isUp = agg.avgChangePercent >= 0;
  const accent = isUp ? "var(--stock-up)" : "var(--stock-down)";
  const arrow = isUp ? "▲" : "▼";
  const topSymbol = agg.topMovers[0]?.symbol;

  return (
    <Link
      href={sectorHref(agg.sector)}
      style={{
        display: "flex",
        flexDirection: "column",
        justifyContent: "space-between",
        height: 96,
        padding: "10px 12px",
        background: "var(--glass-bg, rgba(255,255,255,0.03))",
        border: "1px solid var(--border-color, rgba(255,255,255,0.06))",
        borderLeft: `2px solid ${accent}`,
        backgroundImage: "var(--glass-gradient)",
        boxShadow: "var(--glass-shadow)",
        borderRadius: "var(--glass-radius, 0)",
        color: "inherit",
        textDecoration: "none",
        overflow: "hidden",
      }}
    >
      {/* sector name + count + narrative popover. Popover lives in the
          right-side group so it doesn't fight the count chip for space. */}
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: 8 }}>
        <span
          style={{
            fontSize: 13,
            fontWeight: 600,
            color: "var(--foreground)",
            textOverflow: "ellipsis",
            overflow: "hidden",
            whiteSpace: "nowrap",
          }}
        >
          {agg.sector}
        </span>
        <span style={{ display: "inline-flex", alignItems: "center", gap: 6, flexShrink: 0 }}>
          <SectorNarrativePopover
            sectorName={agg.sector}
            narrative={getSectorNarrative(agg.sector)}
            href={sectorHref(agg.sector)}
            side="bottom"
          />
          <span
            style={{
              fontSize: 10,
              fontWeight: 700,
              color: "var(--text-muted)",
              fontVariantNumeric: "tabular-nums",
            }}
          >
            {agg.companyCount}家
          </span>
        </span>
      </div>

      {/* big % */}
      <div
        style={{
          fontSize: 22,
          fontWeight: 700,
          color: accent,
          fontVariantNumeric: "tabular-nums",
          lineHeight: 1.1,
        }}
      >
        {arrow} {formatPct(agg.avgChangePercent)}
      </div>

      {/* top symbol (sparkline placeholder) */}
      <div
        style={{
          fontSize: 10,
          fontWeight: 600,
          color: "var(--text-muted)",
          letterSpacing: "0.08em",
          textTransform: "uppercase",
          fontFamily: "var(--font-mono, monospace)",
        }}
      >
        {topSymbol ? `領漲 ${topSymbol}` : ""}
      </div>
    </Link>
  );
}

function SectorCardGrid({
  aggregates,
  isLoading,
}: {
  aggregates: SectorAggregate[];
  isLoading: boolean;
}) {
  // Sort by avg % desc — most reactive sectors first; mirrors "Top Hot" intent
  // for the card grid as well so the eye flows top-left to bottom-right.
  const sorted = useMemo(
    () =>
      [...aggregates].sort(
        (a, b) => b.avgChangePercent - a.avgChangePercent,
      ),
    [aggregates],
  );

  // Cap at 12 (4×3) to honor the single-screen budget; remainder lives on
  // /heatmap. The "see all" link gives users a hop point.
  const visible = sorted.slice(0, 12);

  return (
    <GlassPanel
      className="flex flex-col min-h-0 flex-1"
      noPadding
      style={{ padding: 14 }}
    >
      <div
        style={{
          display: "flex",
          alignItems: "center",
          justifyContent: "space-between",
          marginBottom: 10,
        }}
      >
        <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
          <span
            aria-hidden="true"
            style={{
              width: 3,
              height: 14,
              background: "var(--accent-cyan)",
              borderRadius: 1,
            }}
          />
          <span
            className="text-[11px] font-bold uppercase tracking-[0.18em] tabular-nums"
            style={{ color: "var(--accent-cyan)" }}
          >
            產業/類別
          </span>
          <span
            className="text-[11px] font-semibold uppercase tracking-[0.04em]"
            style={{ color: "var(--text-muted)" }}
          >
            Sectors
          </span>
        </div>
        <Link
          href="/heatmap"
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

      <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-4 gap-2 auto-rows-fr">
        {isLoading || visible.length === 0
          ? Array.from({ length: 12 }).map((_, i) => (
              <SectorTileSkeleton key={i} />
            ))
          : visible.map((agg) => (
              <SectorTile key={agg.sector} agg={agg} />
            ))}
      </div>
    </GlassPanel>
  );
}

// ---------------------------------------------------------------------------
// Main single-screen dashboard
//
// Layout budget @ 1440x900 viewport (post-refactor):
//   - StratosHeader (sticky)          64px  (layout-owned)
//   - TickerStrip   (sticky)          40px  (layout-owned)
//   ─────────────────────────────────────  remaining ≈ 796px for this page
//   - py-3 padding                    24px
//   - MarketStatusBar                 28px
//   - KPI row (5 tiles, h-[104px])   104px
//   - gap (between blocks: 12*3)      36px
//   - HotSectorsRow header           ~22px
//   - HotSectorsRow tiles             120px
//   - SectorCardGrid (fills rest)    ~430px
//   - Total ≈ 764px  ✓ fits inside 796px.
//
// Hard rule: root flex column owns the screen height (h-screen on the outer
// wrapper is provided via the layout's flex-col + flex-1); within this page
// nothing scrolls vertically on desktop. Mobile / <lg drops to single column
// and is allowed to scroll (per spec).
// ---------------------------------------------------------------------------

export default function HomePage() {
  const { data: indices = [], isLoading: indicesLoading } = useMarketIndices();
  const { data: heatmapData, isLoading: heatmapLoading } = useHeatmap();

  const kpiRow = useMemo(() => pickKpiRow(indices), [indices]);

  // All sectors (TW + US merged) — the user explicitly asked for a single
  // sector grid à la aistockmap, no region split here.
  const aggregates = useMemo(
    () => aggregateSectors(heatmapData?.sectors ?? []),
    [heatmapData?.sectors],
  );

  const isLoading = indicesLoading || heatmapLoading;

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

            {/* -- 1b. Pre-Market Signal Board (黃金交叉/量價突破/RSI 反彈) --
                 Inserted between KPI row and HotSectorsRow per the
                 day-trader audit: "first thing in the morning, surface
                 what fired overnight". 3 mini-tiles, each links to
                 /research?template=... so users can drill into the
                 strategy that fired the count. */}
            <PreMarketSignalRow />

            {/* -- 1c. TW 三大法人 (外資/投信買超 + 自營賣超 top1) --
                 Directly below the signal board so chip-data and
                 strategy signals share the same row of visual weight.
                 Each tile links to /tw-institutional?kind=... for the
                 full leaderboard. */}
            <TwInstitutionalRow />

            {/* -- 2. HotSectorsRow: top 3 hottest sectors -- */}
            <HotSectorsRow aggregates={aggregates} isLoading={heatmapLoading} />

            {/* -- 3. SectorCardGrid: 4-col grid of every sector -- */}
            <SectorCardGrid aggregates={aggregates} isLoading={heatmapLoading} />
          </div>
        )}
      </main>
    </div>
  );
}
