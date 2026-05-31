import {
  SkeletonBlock,
  SkeletonKpiRow,
  SkeletonTable,
} from "@/components/stratos/skeleton";

export default function FinancialsLoading() {
  return (
    <main
      className="relative z-10 max-w-[var(--page-max-width)] mx-auto px-[var(--page-padding)] md:px-[var(--page-padding-md)] py-6 space-y-6"
      aria-busy="true"
      aria-live="polite"
    >
      <div className="space-y-2">
        <SkeletonBlock style={{ height: 32, width: 240 }} />
        <SkeletonBlock style={{ height: 14, width: 180 }} />
      </div>
      {/* Tab strip */}
      <div className="flex gap-2">
        {Array.from({ length: 4 }).map((_, i) => (
          <SkeletonBlock key={i} style={{ height: 30, width: 110 }} />
        ))}
      </div>
      <SkeletonKpiRow count={4} />
      <SkeletonTable rows={10} cols={6} />
    </main>
  );
}
