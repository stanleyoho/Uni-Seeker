import {
  SkeletonKpiRow,
  SkeletonPageHeader,
  SkeletonTable,
} from "@/components/stratos/skeleton";

export default function JournalGroupDetailLoading() {
  return (
    <main
      className="flex-1 px-[var(--page-padding)] md:px-[var(--page-padding-md)] py-6 space-y-6 max-w-[var(--page-max-width)] mx-auto"
      aria-busy="true"
      aria-live="polite"
    >
      <SkeletonPageHeader />
      <SkeletonKpiRow count={3} />
      <SkeletonTable rows={6} cols={5} />
    </main>
  );
}
