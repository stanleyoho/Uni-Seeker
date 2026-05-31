import { SkeletonBlock, SkeletonPanel } from "@/components/stratos/skeleton";

export default function LoginLoading() {
  return (
    <main
      className="relative z-10 max-w-md mx-auto px-6 py-12"
      aria-busy="true"
      aria-live="polite"
    >
      <SkeletonPanel className="space-y-5" style={{ padding: 32 }}>
        <SkeletonBlock style={{ height: 28, width: "60%" }} />
        <SkeletonBlock style={{ height: 12, width: "80%" }} />
        <SkeletonBlock style={{ height: 40, width: "100%" }} />
        <SkeletonBlock style={{ height: 40, width: "100%" }} />
        <SkeletonBlock style={{ height: 40, width: "100%" }} />
      </SkeletonPanel>
    </main>
  );
}
