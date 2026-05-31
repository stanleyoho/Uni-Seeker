/**
 * Legacy /scanner → /research permanent redirect. Empty shell so the
 * brief redirect window doesn't flash white.
 */
export default function LegacyScannerLoading() {
  return (
    <main
      className="relative flex-1"
      style={{ background: "var(--background)" }}
      aria-busy="true"
      aria-live="polite"
    />
  );
}
