/**
 * onboarding-state — localStorage flags for the first-time user onboarding
 * flow (Round 14).
 *
 * Two independent flags:
 *
 *   - `uni-seeker-onboarded`            → set after the user completes (or
 *                                          skips) the WelcomeModal at least
 *                                          once. Prevents the modal from
 *                                          ever opening again on this
 *                                          browser.
 *   - `uni-seeker-holdings-tour-shown`  → set after the user finishes (or
 *                                          dismisses) the interactive tour
 *                                          on /holdings.
 *
 * SSR rule: every reader function returns the "already done" answer when
 * `window` is undefined. That way the server render never tries to mount
 * the modal/tour, avoiding a hydration mismatch where the modal flashes
 * for one frame before localStorage is read. The real check happens once
 * the component remounts on the client via useEffect.
 *
 * The localStorage keys are scoped to `uni-seeker-` to avoid collision
 * with other Stanley-ecosystem apps that may share the same origin in
 * the future.
 */

const KEY_ONBOARDED = "uni-seeker-onboarded";
const KEY_HOLDINGS_TOUR_SHOWN = "uni-seeker-holdings-tour-shown";

/** Welcome modal has already been completed (or skipped). */
export function isOnboarded(): boolean {
  if (typeof window === "undefined") return true;
  try {
    return window.localStorage.getItem(KEY_ONBOARDED) === "true";
  } catch {
    // localStorage can throw under strict cookie/privacy modes — treat
    // a throwing browser as "already onboarded" so we never spam the user.
    return true;
  }
}

/** Mark the welcome modal as completed. Idempotent. */
export function setOnboarded(): void {
  if (typeof window === "undefined") return;
  try {
    window.localStorage.setItem(KEY_ONBOARDED, "true");
  } catch {
    /* swallow — see isOnboarded() */
  }
}

/** /holdings interactive tour has been shown (or dismissed). */
export function isHoldingsTourShown(): boolean {
  if (typeof window === "undefined") return true;
  try {
    return window.localStorage.getItem(KEY_HOLDINGS_TOUR_SHOWN) === "true";
  } catch {
    return true;
  }
}

/** Mark the holdings tour as shown. Idempotent. */
export function setHoldingsTourShown(): void {
  if (typeof window === "undefined") return;
  try {
    window.localStorage.setItem(KEY_HOLDINGS_TOUR_SHOWN, "true");
  } catch {
    /* swallow */
  }
}

/**
 * Reset both flags. Intended for dev/QA — exposed via the
 * `<OnboardingResetButton />` component (Ctrl+Shift+R chord on any page).
 */
export function resetOnboardingFlags(): void {
  if (typeof window === "undefined") return;
  try {
    window.localStorage.removeItem(KEY_ONBOARDED);
    window.localStorage.removeItem(KEY_HOLDINGS_TOUR_SHOWN);
  } catch {
    /* swallow */
  }
}
