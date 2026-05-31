import { SkeletonBlock, SkeletonPanel } from "@/components/stratos/skeleton";

export default function CompareLoading() {
  return (
    <div className="flex-1 bg-[var(--background)]">
      <main
        className="relative z-10 max-w-[var(--page-max-width)] mx-auto px-[var(--page-padding)] md:px-[var(--page-padding-md)] py-6 space-y-6"
        aria-busy="true"
        aria-live="polite"
      >
        {/* Search row */}
        <div className="flex flex-col md:flex-row gap-4 items-start">
          <SkeletonBlock style={{ height: 44, width: "100%", maxWidth: 420 }} />
          <div className="flex gap-2">
            {Array.from({ length: 3 }).map((_, i) => (
              <SkeletonBlock key={i} style={{ height: 28, width: 80 }} />
            ))}
          </div>
        </div>
        {/* Comparison columns */}
        <div className="flex gap-6 overflow-x-auto pb-6">
          {Array.from({ length: 3 }).map((_, i) => (
            <SkeletonPanel key={i} className="flex-1 min-w-[280px] space-y-4">
              <div className="space-y-2">
                <SkeletonBlock style={{ height: 22, width: 100 }} />
                <SkeletonBlock style={{ height: 30, width: 140 }} />
              </div>
              <SkeletonBlock style={{ height: 120, width: "100%" }} />
              <div className="space-y-2">
                {Array.from({ length: 4 }).map((_, r) => (
                  <SkeletonBlock key={r} style={{ height: 24, width: "100%" }} />
                ))}
              </div>
            </SkeletonPanel>
          ))}
        </div>
      </main>
    </div>
  );
}
