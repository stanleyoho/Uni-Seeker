import {
  SkeletonKpiRow,
  SkeletonPageHeader,
  SkeletonTable,
} from "@/components/stratos/skeleton";

export default function DailyFlowsLoading() {
  return (
    <main
      className="relative flex-1 overflow-y-auto px-3 sm:px-4 lg:px-6 py-4 lg:py-6 space-y-6 max-w-[1440px] mx-auto"
      aria-busy="true"
      aria-live="polite"
    >
      <SkeletonPageHeader />
      <SkeletonKpiRow count={3} />
      <SkeletonTable rows={12} cols={6} />
    </main>
  );
}
