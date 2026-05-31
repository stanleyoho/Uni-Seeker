import {
  SkeletonChart,
  SkeletonKpiRow,
  SkeletonPageHeader,
} from "@/components/stratos/skeleton";

export default function JournalLoading() {
  return (
    <main
      className="flex-1 px-[var(--page-padding)] md:px-[var(--page-padding-md)] py-6 space-y-6 max-w-[var(--page-max-width)] mx-auto"
      aria-busy="true"
      aria-live="polite"
    >
      <SkeletonPageHeader />
      <SkeletonKpiRow count={4} />
      <SkeletonChart height={320} />
    </main>
  );
}
