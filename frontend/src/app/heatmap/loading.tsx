/**
 * /heatmap loading skeleton. Mirrors HeatmapPage shape:
 *   - h1 header strip + market-filter pill bar
 *   - 4-col responsive grid of sector tiles (each ≈ SectorBlock)
 */
import {
  SkeletonBlock,
  SkeletonPageHeader,
  SkeletonTileGrid,
} from "@/components/stratos/skeleton";

export default function HeatmapLoading() {
  return (
    <div className="flex-1 bg-[var(--background)]">
      <main
        className="relative z-10 max-w-[var(--page-max-width)] mx-auto px-[var(--page-padding)] md:px-[var(--page-padding-md)] py-6"
        aria-busy="true"
        aria-live="polite"
      >
        <SkeletonPageHeader withCta={false} />
        <div className="mb-6 flex gap-1">
          {Array.from({ length: 3 }).map((_, i) => (
            <SkeletonBlock key={i} style={{ height: 28, width: 140 }} />
          ))}
        </div>
        <SkeletonTileGrid tiles={12} />
      </main>
    </div>
  );
}
