/**
 * /research/scanner is a permanentRedirect → /research. The loading
 * fallback is only shown for the millisecond the server takes to issue
 * the redirect, but Next requires a sibling loading.tsx for Suspense
 * coverage. Render an empty shell with the correct background so
 * there's no flash.
 */
export default function ScannerLoading() {
  return (
    <main
      className="relative flex-1"
      style={{ background: "var(--background)" }}
      aria-busy="true"
      aria-live="polite"
    />
  );
}
