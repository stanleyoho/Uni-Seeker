import {
  SkeletonBlock,
  SkeletonPageHeader,
  SkeletonPanel,
  SkeletonTable,
} from "@/components/stratos/skeleton";

export default function SettingsAlertsLoading() {
  return (
    <main
      className="relative z-10 max-w-[var(--page-max-width)] mx-auto px-[var(--page-padding)] md:px-[var(--page-padding-md)] py-6 space-y-6"
      aria-busy="true"
      aria-live="polite"
    >
      <SkeletonPageHeader />
      <SkeletonPanel className="space-y-3">
        <SkeletonBlock style={{ height: 16, width: "30%" }} />
        <SkeletonBlock style={{ height: 36, width: "100%" }} />
        <SkeletonBlock style={{ height: 36, width: "100%" }} />
      </SkeletonPanel>
      <SkeletonTable rows={6} cols={5} />
    </main>
  );
}
