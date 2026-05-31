import {
  SkeletonBlock,
  SkeletonPageHeader,
  SkeletonPanel,
} from "@/components/stratos/skeleton";

export default function SettingsNotificationsLoading() {
  return (
    <main
      className="relative z-10 max-w-[var(--page-max-width)] mx-auto px-[var(--page-padding)] md:px-[var(--page-padding-md)] py-6 space-y-6"
      aria-busy="true"
      aria-live="polite"
    >
      <SkeletonPageHeader />
      {Array.from({ length: 4 }).map((_, p) => (
        <SkeletonPanel key={p} className="space-y-4">
          <SkeletonBlock style={{ height: 18, width: "35%" }} />
          <div className="space-y-2">
            {Array.from({ length: 3 }).map((_, r) => (
              <div key={r} className="flex justify-between items-center">
                <SkeletonBlock style={{ height: 14, width: "55%" }} />
                <SkeletonBlock style={{ height: 22, width: 40 }} />
              </div>
            ))}
          </div>
        </SkeletonPanel>
      ))}
    </main>
  );
}
