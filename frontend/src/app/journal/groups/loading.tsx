import {
  SkeletonPageHeader,
  SkeletonTable,
} from "@/components/stratos/skeleton";

export default function JournalGroupsLoading() {
  return (
    <main
      className="flex-1 px-[var(--page-padding)] md:px-[var(--page-padding-md)] py-6 space-y-6 max-w-[var(--page-max-width)] mx-auto"
      aria-busy="true"
      aria-live="polite"
    >
      <SkeletonPageHeader />
      <SkeletonTable rows={5} cols={4} />
    </main>
  );
}
