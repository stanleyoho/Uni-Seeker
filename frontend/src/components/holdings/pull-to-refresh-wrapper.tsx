"use client";

/**
 * Pull-to-Refresh Wrapper — Phase 8 R.2 mobile gesture.
 *
 * Wraps page content in `react-simple-pull-to-refresh` ONLY on mobile
 * (< 768 px, matching Phase 7's Tailwind `md` breakpoint convention).
 * On desktop the wrapper is a transparent pass-through — no extra DOM,
 * no event listeners, no behaviour change.
 *
 * Why this gating matters:
 *   - The lib attaches mousedown/mousemove handlers to support desktop
 *     "drag" pulls — that interferes with normal page interactions on a
 *     mouse-first UI. We bypass the component entirely on ≥ 768 px.
 *   - SSR returns the desktop pass-through so the server markup matches
 *     the initial hydration pass; `useEffect` then upgrades to the
 *     gesture wrapper if the viewport is mobile. This keeps the
 *     "first paint = no PullToRefresh" invariant on every device.
 *
 * `onRefresh` runs the page's `refetch()` calls in parallel and resolves
 * when all queries settle. The lib displays its loader until the promise
 * resolves; we provide STRATOS-styled pulling / refreshing content.
 */

import { useEffect, useState, type ReactElement } from "react";
import PullToRefresh from "react-simple-pull-to-refresh";

interface PullToRefreshWrapperProps {
  onRefresh: () => Promise<unknown>;
  children: ReactElement;
}

const MOBILE_QUERY = "(max-width: 767px)";

function PullingHint() {
  return (
    <div
      style={{
        padding: "8px 12px",
        fontSize: 12,
        color: "var(--text-muted)",
        textAlign: "center",
        letterSpacing: "0.04em",
        textTransform: "uppercase",
      }}
    >
      ↓ 下拉重新整理
    </div>
  );
}

function RefreshingSpinner() {
  return (
    <div
      role="status"
      aria-live="polite"
      aria-label="refreshing"
      style={{
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        gap: 8,
        padding: "10px 12px",
        fontSize: 12,
        color: "var(--accent-cyan)",
        letterSpacing: "0.04em",
        textTransform: "uppercase",
      }}
    >
      <span
        aria-hidden="true"
        style={{
          width: 14,
          height: 14,
          border: "2px solid var(--accent-cyan)",
          borderTopColor: "transparent",
          borderRadius: "50%",
          animation: "ptr-spin 0.8s linear infinite",
          display: "inline-block",
        }}
      />
      <span>更新中…</span>
      <style>{`@keyframes ptr-spin { to { transform: rotate(360deg); } }`}</style>
    </div>
  );
}

export function PullToRefreshWrapper({
  onRefresh,
  children,
}: PullToRefreshWrapperProps) {
  // SSR + initial hydration: assume desktop (no PullToRefresh). The
  // effect below upgrades to mobile after mount so the server-rendered
  // markup never differs from the first client render.
  const [isMobile, setIsMobile] = useState(false);

  useEffect(() => {
    if (typeof window === "undefined") return;
    const mq = window.matchMedia(MOBILE_QUERY);
    const update = () => setIsMobile(mq.matches);
    update();
    mq.addEventListener("change", update);
    return () => {
      mq.removeEventListener("change", update);
    };
  }, []);

  if (!isMobile) {
    return children;
  }

  return (
    <PullToRefresh
      onRefresh={async () => {
        await onRefresh();
      }}
      pullingContent={<PullingHint />}
      refreshingContent={<RefreshingSpinner />}
    >
      {children}
    </PullToRefresh>
  );
}
