/**
 * Root-level loading fallback. Used by Next 16 when any unhandled
 * Suspense boundary (or a page without a sibling loading.tsx) is
 * resolving. Matches the home dashboard's 5-tile KPI row + sector grid
 * shape so first-paint locks in the layout.
 */
import { SkeletonKpiRow, SkeletonTileGrid } from "@/components/stratos/skeleton";

export default function RootLoading() {
  return (
    <main
      className="relative z-10 max-w-[var(--page-max-width)] mx-auto px-[var(--page-padding)] md:px-[var(--page-padding-md)] py-6"
      aria-busy="true"
      aria-live="polite"
    >
      <div className="mb-6">
        <SkeletonKpiRow count={5} />
      </div>
      <SkeletonTileGrid tiles={8} />
    </main>
  );
}
