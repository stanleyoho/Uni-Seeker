/**
 * /institutional loading skeleton. Mirrors InstitutionalPage:
 *   - header strip
 *   - top-level CTAs row
 *   - filer list panel
 *   - view-toolbar + holdings table placeholder
 */
import {
  SkeletonBlock,
  SkeletonPageHeader,
  SkeletonPanel,
  SkeletonTable,
} from "@/components/stratos/skeleton";

export default function InstitutionalLoading() {
  return (
    <main
      className="relative flex-1 overflow-y-auto"
      style={{ background: "var(--background)" }}
      aria-busy="true"
      aria-live="polite"
    >
      <div className="relative max-w-[1440px] mx-auto px-3 sm:px-4 lg:px-6 py-4 lg:py-6 space-y-4 lg:space-y-6">
        <SkeletonPageHeader />
        {/* Filer list */}
        <SkeletonPanel noPadding>
          <div className="px-4 py-3 border-b border-[var(--border-subtle)] flex gap-3">
            {Array.from({ length: 4 }).map((_, i) => (
              <SkeletonBlock key={i} style={{ height: 12, flex: 1 }} />
            ))}
          </div>
          {Array.from({ length: 5 }).map((_, r) => (
            <div
              key={r}
              className="px-4 py-3 border-b border-[var(--border-subtle)] last:border-b-0 flex gap-3"
            >
              {Array.from({ length: 4 }).map((_, c) => (
                <SkeletonBlock key={c} style={{ height: 16, flex: 1 }} />
              ))}
            </div>
          ))}
        </SkeletonPanel>
        {/* View tabs */}
        <div className="flex flex-wrap gap-2">
          {Array.from({ length: 4 }).map((_, i) => (
            <SkeletonBlock key={i} style={{ height: 30, width: 100 }} />
          ))}
        </div>
        {/* Holdings table */}
        <SkeletonTable rows={8} cols={6} />
      </div>
    </main>
  );
}
