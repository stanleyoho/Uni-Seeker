/**
 * /research/low-base loading skeleton.
 *   - h1 header + refresh CTA
 *   - 4-tile KPI strip
 *   - sticky chip nav placeholder
 *   - per-sector quote stack
 */
import {
  SkeletonBlock,
  SkeletonKpiRow,
  SkeletonPageHeader,
  SkeletonQuoteList,
} from "@/components/stratos/skeleton";

export default function LowBaseLoading() {
  return (
    <div className="flex-1 bg-[var(--background)]">
      <main
        className="relative z-10 max-w-[var(--page-max-width)] mx-auto px-[var(--page-padding)] md:px-[var(--page-padding-md)] py-6 space-y-6"
        aria-busy="true"
        aria-live="polite"
      >
        <SkeletonPageHeader />
        <SkeletonKpiRow count={4} />
        {/* Chip bar placeholder */}
        <div className="flex flex-wrap gap-2 py-2">
          {Array.from({ length: 8 }).map((_, i) => (
            <SkeletonBlock key={i} style={{ height: 26, width: 90 }} />
          ))}
        </div>
        {/* 3 sector sections */}
        {Array.from({ length: 3 }).map((_, s) => (
          <div key={s} className="space-y-2">
            <div className="flex items-baseline justify-between px-1">
              <SkeletonBlock style={{ height: 18, width: 140 }} />
              <SkeletonBlock style={{ height: 10, width: 90 }} />
            </div>
            <div
              style={{
                background: "var(--bg-secondary, rgba(255,255,255,0.04))",
                border: "1px solid var(--border-subtle, rgba(255,255,255,0.06))",
              }}
            >
              <SkeletonQuoteList rows={5} />
            </div>
          </div>
        ))}
      </main>
    </div>
  );
}
