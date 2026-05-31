"use client";

/**
 * Home page mini-rows:
 *   1. PreMarketSignalRow — "黃金交叉 8 檔 / 量價突破 12 檔 / RSI 反彈 5 檔"
 *      sourced from /signals/recent grouped counts.
 *   2. TwInstitutionalRow — "外資買超 top1 / 投信買超 top1 / 自營賣超 top1"
 *      sourced from /tw-institutional/top-net (3 parallel queries, one
 *      per kind).
 *
 * Each tile is a <Link> to a relevant drill-down. Tiles are intentionally
 * compact (~74px tall) so the row fits the home single-screen budget
 * (see app/page.tsx layout-budget comment block).
 *
 * Styling follows STRATOS: GlassPanel-like surface + accent border-top
 * keyed to the up/down semantic. CSS variables only (no hardcoded hex)
 * so light/dark mode remains consistent.
 */

import Link from "next/link";
import { useMemo } from "react";

import {
  useRecentSignals,
  useTwInstitutionalTopNet,
} from "@/hooks/use-tw-institutional";

// ---------------------------------------------------------------------------
// Shared
// ---------------------------------------------------------------------------

const MINI_TILE_HEIGHT = 74;

function MiniTileSkeleton() {
  return (
    <div
      style={{
        height: MINI_TILE_HEIGHT,
        background: "var(--glass-bg, rgba(255,255,255,0.03))",
        border: "1px solid var(--border-color, rgba(255,255,255,0.06))",
        borderRadius: "var(--glass-radius, 0)",
        backgroundImage: "var(--glass-gradient)",
      }}
    />
  );
}

function SectionHeader({
  accent,
  label,
  subLabel,
}: {
  accent: string;
  label: string;
  subLabel: string;
}) {
  return (
    <div
      style={{
        display: "flex",
        alignItems: "center",
        gap: 8,
        marginBottom: 6,
      }}
    >
      <span
        aria-hidden="true"
        style={{
          width: 3,
          height: 12,
          background: accent,
          borderRadius: 1,
        }}
      />
      <span
        className="text-[11px] font-bold uppercase tracking-[0.18em] tabular-nums"
        style={{ color: accent }}
      >
        {label}
      </span>
      <span
        className="text-[11px] font-semibold uppercase tracking-[0.04em]"
        style={{ color: "var(--text-muted)" }}
      >
        {subLabel}
      </span>
    </div>
  );
}

// ---------------------------------------------------------------------------
// PreMarketSignalRow
// ---------------------------------------------------------------------------

interface SignalTileConfig {
  key: string;          // grouped key from backend
  label: string;        // surface label
  template: string;     // /research?template= value
  accentVar: string;    // CSS var name (not value) for the top border
}

const SIGNAL_TILES: SignalTileConfig[] = [
  {
    key: "golden_cross",
    label: "黃金交叉",
    template: "golden-cross",
    accentVar: "var(--stock-up)",
  },
  {
    key: "bollinger_bounce",
    // The backend tile name "volume_breakout" isn't fired by current
    // strategies — bollinger_bounce is the closest proxy ("price punched
    // through the upper band"). Rename here when a true volume-breakout
    // strategy lands.
    label: "量價突破",
    template: "volume-breakout",
    accentVar: "var(--accent-cyan)",
  },
  {
    key: "rsi_oversold_bounce",
    label: "RSI 反彈",
    template: "rsi-bounce",
    accentVar: "var(--accent-primary)",
  },
];

function SignalMiniTile({
  cfg,
  count,
  isLoading,
}: {
  cfg: SignalTileConfig;
  count: number;
  isLoading: boolean;
}) {
  return (
    <Link
      href={`/research?template=${cfg.template}`}
      style={{
        display: "flex",
        flexDirection: "column",
        justifyContent: "space-between",
        height: MINI_TILE_HEIGHT,
        padding: "8px 12px",
        background: "var(--glass-bg, rgba(255,255,255,0.03))",
        border: "1px solid var(--border-color, rgba(255,255,255,0.06))",
        borderTop: `2px solid ${cfg.accentVar}`,
        backgroundImage: "var(--glass-gradient)",
        boxShadow: "var(--glass-shadow)",
        borderRadius: "var(--glass-radius, 0)",
        color: "inherit",
        textDecoration: "none",
        overflow: "hidden",
      }}
    >
      <div
        style={{
          fontSize: 11,
          fontWeight: 600,
          color: "var(--text-secondary, var(--text-muted))",
          letterSpacing: "0.04em",
        }}
      >
        {cfg.label}
      </div>
      <div
        style={{
          fontSize: 22,
          fontWeight: 700,
          color: cfg.accentVar,
          fontVariantNumeric: "tabular-nums",
          lineHeight: 1.05,
        }}
      >
        {isLoading ? "—" : `${count} 檔`}
      </div>
    </Link>
  );
}

export function PreMarketSignalRow() {
  const { data, isLoading } = useRecentSignals(20, 10);
  const grouped = data?.grouped ?? {};

  return (
    <section style={{ flexShrink: 0 }}>
      <SectionHeader
        accent="var(--accent-primary)"
        label="昨日 / 盤前訊號"
        subLabel="Pre-Market Signals"
      />
      <div className="grid grid-cols-3 gap-3">
        {SIGNAL_TILES.map((cfg) => (
          <SignalMiniTile
            key={cfg.key}
            cfg={cfg}
            count={grouped[cfg.key] ?? 0}
            isLoading={isLoading}
          />
        ))}
      </div>
    </section>
  );
}

// ---------------------------------------------------------------------------
// TwInstitutionalRow
// ---------------------------------------------------------------------------

interface InstKindConfig {
  kind: "foreign" | "trust" | "dealer";
  direction: "buy" | "sell";
  label: string;
  accentVar: string;
}

const INST_TILES: InstKindConfig[] = [
  {
    kind: "foreign",
    direction: "buy",
    label: "外資買超 top1",
    accentVar: "var(--stock-up)",
  },
  {
    kind: "trust",
    direction: "buy",
    label: "投信買超 top1",
    accentVar: "var(--accent-primary)",
  },
  {
    kind: "dealer",
    direction: "sell",
    label: "自營賣超 top1",
    accentVar: "var(--stock-down)",
  },
];

function formatNetAmount(rawShares: number): string {
  // FinMind nets are in shares — convert to 億 (1e8 shares ≈ 1 億 股).
  const yi = rawShares / 1e8;
  const sign = yi >= 0 ? "+" : "";
  if (Math.abs(yi) >= 0.1) return `${sign}${yi.toFixed(2)} 億股`;
  // Sub-0.1 億: fall back to 萬股 for finer resolution on small caps.
  const wan = rawShares / 1e4;
  return `${wan >= 0 ? "+" : ""}${wan.toFixed(0)} 萬股`;
}

function InstMiniTile({ cfg }: { cfg: InstKindConfig }) {
  const { data, isLoading } = useTwInstitutionalTopNet({
    kind: cfg.kind,
    direction: cfg.direction,
    limit: 1,
  });
  const top = data?.data?.[0];

  const display = useMemo(() => {
    if (isLoading) return { line1: "—", line2: "" };
    if (!top) return { line1: "尚無資料", line2: "no data" };
    return {
      line1: `${top.symbol} ${top.name}`,
      line2: formatNetAmount(top.net_amount),
    };
  }, [isLoading, top]);

  return (
    <Link
      href={`/tw-institutional?kind=${cfg.kind}&direction=${cfg.direction}`}
      style={{
        display: "flex",
        flexDirection: "column",
        justifyContent: "space-between",
        height: MINI_TILE_HEIGHT,
        padding: "8px 12px",
        background: "var(--glass-bg, rgba(255,255,255,0.03))",
        border: "1px solid var(--border-color, rgba(255,255,255,0.06))",
        borderTop: `2px solid ${cfg.accentVar}`,
        backgroundImage: "var(--glass-gradient)",
        boxShadow: "var(--glass-shadow)",
        borderRadius: "var(--glass-radius, 0)",
        color: "inherit",
        textDecoration: "none",
        overflow: "hidden",
      }}
    >
      <div
        style={{
          fontSize: 11,
          fontWeight: 600,
          color: "var(--text-secondary, var(--text-muted))",
          letterSpacing: "0.04em",
          textOverflow: "ellipsis",
          overflow: "hidden",
          whiteSpace: "nowrap",
        }}
      >
        {cfg.label}
      </div>
      <div
        style={{
          display: "flex",
          alignItems: "baseline",
          justifyContent: "space-between",
          gap: 8,
        }}
      >
        <span
          style={{
            fontSize: 13,
            fontWeight: 600,
            color: "var(--foreground)",
            textOverflow: "ellipsis",
            overflow: "hidden",
            whiteSpace: "nowrap",
            maxWidth: "60%",
          }}
        >
          {display.line1}
        </span>
        <span
          style={{
            fontSize: 14,
            fontWeight: 700,
            color: cfg.accentVar,
            fontVariantNumeric: "tabular-nums",
            flexShrink: 0,
          }}
        >
          {display.line2}
        </span>
      </div>
    </Link>
  );
}

export function TwInstitutionalRow() {
  return (
    <section style={{ flexShrink: 0 }}>
      <SectionHeader
        accent="var(--accent-cyan)"
        label="三大法人"
        subLabel="Institutional Flow"
      />
      <div className="grid grid-cols-3 gap-3">
        {INST_TILES.map((cfg) => (
          <InstMiniTile key={`${cfg.kind}-${cfg.direction}`} cfg={cfg} />
        ))}
      </div>
    </section>
  );
}

// Re-export skeleton for callers that want a placeholder before the
// query resolves (tests / Storybook).
export { MiniTileSkeleton };
