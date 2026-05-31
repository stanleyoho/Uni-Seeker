import {
  SkeletonBlock,
  SkeletonPageHeader,
  SkeletonTable,
} from "@/components/stratos/skeleton";

export default function SettingsAuditLoading() {
  return (
    <main
      className="relative z-10 max-w-[var(--page-max-width)] mx-auto px-[var(--page-padding)] md:px-[var(--page-padding-md)] py-6 space-y-6"
      aria-busy="true"
      aria-live="polite"
    >
      <SkeletonPageHeader />
      <div className="flex gap-2">
        {Array.from({ length: 4 }).map((_, i) => (
          <SkeletonBlock key={i} style={{ height: 30, width: 110 }} />
        ))}
      </div>
      <SkeletonTable rows={12} cols={6} />
    </main>
  );
}
