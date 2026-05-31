import {
  SkeletonKpiRow,
  SkeletonPageHeader,
  SkeletonTable,
} from "@/components/stratos/skeleton";

export default function AlertsLoading() {
  return (
    <div className="flex-1 bg-[var(--background)]">
      <main
        className="relative z-10 max-w-[var(--page-max-width)] mx-auto px-[var(--page-padding)] md:px-[var(--page-padding-md)] py-6 space-y-6"
        aria-busy="true"
        aria-live="polite"
      >
        <SkeletonPageHeader />
        <SkeletonKpiRow count={4} />
        <SkeletonTable rows={8} cols={5} />
      </main>
    </div>
  );
}
