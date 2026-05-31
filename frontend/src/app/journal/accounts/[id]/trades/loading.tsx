import {
  SkeletonPageHeader,
  SkeletonTable,
} from "@/components/stratos/skeleton";

export default function JournalTradesLoading() {
  return (
    <main
      className="flex-1 px-[var(--page-padding)] md:px-[var(--page-padding-md)] py-6 space-y-6 max-w-[var(--page-max-width)] mx-auto"
      aria-busy="true"
      aria-live="polite"
    >
      <SkeletonPageHeader />
      <SkeletonTable rows={12} cols={7} />
    </main>
  );
}
