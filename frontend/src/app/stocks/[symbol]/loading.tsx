/**
 * /stocks/[symbol] loading skeleton — mirrors the stock-detail page:
 *   - symbol header + price + quick stats
 *   - chart placeholder
 *   - tab strip
 *   - indicator / valuation card grid
 */
import {
  SkeletonBlock,
  SkeletonChart,
  SkeletonKpiRow,
  SkeletonPanel,
} from "@/components/stratos/skeleton";

export default function StockDetailLoading() {
  return (
    <main
      className="relative z-10 max-w-[var(--page-max-width)] mx-auto px-[var(--page-padding)] md:px-[var(--page-padding-md)] py-6 space-y-6"
      aria-busy="true"
      aria-live="polite"
    >
      {/* Symbol header */}
      <div className="flex items-end justify-between border-b border-[var(--border-subtle)] pb-4">
        <div className="space-y-2">
          <SkeletonBlock style={{ height: 36, width: 180 }} />
          <SkeletonBlock style={{ height: 14, width: 260 }} />
        </div>
        <div className="text-right space-y-2">
          <SkeletonBlock style={{ height: 30, width: 140 }} />
          <SkeletonBlock style={{ height: 16, width: 100 }} />
        </div>
      </div>
      <SkeletonKpiRow count={4} />
      <SkeletonChart height={360} />
      {/* Tab strip */}
      <div className="flex gap-2">
        {Array.from({ length: 4 }).map((_, i) => (
          <SkeletonBlock key={i} style={{ height: 30, width: 100 }} />
        ))}
      </div>
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        {Array.from({ length: 4 }).map((_, i) => (
          <SkeletonPanel key={i} className="space-y-3">
            <SkeletonBlock style={{ height: 14, width: "40%" }} />
            <SkeletonBlock style={{ height: 80, width: "100%" }} />
            <SkeletonBlock style={{ height: 12, width: "60%" }} />
          </SkeletonPanel>
        ))}
      </div>
    </main>
  );
}
