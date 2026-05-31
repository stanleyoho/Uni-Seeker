import {
  SkeletonBlock,
  SkeletonKpiRow,
  SkeletonPageHeader,
  SkeletonTable,
} from "@/components/stratos/skeleton";

export default function HoldingsLoading() {
  return (
    <div className="flex-1 bg-[var(--background)]">
      <main
        className="relative z-10 max-w-[var(--page-max-width)] mx-auto px-[var(--page-padding)] md:px-[var(--page-padding-md)] py-6 space-y-6"
        aria-busy="true"
        aria-live="polite"
      >
        <SkeletonPageHeader />
        {/* Account switcher + currency toggle row */}
        <div className="flex flex-wrap gap-2">
          <SkeletonBlock style={{ height: 32, width: 160 }} />
          <SkeletonBlock style={{ height: 32, width: 80 }} />
          <SkeletonBlock style={{ height: 32, width: 100 }} />
        </div>
        <SkeletonKpiRow count={4} />
        <SkeletonTable rows={10} cols={6} />
      </main>
    </div>
  );
}
