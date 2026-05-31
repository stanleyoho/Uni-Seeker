/**
 * /research loading skeleton. The unified Scan workflow renders a
 * template selector strip + condition cards grid + run button +
 * results panel. We reserve those four blocks so the layout doesn't
 * jump when the bundle hydrates.
 */
import {
  SkeletonBlock,
  SkeletonPageHeader,
  SkeletonPanel,
  SkeletonTable,
} from "@/components/stratos/skeleton";

export default function ResearchLoading() {
  return (
    <main
      className="relative z-10 max-w-[var(--page-max-width)] mx-auto px-[var(--page-padding)] md:px-[var(--page-padding-md)] py-6 space-y-6"
      aria-busy="true"
      aria-live="polite"
    >
      <SkeletonPageHeader />
      {/* Template selector strip */}
      <div className="flex flex-wrap gap-2">
        {Array.from({ length: 6 }).map((_, i) => (
          <SkeletonBlock key={i} style={{ height: 32, width: 120 }} />
        ))}
      </div>
      {/* Indicator condition cards grid */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
        {Array.from({ length: 6 }).map((_, i) => (
          <SkeletonPanel key={i} className="space-y-3">
            <SkeletonBlock style={{ height: 14, width: "55%" }} />
            <SkeletonBlock style={{ height: 28, width: "100%" }} />
            <SkeletonBlock style={{ height: 12, width: "70%" }} />
          </SkeletonPanel>
        ))}
      </div>
      <SkeletonTable rows={6} cols={5} />
    </main>
  );
}
