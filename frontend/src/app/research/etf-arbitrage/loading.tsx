/**
 * /research/etf-arbitrage loading skeleton.
 *
 *   - h1 header + refresh CTA
 *   - 5-tile KPI strip (mirrors the final layout)
 *   - filter chip bar placeholder
 *   - quote stack placeholder
 */
import {
  SkeletonBlock,
  SkeletonKpiRow,
  SkeletonPageHeader,
  SkeletonQuoteList,
} from "@/components/stratos/skeleton";

export default function ETFArbitrageLoading() {
  return (
    <div className="flex-1 bg-[var(--background)]">
      <main
        className="relative z-10 max-w-[var(--page-max-width)] mx-auto px-[var(--page-padding)] md:px-[var(--page-padding-md)] py-6 space-y-6"
        aria-busy="true"
        aria-live="polite"
      >
        <SkeletonPageHeader />
        <SkeletonKpiRow count={5} />
        <div className="flex flex-wrap gap-2 py-2">
          {Array.from({ length: 8 }).map((_, i) => (
            <SkeletonBlock key={i} style={{ height: 26, width: 90 }} />
          ))}
        </div>
        <SkeletonQuoteList rows={8} />
      </main>
    </div>
  );
}
