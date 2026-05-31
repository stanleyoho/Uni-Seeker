import {
  SkeletonPageHeader,
  SkeletonTable,
} from "@/components/stratos/skeleton";

export default function JournalAccountsLoading() {
  return (
    <main
      className="flex-1 px-[var(--page-padding)] md:px-[var(--page-padding-md)] py-6 space-y-6 max-w-[var(--page-max-width)] mx-auto"
      aria-busy="true"
      aria-live="polite"
    >
      <SkeletonPageHeader />
      <SkeletonTable rows={6} cols={5} />
    </main>
  );
}
