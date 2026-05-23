"use client";

/**
 * OnboardingProvider — orchestrates the first-time user flow (Round 14).
 *
 * Two surfaces:
 *
 *   1. WelcomeModal — opens once when an authenticated user has not yet
 *      been marked `uni-seeker-onboarded`. Opens on auth, NOT on first
 *      mount (so a non-logged-in visitor never sees it).
 *
 *   2. Holdings FeatureTour — opens when the user lands on /holdings and
 *      has not yet been marked `uni-seeker-holdings-tour-shown`. We use
 *      `usePathname()` to detect the route — the provider lives at the
 *      root layout, so a single instance handles every page.
 *
 * Why a provider (vs. inline in `layout.tsx`)?
 *   - Co-locates modal + tour state with derived auth/route checks.
 *   - Exposes `restartOnboarding()` to other components (e.g. a "show
 *     tutorial again" button in settings) without prop drilling.
 *
 * Render order in `app/layout.tsx`:
 *   AuthProvider → OnboardingProvider → children
 *   (OnboardingProvider must sit inside AuthProvider so it can read
 *   `useAuth()`.)
 *
 * SSR safety: initial state mirrors `is*ShownOnServer = true` so the
 * provider renders no modals during the first server pass. We then run
 * a client-only effect that re-reads localStorage and (if needed)
 * toggles the modal on.
 */

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useState,
  type ReactNode,
} from "react";
import { usePathname } from "next/navigation";
import { useAuth } from "@/contexts/auth-context";
import {
  isHoldingsTourShown,
  isOnboarded,
  resetOnboardingFlags,
  setHoldingsTourShown,
  setOnboarded,
} from "@/lib/onboarding-state";
import { WelcomeModal } from "@/components/onboarding/welcome-modal";
import {
  FeatureTour,
  HOLDINGS_TOUR_STEPS,
} from "@/components/onboarding/feature-tour";

interface OnboardingContextValue {
  /** True if the welcome modal is currently displayed. */
  welcomeOpen: boolean;
  /** True if the holdings tour is currently displayed. */
  holdingsTourOpen: boolean;
  /**
   * Clear both localStorage flags AND immediately reopen the welcome
   * modal. Useful for a "Reset tutorial" dev hook.
   */
  restartOnboarding: () => void;
  /** Manually open the holdings tour (e.g. from a help menu). */
  openHoldingsTour: () => void;
}

const OnboardingContext = createContext<OnboardingContextValue>({
  welcomeOpen: false,
  holdingsTourOpen: false,
  restartOnboarding: () => {},
  openHoldingsTour: () => {},
});

export function OnboardingProvider({ children }: { children: ReactNode }) {
  const { user, loading: authLoading } = useAuth();
  const pathname = usePathname();
  const [welcomeOpen, setWelcomeOpen] = useState(false);
  const [holdingsTourOpen, setHoldingsTourOpen] = useState(false);
  // Guards against the auth-resolution race re-firing the modal after
  // the user clicks "略過" but before the underlying localStorage write
  // commits (we set it synchronously, but React batches state updates).
  const [welcomeHandled, setWelcomeHandled] = useState(false);

  /* -------- Welcome modal trigger: fires when auth resolves -------- */
  useEffect(() => {
    if (authLoading) return;
    if (!user) {
      // Logged out → never show. Reset the in-session guard so a fresh
      // login attempt can trigger the modal again.
      setWelcomeOpen(false);
      setWelcomeHandled(false);
      return;
    }
    if (welcomeHandled) return;
    if (!isOnboarded()) {
      setWelcomeOpen(true);
    }
  }, [authLoading, user, welcomeHandled]);

  const handleWelcomeClose = useCallback(() => {
    setOnboarded();
    setWelcomeOpen(false);
    setWelcomeHandled(true);
  }, []);

  const handleWelcomeComplete = useCallback(() => {
    setOnboarded();
    setWelcomeOpen(false);
    setWelcomeHandled(true);
  }, []);

  /* -------- Holdings tour trigger: fires on /holdings nav --------- */
  useEffect(() => {
    if (!user) return;
    if (welcomeOpen) return; // never overlap with welcome
    if (pathname !== "/holdings") return;
    if (isHoldingsTourShown()) return;

    // Wait a tick so the page's data-tour-* targets are mounted before
    // we compute spotlight rects. 600ms is empirically enough for the
    // holdings page's first paint (KPI row + action buttons mount
    // synchronously; only the positions table is async).
    const timeout = window.setTimeout(() => {
      setHoldingsTourOpen(true);
    }, 600);
    return () => window.clearTimeout(timeout);
  }, [pathname, user, welcomeOpen]);

  const handleHoldingsTourComplete = useCallback(() => {
    setHoldingsTourShown();
  }, []);

  const handleHoldingsTourClose = useCallback(() => {
    setHoldingsTourOpen(false);
  }, []);

  const restartOnboarding = useCallback(() => {
    resetOnboardingFlags();
    setWelcomeHandled(false);
    setWelcomeOpen(true);
    setHoldingsTourOpen(false);
  }, []);

  const openHoldingsTour = useCallback(() => {
    setHoldingsTourOpen(true);
  }, []);

  return (
    <OnboardingContext.Provider
      value={{
        welcomeOpen,
        holdingsTourOpen,
        restartOnboarding,
        openHoldingsTour,
      }}
    >
      {children}
      <WelcomeModal
        open={welcomeOpen}
        onClose={handleWelcomeClose}
        onComplete={handleWelcomeComplete}
      />
      <FeatureTour
        open={holdingsTourOpen}
        steps={HOLDINGS_TOUR_STEPS}
        onClose={handleHoldingsTourClose}
        onComplete={handleHoldingsTourComplete}
      />
    </OnboardingContext.Provider>
  );
}

export function useOnboarding() {
  return useContext(OnboardingContext);
}
