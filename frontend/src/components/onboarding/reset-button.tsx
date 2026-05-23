"use client";

/**
 * OnboardingResetHook — invisible dev-only keyboard chord listener.
 *
 * Chord: Ctrl+Shift+R (Cmd+Shift+R on macOS — but that's the browser's
 * "hard reload" shortcut, so we ONLY listen for Ctrl+Shift+R to avoid
 * stomping on muscle memory).
 *
 * On chord:
 *   1. Clear both onboarding localStorage flags via
 *      `restartOnboarding()` from OnboardingContext.
 *   2. Surface a brief toast-like banner so the dev knows the chord
 *      registered (otherwise it's invisible and easy to second-guess).
 *
 * Renders nothing visible by default. The banner is a transient
 * fixed-position div that auto-dismisses after 2s.
 *
 * Why a component (vs. a useEffect inside OnboardingProvider)?
 *   - Keeps the provider lean.
 *   - Easy to gate by NODE_ENV if we want to ship a prod build without
 *     the chord listener. (Currently always-on — devs/QA can use it on
 *     any environment, and accidental hits are non-destructive — they
 *     just replay the welcome modal.)
 */

import { useCallback, useEffect, useState } from "react";
import { useOnboarding } from "@/contexts/onboarding-context";

const BANNER_MS = 2000;

export function OnboardingResetHook() {
  const { restartOnboarding } = useOnboarding();
  const [bannerVisible, setBannerVisible] = useState(false);

  const trigger = useCallback(() => {
    restartOnboarding();
    setBannerVisible(true);
    const t = window.setTimeout(() => setBannerVisible(false), BANNER_MS);
    return () => window.clearTimeout(t);
  }, [restartOnboarding]);

  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      // Ctrl+Shift+R (case-insensitive). Avoid metaKey so macOS Cmd
      // shortcut still hard-reloads as the browser intends.
      if (
        e.ctrlKey &&
        e.shiftKey &&
        !e.metaKey &&
        !e.altKey &&
        (e.key === "R" || e.key === "r")
      ) {
        e.preventDefault();
        trigger();
      }
    };
    window.addEventListener("keydown", handler);
    return () => window.removeEventListener("keydown", handler);
  }, [trigger]);

  if (!bannerVisible) return null;
  return (
    <div
      role="status"
      aria-live="polite"
      style={{
        position: "fixed",
        bottom: 16,
        right: 16,
        padding: "8px 14px",
        background: "var(--glass-bg)",
        backdropFilter: "var(--glass-blur)",
        WebkitBackdropFilter: "var(--glass-blur)",
        border: "1px solid var(--accent-cyan)",
        color: "var(--accent-cyan)",
        fontSize: 12,
        fontWeight: 600,
        zIndex: 1100,
        borderRadius: "var(--glass-radius, 0)",
      }}
    >
      Onboarding reset — reloading welcome modal
    </div>
  );
}
