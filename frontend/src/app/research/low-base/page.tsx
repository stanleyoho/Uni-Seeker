"use client";

/**
 * Low-base research page (/research/low-base).
 *
 * Renders the low-base ranking GROUPED BY sector/industry, not as one
 * flat list. Stanley's feedback (2026-05-28): "低基期的話應該要分類股"
 * — the user scans one sector at a time, not a 50-row mixed table.
 *
 * Layout:
 *   1. Header (title + refresh).
 *   2. Summary KPI cards (totals + hit rate + avg score).
 *   3. Sticky sector chip bar — `半導體 (12)` / `金融 (8)` / `其他 (3)` /…
 *      Each chip is an anchor that jumps to the section below.
 *   4. Per-sector sections:
 *      - <h2> section header with sector name + count.
 *      - GlassPanel wrapping a stack of QuoteRow components, sorted by
 *        total_score within the section.
 *
 * Backend contract (`/api/v1/low-base/scan`): each row now carries a
 * `sector` field (string | null). NULL → grouped under "其他".
 */

import { useMemo } from "react";
import { useI18n } from "@/i18n/context";
import { useLowBaseRanking } from "@/hooks/use-market-data";
import { GlassPanel, KpiCard, ClippedButton } from "@/components/stratos/primitives";
import { LoadingSpinner } from "@/components/ui/loading";
import { getErrorMessage } from "@/lib/type-guards";
import { AmbientBackground } from "@/components/stratos/ambient";
import { QuoteRow } from "@/components/quote-row/QuoteRow";
import { classifySentiment, type SentimentClassification } from "@/lib/sentiment";
import type { LowBaseScore } from "@/lib/api-client";

const OTHER_SECTOR_LABEL = "其他";

/** Build a stable DOM id for a sector section so the chip bar can scroll-link. */
function sectorAnchor(name: string): string {
  // Encode aggressively — sector names contain Chinese chars, spaces, slashes.
  return `sector-${encodeURIComponent(name)}`;
}

/**
 * Map the 0–100 low-base composite score onto the shared 5-level
 * sentiment band. The legacy scoreColor() ramp (>=80 / >=60 / >=40 /
 * else) used 4 buckets driven by `var(--stock-*)` tokens; we re-bucket
 * to 5 levels so the visual language matches heatmap + scanner.
 *
 * Bucket borders chosen to preserve the legacy "≥80 = strongest signal"
 * read: 80 → heated, 60 → up, 40 → flat, 20 → down, else → deep.
 * Conceptually we feed (score − 50) into classifySentiment so a 0-100
 * scale collapses onto its percent-band semantics.
 */
function scoreSentiment(score: number | string): SentimentClassification {
  const n = Number(score);
  if (!Number.isFinite(n)) return classifySentiment(null);
  // Re-centre the 0-100 score on 50 and scale so ±30 lands at the
  // ±1 "heated/deep" boundary of classifySentiment.
  const recentred = (n - 50) / 30;
  return classifySentiment(recentred);
}

interface SectorBucket {
  name: string;
  rows: LowBaseScore[];
}

/** Group the ranking rows by `sector`, fold NULL into "其他", preserve
 * intra-sector ranking (already sorted by total_score DESC server-side). */
function groupBySector(rows: readonly LowBaseScore[]): SectorBucket[] {
  const buckets = new Map<string, LowBaseScore[]>();
  for (const row of rows) {
    const key = row.sector?.trim() || OTHER_SECTOR_LABEL;
    const existing = buckets.get(key);
    if (existing) {
      existing.push(row);
    } else {
      buckets.set(key, [row]);
    }
  }
  // Sort sectors by descending bucket size, then by highest top-row score.
  // Sector with the most candidates surfaces first — matches "where's the
  // signal?" scanning behaviour. Ties broken by best score in the bucket.
  return Array.from(buckets.entries())
    .map(([name, rs]) => ({ name, rows: rs }))
    .sort((a, b) => {
      if (b.rows.length !== a.rows.length) return b.rows.length - a.rows.length;
      const aTop = a.rows.length > 0 ? Number(a.rows[0].total_score) : 0;
      const bTop = b.rows.length > 0 ? Number(b.rows[0].total_score) : 0;
      return bTop - aTop;
    });
}

export default function LowBasePage() {
  const { t } = useI18n();
  const lb = t.lowBase;

  const { data, isLoading: loading, error: queryError, refetch: load } = useLowBaseRanking(20);
  const error = queryError ? getErrorMessage(queryError) : null;

  // Memoise so re-renders don't repeatedly rebucket — group ordering matters
  // for the chip bar / anchor mapping consistency.
  const sectors = useMemo<SectorBucket[]>(() => {
    if (!data?.results) return [];
    return groupBySector(data.results);
  }, [data]);

  return (
    <div className="flex-1 bg-[var(--background)]">
      <AmbientBackground />
      <main className="relative z-10 max-w-[var(--page-max-width)] mx-auto px-[var(--page-padding)] md:px-[var(--page-padding-md)] py-6 animate-fade-in">

        {/* Header row */}
        <div className="flex items-end justify-between mb-6 border-b border-[var(--border-subtle)] pb-4">
          <div>
            <h1 className="text-3xl font-bold tracking-tighter text-[var(--foreground)] uppercase">
              {lb.title}
            </h1>
            <p className="text-xs font-bold text-[var(--text-muted)] tracking-widest mt-1 uppercase">
              {lb.subtitle}
            </p>
          </div>
          <ClippedButton
            variant="red-solid"
            size="sm"
            onClick={() => load()}
            disabled={loading}
          >
            {loading ? "INITIALIZING SCAN..." : "REFRESH DATA"}
          </ClippedButton>
        </div>

        {/* Summary KPI cards */}
        {data && (
          <div className="grid grid-cols-2 lg:grid-cols-4 gap-4 mb-6">
            <KpiCard
              label="TOTAL SCANNED"
              value={String(data.total_scanned)}
              delta="STOCKS"
              direction="flat"
            />
            <KpiCard
              label="QUALIFIED"
              value={String(data.total_qualified)}
              delta="PASSED FILTERS"
              direction="up"
            />
            <KpiCard
              label="HIT RATE"
              value={data.total_scanned > 0 ? `${((data.total_qualified / data.total_scanned) * 100).toFixed(1)}%` : "-"}
              delta="SUCCESS RATIO"
              direction="flat"
            />
            <KpiCard
              label="AVG SCORE"
              value={data.results.length > 0 ? (data.results.reduce((s, r) => s + Number(r.total_score), 0) / data.results.length).toFixed(1) : "-"}
              delta="TOP RANKINGS"
              direction="up"
            />
          </div>
        )}

        {loading ? (
          <div className="py-20 flex justify-center"><LoadingSpinner /></div>
        ) : error ? (
          <GlassPanel className="py-20 text-center">
            <p className="text-red-400 font-bold mb-4">ERROR: {error.toUpperCase()}</p>
            <ClippedButton variant="red-ghost" size="sm" onClick={() => load()}>RETRY</ClippedButton>
          </GlassPanel>
        ) : sectors.length === 0 ? (
          <GlassPanel className="py-20 text-center">
            <p className="text-[var(--text-muted)] font-bold uppercase tracking-widest text-xs">
              {lb.noData}
            </p>
          </GlassPanel>
        ) : (
          <>
            {/* Sticky sector chip bar — anchor-jump to each section below.
                Sticky offset 0 inside this main; the page itself scrolls. */}
            <nav
              aria-label="Sectors"
              className="sticky top-0 z-20 -mx-2 px-2 py-2 mb-4 backdrop-blur-md bg-[color-mix(in_srgb,var(--background)_70%,transparent)] border-b border-[var(--border-subtle)]"
            >
              <div className="flex flex-wrap gap-2">
                {sectors.map((s) => (
                  <a
                    key={s.name}
                    href={`#${sectorAnchor(s.name)}`}
                    className="inline-flex items-center gap-1.5 px-3 py-1 text-[11px] font-bold uppercase tracking-wider rounded border border-[var(--border-subtle)] text-[var(--text-secondary)] hover:border-[var(--accent-cyan)] hover:text-[var(--accent-cyan)] transition-colors"
                  >
                    <span>{s.name}</span>
                    <span className="tabular-nums text-[var(--text-muted)]">
                      ({s.rows.length})
                    </span>
                  </a>
                ))}
              </div>
            </nav>

            {/* Per-sector sections */}
            <div className="flex flex-col gap-6">
              {sectors.map((s) => (
                <section
                  key={s.name}
                  id={sectorAnchor(s.name)}
                  // scroll-margin-top so the sticky chip bar doesn't cover
                  // the header when anchor-jumping in.
                  className="scroll-mt-20"
                >
                  <div className="flex items-baseline justify-between mb-2 px-1">
                    <h2 className="text-base font-bold tracking-tighter text-[var(--foreground)] uppercase">
                      {s.name}
                    </h2>
                    <span className="text-[10px] font-bold text-[var(--text-muted)] uppercase tracking-widest tabular-nums">
                      {s.rows.length} CANDIDATES
                    </span>
                  </div>
                  <GlassPanel noPadding>
                    <ul className="flex flex-col">
                      {s.rows.map((row, idx) => {
                        const ss = scoreSentiment(row.total_score);
                        return (
                          <li
                            key={row.symbol}
                            className="flex items-center gap-2 border-b border-[var(--border-subtle)] last:border-b-0"
                          >
                            <div className="flex-1 min-w-0">
                              <QuoteRow
                                symbol={row.symbol}
                                name={row.name}
                                // Price / change come from the scan endpoint's
                                // `details` payload only sometimes; the scan
                                // contract focuses on scores, not quotes —
                                // QuoteRow renders em-dash for missing fields.
                                href={`/stocks/${encodeURIComponent(row.symbol)}`}
                                rank={idx + 1}
                              />
                            </div>
                            <div
                              className={`shrink-0 pr-3 text-sm font-bold tabular-nums inline-flex items-center gap-1 ${ss.colorClass}`}
                              aria-label={`${lb.totalScore} ${row.total_score}`}
                            >
                              <span aria-hidden="true">{ss.emoji}</span>
                              <span>{row.total_score}</span>
                            </div>
                          </li>
                        );
                      })}
                    </ul>
                  </GlassPanel>
                </section>
              ))}
            </div>
          </>
        )}
      </main>
    </div>
  );
}
