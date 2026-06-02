"use client";

/**
 * ETF 折溢價監控 (/research/etf-arbitrage).
 *
 * Models the twetf.com core feature ported into Uni-Seeker:
 *
 *     premium% = (market_price - estimated_nav) / estimated_nav * 100
 *
 * Layout (mirrors the reference screenshot in
 * `warroom/data/ref-twetf-home.png`):
 *
 *   1. Header + 重新整理 button + data-source caption.
 *   2. Stats row — 5 mini KPI tiles (監控 / 溢價 / 折價 / 巴菲特 / 市場情緒).
 *   3. 情緒雷達 + 市場溫度計 (two GlassPanels). The radar bars come
 *      directly from the per-row sentiment_level breakdown; the
 *      thermometer reuses max-premium / max-discount from stats.
 *   4. 3 排行榜並列 — 溢價 top 3, 折價 top 3, 成交量 top 3.
 *   5. Search input + filter chips (全部 / 溢價 / 折價 / 股票型 / 主動式 /
 *      債券型 / 槓桿反向 / ⭐ 自選).
 *   6. Sort dropdown (折溢價絕對值 / 溢價高低 / 折價深淺 / 代號 / 成交量).
 *   7. Main table — 代號 / 名稱 / 類型 / 預估淨值 / 市價 / 漲跌 /
 *      折溢價% / 情緒燈號 / 趨勢 / 成交量 / ⭐.
 *
 * The 5-level sentiment palette is hard-coded here (W4-B helper not
 * available yet at agent-spawn time) and will be lifted into a shared
 * module once W4-B lands.
 */

import { useMemo, useState } from "react";
import { useETFArbitrage } from "@/hooks/use-market-data";
import { GlassPanel, KpiCard, ClippedButton } from "@/components/stratos/primitives";
import { LoadingSpinner } from "@/components/ui/loading";
import { AmbientBackground } from "@/components/stratos/ambient";
import { getErrorMessage } from "@/lib/type-guards";
import type {
  ETFArbitrageRow,
  ETFArbitrageSentiment,
  ETFArbitrageType,
} from "@/lib/api-client";

// ──────────────────────────────────────────────────────────────────
// Sentiment palette (5-level taxonomy).
// Lifted into a shared helper when W4-B ships.
// ──────────────────────────────────────────────────────────────────

const SENTIMENT_META: Record<
  ETFArbitrageSentiment,
  { emoji: string; color: string; label: string }
> = {
  過熱: { emoji: "🔴", color: "var(--stock-up, #FF4D4F)", label: "過熱" },
  溢價: { emoji: "🟠", color: "#FF8C42", label: "溢價" },
  平價: { emoji: "⚪", color: "var(--text-muted, #9CA3AF)", label: "平價" },
  折價: { emoji: "🔵", color: "var(--accent-cyan, #00E5FF)", label: "折價" },
  深折: { emoji: "🟣", color: "#A855F7", label: "深折" },
};

const SENTIMENT_ORDER: ETFArbitrageSentiment[] = [
  "過熱",
  "溢價",
  "平價",
  "折價",
  "深折",
];

const TYPE_FILTERS: { value: "all" | ETFArbitrageType; label: string }[] = [
  { value: "all", label: "全部" },
  { value: "股票型", label: "股票型" },
  { value: "主動式", label: "主動式" },
  { value: "債券型", label: "債券型" },
  { value: "槓桿反向", label: "槓桿反向" },
];

const DIRECTION_FILTERS: {
  value: "all" | "premium" | "discount";
  label: string;
}[] = [
  { value: "all", label: "全部方向" },
  { value: "premium", label: "溢價" },
  { value: "discount", label: "折價" },
];

type SortKey =
  | "abs_premium"
  | "premium_desc"
  | "discount_desc"
  | "symbol"
  | "volume";

const SORT_OPTIONS: { value: SortKey; label: string }[] = [
  { value: "abs_premium", label: "折溢價絕對值" },
  { value: "premium_desc", label: "溢價高低" },
  { value: "discount_desc", label: "折價深淺" },
  { value: "symbol", label: "代號" },
  { value: "volume", label: "成交量" },
];

// ──────────────────────────────────────────────────────────────────
// Helpers
// ──────────────────────────────────────────────────────────────────

function num(s: string): number {
  // Tolerant of "+1.41" / "-0.50" / "0.00" — all valid Number() input.
  return Number(s);
}

function signedColor(value: string): string {
  const n = num(value);
  if (n > 0) return "var(--stock-up, #FF4D4F)";
  if (n < 0) return "var(--stock-down, #00E5FF)";
  return "var(--text-muted)";
}

function classifyRow(rows: readonly ETFArbitrageRow[]) {
  // Bucket counts by sentiment level — drives the 情緒雷達 widget.
  const counts = new Map<ETFArbitrageSentiment, number>();
  for (const r of rows) {
    counts.set(r.sentiment_level, (counts.get(r.sentiment_level) ?? 0) + 1);
  }
  return counts;
}

// ──────────────────────────────────────────────────────────────────
// Page
// ──────────────────────────────────────────────────────────────────

export default function ETFArbitragePage() {
  const [typeFilter, setTypeFilter] = useState<"all" | ETFArbitrageType>("all");
  const [direction, setDirection] = useState<"all" | "premium" | "discount">(
    "all",
  );
  const [search, setSearch] = useState("");
  const [sortKey, setSortKey] = useState<SortKey>("abs_premium");

  const { data, isLoading, error, refetch } = useETFArbitrage({
    market: "TW",
    type: typeFilter,
    direction,
    limit: 200,
  });

  // Stabilize `rows` identity across renders so the downstream useMemo
  // hooks have a clean dependency. Without this wrap, `data?.data ?? []`
  // produces a fresh `[]` literal each render and forces recomputation.
  const rows = useMemo<ETFArbitrageRow[]>(() => data?.data ?? [], [data]);
  const stats = data?.stats;

  // Client-side search + sort. The server already filters by direction +
  // type so this layer only handles the text search and sort key —
  // keeping the server contract clean and predictable.
  const filteredSorted = useMemo<ETFArbitrageRow[]>(() => {
    const q = search.trim().toLowerCase();
    const out = q
      ? rows.filter(
          (r) =>
            r.symbol.toLowerCase().includes(q) ||
            r.name.toLowerCase().includes(q),
        )
      : [...rows];
    out.sort((a, b) => {
      switch (sortKey) {
        case "premium_desc":
          return num(b.premium_percent) - num(a.premium_percent);
        case "discount_desc":
          return num(a.premium_percent) - num(b.premium_percent);
        case "symbol":
          return a.symbol.localeCompare(b.symbol);
        case "volume":
          return b.volume_lots - a.volume_lots;
        case "abs_premium":
        default:
          return Math.abs(num(b.premium_percent)) - Math.abs(num(a.premium_percent));
      }
    });
    return out;
  }, [rows, search, sortKey]);

  // Top-3 rankings: derived from the unfiltered (but direction/type
  // filtered) row set so the rankings reflect the current scope.
  const topPremium = useMemo(
    () =>
      [...rows]
        .filter((r) => num(r.premium_percent) > 0)
        .sort((a, b) => num(b.premium_percent) - num(a.premium_percent))
        .slice(0, 3),
    [rows],
  );
  const topDiscount = useMemo(
    () =>
      [...rows]
        .filter((r) => num(r.premium_percent) < 0)
        .sort((a, b) => num(a.premium_percent) - num(b.premium_percent))
        .slice(0, 3),
    [rows],
  );
  const topVolume = useMemo(
    () => [...rows].sort((a, b) => b.volume_lots - a.volume_lots).slice(0, 3),
    [rows],
  );

  const sentimentCounts = useMemo(() => classifyRow(rows), [rows]);

  return (
    <div className="flex-1 bg-[var(--background)]">
      <AmbientBackground />
      <main className="relative z-10 max-w-[var(--page-max-width)] mx-auto px-[var(--page-padding)] md:px-[var(--page-padding-md)] py-6 animate-fade-in">
        {/* Header */}
        <div className="flex items-end justify-between mb-6 border-b border-[var(--border-subtle)] pb-4">
          <div>
            <h1 className="text-3xl font-bold tracking-tighter text-[var(--foreground)] uppercase">
              台股 ETF 折溢價監控
            </h1>
            <p className="text-xs font-bold text-[var(--text-muted)] tracking-widest mt-1 uppercase">
              FINMIND 預估淨值 · 完全免費 · 收盤資料
            </p>
          </div>
          <ClippedButton
            variant="red-solid"
            size="sm"
            onClick={() => refetch()}
            disabled={isLoading}
          >
            {isLoading ? "重新整理中..." : "重新整理"}
          </ClippedButton>
        </div>

        {/* Backend message (e.g. NAV unavailable) */}
        {data?.message && (
          <GlassPanel className="mb-4 py-3" noPadding>
            <div className="px-4 py-3 text-[12px] text-[var(--text-secondary)] font-medium">
              <span style={{ color: "var(--stock-down, #FFA500)" }}>● </span>
              {data.message}
            </div>
          </GlassPanel>
        )}

        {/* KPI Tiles row */}
        {stats && (
          <div className="grid grid-cols-2 lg:grid-cols-5 gap-3 mb-6">
            <KpiCard
              label="監控 ETF"
              value={String(stats.total_monitored)}
              delta="支"
              direction="flat"
            />
            <KpiCard
              label="溢價"
              value={String(stats.premium_count)}
              delta={stats.max_premium_etf?.percent ?? "—"}
              direction="up"
            />
            <KpiCard
              label="折價"
              value={String(stats.discount_count)}
              delta={stats.max_discount_etf?.percent ?? "—"}
              direction="down"
            />
            <KpiCard
              label="巴菲特指標"
              value={stats.buffett_indicator}
              delta="歷史極值"
              direction="flat"
            />
            <KpiCard
              label="市場情緒"
              value={stats.market_sentiment}
              delta={stats.data_source.split("·").slice(-1)[0]?.trim() ?? "—"}
              direction="flat"
            />
          </div>
        )}

        {/* 情緒雷達 + 市場溫度計 */}
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-4 mb-6">
          <GlassPanel title="情緒雷達">
            <div className="space-y-2">
              {SENTIMENT_ORDER.map((level) => {
                const meta = SENTIMENT_META[level];
                const count = sentimentCounts.get(level) ?? 0;
                const pct =
                  rows.length > 0 ? (count / rows.length) * 100 : 0;
                return (
                  <div key={level} className="flex items-center gap-3">
                    <span className="w-16 text-xs font-bold tabular-nums text-[var(--text-secondary)]">
                      <span aria-hidden>{meta.emoji}</span> {level}
                    </span>
                    <div
                      className="flex-1 h-3 rounded-sm overflow-hidden"
                      style={{ background: "rgba(255,255,255,0.05)" }}
                      role="progressbar"
                      aria-valuenow={Math.round(pct)}
                      aria-valuemin={0}
                      aria-valuemax={100}
                      aria-label={`${level} ${count} 支 (${pct.toFixed(1)}%)`}
                    >
                      <div
                        style={{
                          width: `${pct}%`,
                          height: "100%",
                          background: meta.color,
                          transition: "width 200ms ease-out",
                        }}
                      />
                    </div>
                    <span className="w-20 text-right text-xs font-bold tabular-nums text-[var(--text-muted)]">
                      {count} 支 ({pct.toFixed(1)}%)
                    </span>
                  </div>
                );
              })}
            </div>
          </GlassPanel>

          <GlassPanel title="市場溫度計">
            <div className="flex items-center justify-around py-4">
              <div className="text-center">
                <div className="text-[11px] uppercase tracking-widest text-[var(--text-muted)] font-bold">
                  最大溢價
                </div>
                <div
                  className="text-2xl font-bold tabular-nums mt-1"
                  style={{ color: "var(--stock-up, #FF4D4F)" }}
                >
                  {stats?.max_premium_etf?.percent ?? "—"}
                </div>
                <div className="text-xs text-[var(--text-muted)] mt-1">
                  {stats?.max_premium_etf?.symbol ?? "—"} · {stats?.premium_count ?? 0} 支
                </div>
              </div>
              <div className="text-center">
                <div className="text-[11px] uppercase tracking-widest text-[var(--text-muted)] font-bold">
                  市場情緒
                </div>
                <div className="text-2xl font-bold mt-1 text-[var(--foreground)]">
                  {stats?.market_sentiment ?? "—"}
                </div>
                <div className="text-xs text-[var(--text-muted)] mt-1">
                  全市場平均
                </div>
              </div>
              <div className="text-center">
                <div className="text-[11px] uppercase tracking-widest text-[var(--text-muted)] font-bold">
                  最大折價
                </div>
                <div
                  className="text-2xl font-bold tabular-nums mt-1"
                  style={{ color: "var(--accent-cyan, #00E5FF)" }}
                >
                  {stats?.max_discount_etf?.percent ?? "—"}
                </div>
                <div className="text-xs text-[var(--text-muted)] mt-1">
                  {stats?.max_discount_etf?.symbol ?? "—"} · {stats?.discount_count ?? 0} 支
                </div>
              </div>
            </div>
          </GlassPanel>
        </div>

        {/* 3 排行榜 */}
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-4 mb-6">
          <RankingPanel title="🔴 溢價排行" rows={topPremium} valueKind="premium" />
          <RankingPanel title="🔵 折價排行" rows={topDiscount} valueKind="premium" />
          <RankingPanel title="💹 成交量排行" rows={topVolume} valueKind="volume" />
        </div>

        {/* Filters */}
        <GlassPanel className="mb-4" noPadding>
          <div className="p-4 flex flex-col gap-3">
            <div className="flex items-center gap-2 flex-wrap">
              <input
                type="search"
                placeholder="搜尋代號或名稱"
                value={search}
                onChange={(e) => setSearch(e.target.value)}
                className="px-3 py-1.5 text-sm bg-[var(--bg-secondary)] border border-[var(--border-subtle)] text-[var(--foreground)] placeholder:text-[var(--text-muted)] focus:outline-none focus:border-[var(--accent-cyan)]"
                style={{ minWidth: 200 }}
                aria-label="搜尋 ETF"
              />
              <div className="flex items-center gap-1 ml-auto">
                <label className="text-[11px] uppercase tracking-widest text-[var(--text-muted)] font-bold">
                  排序
                </label>
                <select
                  value={sortKey}
                  onChange={(e) => setSortKey(e.target.value as SortKey)}
                  className="px-3 py-1.5 text-sm bg-[var(--bg-secondary)] border border-[var(--border-subtle)] text-[var(--foreground)] focus:outline-none focus:border-[var(--accent-cyan)]"
                  aria-label="排序方式"
                >
                  {SORT_OPTIONS.map((opt) => (
                    <option key={opt.value} value={opt.value}>
                      {opt.label}
                    </option>
                  ))}
                </select>
              </div>
            </div>

            {/* Direction chips */}
            <div className="flex flex-wrap gap-1.5" role="group" aria-label="方向過濾">
              {DIRECTION_FILTERS.map((opt) => (
                <Chip
                  key={opt.value}
                  active={direction === opt.value}
                  onClick={() => setDirection(opt.value)}
                >
                  {opt.label}
                </Chip>
              ))}
              <span className="mx-2 text-[var(--border-subtle)]">|</span>
              {TYPE_FILTERS.map((opt) => (
                <Chip
                  key={opt.value}
                  active={typeFilter === opt.value}
                  onClick={() => setTypeFilter(opt.value)}
                >
                  {opt.label}
                </Chip>
              ))}
            </div>
          </div>
        </GlassPanel>

        {/* Main table */}
        {isLoading ? (
          <div className="py-20 flex justify-center">
            <LoadingSpinner />
          </div>
        ) : error ? (
          <GlassPanel className="py-20 text-center">
            <p className="text-red-400 font-bold mb-4">
              ERROR: {getErrorMessage(error).toUpperCase()}
            </p>
            <ClippedButton variant="red-ghost" size="sm" onClick={() => refetch()}>
              重試
            </ClippedButton>
          </GlassPanel>
        ) : filteredSorted.length === 0 ? (
          <GlassPanel className="py-20 text-center">
            <p className="text-[var(--text-muted)] font-bold uppercase tracking-widest text-xs">
              {data?.message ? "目前無折溢價資料" : "查無符合條件的 ETF"}
            </p>
          </GlassPanel>
        ) : (
          <ETFTable rows={filteredSorted} />
        )}
      </main>
    </div>
  );
}

// ──────────────────────────────────────────────────────────────────
// Sub-components
// ──────────────────────────────────────────────────────────────────

function Chip({
  active,
  onClick,
  children,
}: {
  active: boolean;
  onClick: () => void;
  children: React.ReactNode;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      aria-pressed={active}
      className={`px-3 py-1 text-[11px] font-bold uppercase tracking-wider rounded border transition-colors ${
        active
          ? "border-[var(--accent-cyan)] text-[var(--accent-cyan)] bg-[color-mix(in_srgb,var(--accent-cyan)_10%,transparent)]"
          : "border-[var(--border-subtle)] text-[var(--text-muted)] hover:text-[var(--foreground)] hover:border-[var(--text-secondary)]"
      }`}
    >
      {children}
    </button>
  );
}

function RankingPanel({
  title,
  rows,
  valueKind,
}: {
  title: string;
  rows: ETFArbitrageRow[];
  valueKind: "premium" | "volume";
}) {
  return (
    <GlassPanel title={title}>
      {rows.length === 0 ? (
        <p className="text-xs text-[var(--text-muted)] py-2">—</p>
      ) : (
        <ul className="space-y-2">
          {rows.map((r, i) => (
            <li
              key={r.symbol}
              className="flex items-center justify-between gap-2 text-sm"
            >
              <span className="flex items-center gap-2 min-w-0">
                <span className="w-4 text-[var(--text-muted)] tabular-nums text-xs">
                  {i + 1}
                </span>
                <span className="font-bold tabular-nums">{r.symbol}</span>
                <span className="text-[var(--text-secondary)] truncate">
                  {r.name}
                </span>
              </span>
              <span
                className="font-bold tabular-nums shrink-0"
                style={{
                  color:
                    valueKind === "premium"
                      ? signedColor(r.premium_percent)
                      : "var(--foreground)",
                }}
              >
                {valueKind === "premium"
                  ? `${r.premium_percent}%`
                  : r.volume_lots.toLocaleString()}
              </span>
            </li>
          ))}
        </ul>
      )}
    </GlassPanel>
  );
}

function ETFTable({ rows }: { rows: ETFArbitrageRow[] }) {
  return (
    <GlassPanel noPadding>
      <div className="overflow-x-auto">
        <table
          className="w-full text-sm tabular-nums"
          aria-label="ETF 折溢價列表"
        >
          <thead>
            <tr className="border-b border-[var(--border-subtle)] text-[10px] uppercase tracking-widest text-[var(--text-muted)]">
              <th className="text-left px-3 py-2 font-bold">代號</th>
              <th className="text-left px-3 py-2 font-bold">名稱</th>
              <th className="text-left px-3 py-2 font-bold">類型</th>
              <th className="text-right px-3 py-2 font-bold">預估淨值</th>
              <th className="text-right px-3 py-2 font-bold">市價</th>
              <th className="text-right px-3 py-2 font-bold">漲跌</th>
              <th className="text-right px-3 py-2 font-bold">折溢價%</th>
              <th className="text-center px-3 py-2 font-bold">情緒</th>
              <th className="text-center px-3 py-2 font-bold">趨勢</th>
              <th className="text-right px-3 py-2 font-bold">成交量</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((r) => {
              const sentiment = SENTIMENT_META[r.sentiment_level];
              return (
                <tr
                  key={r.symbol}
                  className="border-b border-[var(--border-subtle)] last:border-b-0 hover:bg-[color-mix(in_srgb,var(--accent-cyan)_5%,transparent)] transition-colors"
                >
                  <td className="px-3 py-2 font-bold text-[var(--foreground)]">
                    <a
                      href={`/stocks/${encodeURIComponent(r.symbol)}`}
                      className="hover:text-[var(--accent-cyan)]"
                    >
                      {r.symbol}
                    </a>
                  </td>
                  <td className="px-3 py-2 text-[var(--text-secondary)] max-w-[200px] truncate">
                    {r.name}
                  </td>
                  <td className="px-3 py-2 text-[11px] text-[var(--text-muted)]">
                    {r.type}
                  </td>
                  <td className="px-3 py-2 text-right">{r.estimated_nav}</td>
                  <td className="px-3 py-2 text-right font-bold">
                    {r.market_price}
                  </td>
                  <td
                    className="px-3 py-2 text-right"
                    style={{ color: signedColor(r.change) }}
                  >
                    {r.change} ({r.change_percent}%)
                  </td>
                  <td
                    className="px-3 py-2 text-right font-bold"
                    style={{ color: signedColor(r.premium_percent) }}
                  >
                    {r.premium_percent}%
                  </td>
                  <td className="px-3 py-2 text-center">
                    <span
                      title={sentiment.label}
                      style={{ color: sentiment.color }}
                      aria-label={`情緒: ${sentiment.label}`}
                    >
                      {sentiment.emoji} {sentiment.label}
                    </span>
                  </td>
                  <td className="px-3 py-2 text-center text-[var(--text-muted)]">
                    {r.trend ?? "—"}
                  </td>
                  <td className="px-3 py-2 text-right text-[var(--text-secondary)]">
                    {r.volume_lots.toLocaleString()}
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
