"use client";

/*
 * Shared per-segment Error UI. Re-used by every app/.../error.tsx file
 * so we don't sprinkle near-identical error markup across the app.
 *
 * Honors the Next 16 error.tsx contract:
 *   - Must be a Client Component (the "use client" directive above).
 *   - Receives `error` + `unstable_retry`. We expose `reset` as an
 *     alias for back-compat with anything that wants the old name.
 *   - Logs via console.error so the dev terminal + Sentry-style hooks
 *     can pick it up.
 *
 * STRATOS-styled: red-ghost panel + cyan retry CTA.
 */

import { useEffect } from "react";

interface SegmentErrorProps {
  /** Page-specific scope label, e.g. "HEATMAP" / "WATCHLIST". */
  scope?: string;
  error: Error & { digest?: string };
  reset?: () => void;
  /** Next 16 native retry handler. Preferred over reset() per docs. */
  unstable_retry?: () => void;
}

export function SegmentError({
  scope = "PAGE",
  error,
  reset,
  unstable_retry,
}: SegmentErrorProps) {
  useEffect(() => {
    // Surface to dev console / external error reporters. `digest` is
    // the server-only hash Next forwards so we can correlate to server
    // logs without leaking the raw message in prod.
    console.error(`[segment-error:${scope}]`, error.message, {
      digest: error.digest,
    });
  }, [scope, error]);

  const retry = unstable_retry ?? reset ?? (() => {
    // Final fallback — hard reload. Should rarely fire because Next 16
    // always passes unstable_retry.
    if (typeof window !== "undefined") window.location.reload();
  });

  return (
    <main
      className="relative flex-1 flex items-center justify-center px-6 py-12"
      style={{ background: "var(--background)" }}
    >
      <div
        className="max-w-md w-full p-8 space-y-5"
        style={{
          background: "var(--glass-bg)",
          backdropFilter: "var(--glass-blur)",
          WebkitBackdropFilter: "var(--glass-blur)",
          border: "1px solid var(--accent-primary)",
          backgroundImage: "var(--glass-gradient)",
          boxShadow: "var(--glass-shadow)",
        }}
        role="alert"
        aria-live="polite"
      >
        <div className="space-y-2">
          <div
            className="text-[10px] font-bold tracking-[0.2em] uppercase"
            style={{ color: "var(--accent-primary)" }}
          >
            {scope} · SYSTEM FAULT
          </div>
          <h2
            className="text-xl font-bold tracking-tighter uppercase"
            style={{ color: "var(--foreground)" }}
          >
            Something went wrong
          </h2>
          <p
            className="text-xs leading-relaxed"
            style={{ color: "var(--text-muted)" }}
          >
            {/* In prod, error.message is replaced by a generic string for
             * Server Component errors. Show the digest so support can
             * cross-reference server logs. */}
            {error.message || "An unexpected error occurred."}
            {error.digest && (
              <span
                className="block mt-2 font-mono tabular-nums opacity-60"
                style={{ fontSize: 10 }}
              >
                ref: {error.digest}
              </span>
            )}
          </p>
        </div>

        <button
          type="button"
          onClick={retry}
          className="w-full px-5 py-2 text-sm font-semibold transition-all duration-200 active:scale-95 hover:brightness-110"
          style={{
            background: "var(--accent-primary)",
            color: "#fff",
            border: "none",
            clipPath:
              "polygon(0 0, calc(100% - 12px) 0, 100% 12px, 100% 100%, 12px 100%, 0 calc(100% - 12px))",
            cursor: "pointer",
            outline: "none",
          }}
        >
          RETRY
        </button>
      </div>
    </main>
  );
}
