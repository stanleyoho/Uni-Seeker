"use client";

/**
 * FeatureTour — lightweight Shepherd-style guided tour (Round 14).
 *
 * Zero dependencies. Renders:
 *   1. A full-viewport dim overlay
 *   2. A "spotlight" rectangle aligned to the target element's
 *      getBoundingClientRect(), keeping the target visually unobscured
 *   3. A tooltip positioned next to the target with the step's content
 *
 * Targeting:
 *   Each step has a CSS selector. We resolve it via
 *   `document.querySelector` on every recalculation pass. If the target
 *   is missing (page hasn't rendered it yet, user scrolled it off,
 *   selector typo), we render a centered fallback tooltip so the user
 *   isn't stranded — they can still skip / next through.
 *
 * Recalculation:
 *   - On step change
 *   - On window resize
 *   - On window scroll (the tooltip uses fixed positioning, so scrolling
 *     changes the target's viewport rect)
 *   - On a 16ms rAF tick while the tour is open (cheap; covers
 *     animations, lazy-mounting content, etc.)
 *
 * Why not portal? The overlay uses position: fixed + zIndex 999 — sits
 * above page content but below the WelcomeModal (1000). React renders
 * it inline, which is fine because pointer-events are scoped to the
 * tooltip element only (overlay accepts clicks but routes them to
 * "next").
 *
 * STRATOS styling:
 *   - GlassPanel for the tooltip
 *   - ClippedButton primary/ghost for next/skip
 *   - Cyan border on the spotlight (matches accent palette)
 */

import React, {
  useCallback,
  useEffect,
  useLayoutEffect,
  useMemo,
  useRef,
  useState,
} from "react";
import {
  ClippedButton,
  GlassPanel,
} from "@/components/stratos/primitives";
import { useI18n } from "@/i18n/context";

export interface TourStep {
  /** CSS selector targeting the element to highlight. May be null for
   *  intro/outro steps that don't point at a specific element. */
  target: string | null;
  /** Translation key under `onboarding.tour.holdings.*` — resolved at
   *  render time. Fallbacks live in DEFAULT_HOLDINGS_STEPS below. */
  titleKey: string;
  contentKey: string;
  /** Fallback strings if the i18n lookup misses. */
  titleFallback: string;
  contentFallback: string;
}

export interface FeatureTourProps {
  open: boolean;
  steps: TourStep[];
  onClose: () => void;
  /** Called when the user finishes (Got it!) or skips. Either way the
   *  parent should mark the tour as seen so it doesn't reopen. */
  onComplete: () => void;
}

// Tooltip dimensions used for placement math. Kept as constants because
// the tooltip's measured size can fluctuate per step (different content
// lengths), but using a stable estimate keeps positioning predictable
// and avoids a measure-then-reposition flicker.
const TOOLTIP_WIDTH = 320;
const TOOLTIP_HEIGHT = 160;
const TOOLTIP_GAP = 12;
const SPOTLIGHT_PAD = 6;

const overlayStyle: React.CSSProperties = {
  position: "fixed",
  inset: 0,
  zIndex: 999,
  pointerEvents: "none",
};

const dimStyle: React.CSSProperties = {
  position: "absolute",
  background: "rgba(0, 0, 0, 0.65)",
  pointerEvents: "auto",
};

interface Box {
  top: number;
  left: number;
  width: number;
  height: number;
}

interface Placement {
  spotlight: Box | null;
  tooltipTop: number;
  tooltipLeft: number;
  /** Direction the tooltip is anchored — used to render an arrow. */
  side: "top" | "bottom" | "left" | "right" | "center";
}

/**
 * Compute the spotlight rect and tooltip position given a target.
 * When `targetRect` is null (no selector or selector not found), the
 * tooltip centers on the viewport with no spotlight.
 */
function computePlacement(
  targetRect: DOMRect | null,
  viewport: { w: number; h: number },
): Placement {
  if (!targetRect) {
    return {
      spotlight: null,
      tooltipTop: (viewport.h - TOOLTIP_HEIGHT) / 2,
      tooltipLeft: (viewport.w - TOOLTIP_WIDTH) / 2,
      side: "center",
    };
  }

  const spotlight: Box = {
    top: targetRect.top - SPOTLIGHT_PAD,
    left: targetRect.left - SPOTLIGHT_PAD,
    width: targetRect.width + SPOTLIGHT_PAD * 2,
    height: targetRect.height + SPOTLIGHT_PAD * 2,
  };

  // Prefer below, then above, then right, then left.
  const spaceBelow = viewport.h - (targetRect.bottom + TOOLTIP_GAP);
  const spaceAbove = targetRect.top - TOOLTIP_GAP;
  const spaceRight = viewport.w - (targetRect.right + TOOLTIP_GAP);
  const spaceLeft = targetRect.left - TOOLTIP_GAP;

  let side: Placement["side"] = "bottom";
  let top = targetRect.bottom + TOOLTIP_GAP;
  let left = targetRect.left + targetRect.width / 2 - TOOLTIP_WIDTH / 2;

  if (spaceBelow < TOOLTIP_HEIGHT && spaceAbove >= TOOLTIP_HEIGHT) {
    side = "top";
    top = targetRect.top - TOOLTIP_GAP - TOOLTIP_HEIGHT;
  } else if (
    spaceBelow < TOOLTIP_HEIGHT &&
    spaceAbove < TOOLTIP_HEIGHT &&
    spaceRight >= TOOLTIP_WIDTH
  ) {
    side = "right";
    top = targetRect.top + targetRect.height / 2 - TOOLTIP_HEIGHT / 2;
    left = targetRect.right + TOOLTIP_GAP;
  } else if (
    spaceBelow < TOOLTIP_HEIGHT &&
    spaceAbove < TOOLTIP_HEIGHT &&
    spaceLeft >= TOOLTIP_WIDTH
  ) {
    side = "left";
    top = targetRect.top + targetRect.height / 2 - TOOLTIP_HEIGHT / 2;
    left = targetRect.left - TOOLTIP_GAP - TOOLTIP_WIDTH;
  }

  // Clamp to viewport so tooltip never overflows the screen.
  left = Math.max(8, Math.min(left, viewport.w - TOOLTIP_WIDTH - 8));
  top = Math.max(8, Math.min(top, viewport.h - TOOLTIP_HEIGHT - 8));

  return { spotlight, tooltipTop: top, tooltipLeft: left, side };
}

export function FeatureTour({
  open,
  steps,
  onClose,
  onComplete,
}: FeatureTourProps) {
  const { tr } = useI18n();
  const [stepIndex, setStepIndex] = useState(0);
  const [placement, setPlacement] = useState<Placement>({
    spotlight: null,
    tooltipTop: 0,
    tooltipLeft: 0,
    side: "center",
  });
  const rafId = useRef<number | null>(null);

  // Reset to step 0 each time the tour opens. Sync setState on the
  // `open` prop transition; deriving stepIndex would require keying
  // the whole tour component off `open` and remounting on each open,
  // which is heavier than the single state reset.
  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect -- reset step pointer on parent-driven open transition; remount alternative is more expensive
    if (open) setStepIndex(0);
  }, [open]);

  const recalculate = useCallback(() => {
    if (!open || typeof window === "undefined") return;
    const step = steps[stepIndex];
    if (!step) return;

    let targetRect: DOMRect | null = null;
    if (step.target) {
      const el = document.querySelector(step.target);
      if (el instanceof HTMLElement) {
        targetRect = el.getBoundingClientRect();
      }
    }
    const viewport = {
      w: window.innerWidth,
      h: window.innerHeight,
    };
    setPlacement(computePlacement(targetRect, viewport));
  }, [open, steps, stepIndex]);

  // Recalculate on step change + on resize/scroll. The rAF loop covers
  // mid-frame layout shifts (lazy charts, accordions, etc.). We must
  // setState (placement) synchronously here because layout effects
  // run before paint -- this is exactly the use case useLayoutEffect
  // exists for, even though the rule's heuristic flags it.
  useLayoutEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect -- layout measurement -> setState is the canonical useLayoutEffect pattern; setPlacement runs before paint
    recalculate();
  }, [recalculate]);

  useEffect(() => {
    if (!open) return;
    const handler = () => recalculate();
    window.addEventListener("resize", handler);
    window.addEventListener("scroll", handler, true);

    const tick = () => {
      recalculate();
      rafId.current = window.requestAnimationFrame(tick);
    };
    rafId.current = window.requestAnimationFrame(tick);

    return () => {
      window.removeEventListener("resize", handler);
      window.removeEventListener("scroll", handler, true);
      if (rafId.current !== null) {
        window.cancelAnimationFrame(rafId.current);
        rafId.current = null;
      }
    };
  }, [open, recalculate]);

  // Esc to skip.
  useEffect(() => {
    if (!open) return;
    const handler = (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        onComplete();
        onClose();
      }
    };
    window.addEventListener("keydown", handler);
    return () => window.removeEventListener("keydown", handler);
  }, [open, onComplete, onClose]);

  const step = steps[stepIndex];

  const next = useCallback(() => {
    if (stepIndex < steps.length - 1) {
      setStepIndex((i) => i + 1);
    } else {
      onComplete();
      onClose();
    }
  }, [stepIndex, steps.length, onComplete, onClose]);

  const skip = useCallback(() => {
    onComplete();
    onClose();
  }, [onComplete, onClose]);

  // Build the 4 dim rectangles around the spotlight. When there's no
  // spotlight (centered fallback), we render a single full-screen dim.
  const dimRects = useMemo(() => {
    if (!placement.spotlight) {
      return [{ top: 0, left: 0, width: "100vw", height: "100vh" }];
    }
    const s = placement.spotlight;
    return [
      // top strip
      { top: 0, left: 0, width: "100vw", height: s.top },
      // bottom strip
      {
        top: s.top + s.height,
        left: 0,
        width: "100vw",
        height: `calc(100vh - ${s.top + s.height}px)`,
      },
      // left strip
      { top: s.top, left: 0, width: s.left, height: s.height },
      // right strip
      {
        top: s.top,
        left: s.left + s.width,
        width: `calc(100vw - ${s.left + s.width}px)`,
        height: s.height,
      },
    ];
  }, [placement.spotlight]);

  if (!open || !step) return null;

  const title = tr(step.titleKey);
  const resolvedTitle =
    title === step.titleKey ? step.titleFallback : title;
  const content = tr(step.contentKey);
  const resolvedContent =
    content === step.contentKey ? step.contentFallback : content;

  const isLast = stepIndex === steps.length - 1;

  return (
    <div style={overlayStyle} aria-hidden="false">
      {/* Dim rectangles. They accept clicks and route to "next" so the
          user has a generous tap target. */}
      {dimRects.map((rect, i) => (
        <div
          key={i}
          style={{
            ...dimStyle,
            top: rect.top as number | string,
            left: rect.left as number | string,
            width: rect.width as number | string,
            height: rect.height as number | string,
          }}
          onClick={next}
        />
      ))}

      {/* Spotlight border — purely visual, doesn't intercept events. */}
      {placement.spotlight && (
        <div
          style={{
            position: "absolute",
            top: placement.spotlight.top,
            left: placement.spotlight.left,
            width: placement.spotlight.width,
            height: placement.spotlight.height,
            border: "2px solid var(--accent-cyan)",
            boxShadow:
              "0 0 0 9999px rgba(0,0,0,0.0), 0 0 16px var(--accent-cyan)",
            pointerEvents: "none",
            borderRadius: 4,
          }}
        />
      )}

      {/* Tooltip */}
      <div
        role="dialog"
        aria-modal="false"
        aria-label={resolvedTitle}
        style={{
          position: "fixed",
          top: placement.tooltipTop,
          left: placement.tooltipLeft,
          width: TOOLTIP_WIDTH,
          pointerEvents: "auto",
        }}
        onClick={(e) => e.stopPropagation()}
      >
        <GlassPanel>
          <div
            style={{
              fontSize: 11,
              fontWeight: 600,
              textTransform: "uppercase",
              letterSpacing: "0.05em",
              color: "var(--text-muted)",
              marginBottom: 6,
            }}
          >
            {stepIndex + 1} / {steps.length}
          </div>
          <div
            style={{
              fontSize: 15,
              fontWeight: 700,
              color: "var(--foreground)",
              marginBottom: 6,
            }}
          >
            {resolvedTitle}
          </div>
          <p
            style={{
              fontSize: 13,
              color: "var(--text-muted)",
              lineHeight: 1.5,
              marginBottom: 14,
            }}
          >
            {resolvedContent}
          </p>
          <div
            style={{
              display: "flex",
              alignItems: "center",
              justifyContent: "space-between",
              gap: 8,
            }}
          >
            <ClippedButton
              variant="red-ghost"
              size="sm"
              onClick={skip}
            >
              {tr("onboarding.skip") === "onboarding.skip"
                ? "略過"
                : tr("onboarding.skip")}
            </ClippedButton>
            <ClippedButton
              variant="red-solid"
              size="sm"
              onClick={next}
            >
              {isLast
                ? tr("onboarding.got_it") === "onboarding.got_it"
                  ? "完成"
                  : tr("onboarding.got_it")
                : tr("onboarding.next") === "onboarding.next"
                  ? "下一步"
                  : tr("onboarding.next")}
            </ClippedButton>
          </div>
        </GlassPanel>
      </div>
    </div>
  );
}

/**
 * Default tour steps for /holdings. Selectors target `data-tour-*`
 * attributes added to the holdings page — keeping selectors as data-
 * attributes shields the tour from refactors that rename CSS classes.
 */
export const HOLDINGS_TOUR_STEPS: TourStep[] = [
  {
    target: '[data-tour="holdings-add-account"]',
    titleKey: "onboarding.tour.holdings.step1_title",
    contentKey: "onboarding.tour.holdings.step1_content",
    titleFallback: "建立你的第一個券商帳戶",
    contentFallback:
      "Uni-Seeker 支援多帳戶管理，先建立一個帳戶來存放你的持股。",
  },
  {
    target: '[data-tour="holdings-add-trade"]',
    titleKey: "onboarding.tour.holdings.step2_title",
    contentKey: "onboarding.tour.holdings.step2_content",
    titleFallback: "新增交易來追蹤持股",
    contentFallback:
      "記錄買進 / 賣出資料，系統自動計算成本、損益與部位。",
  },
  {
    target: '[data-tour="holdings-kpi"]',
    titleKey: "onboarding.tour.holdings.step3_title",
    contentKey: "onboarding.tour.holdings.step3_content",
    titleFallback: "Portfolio Summary",
    contentFallback:
      "這裡顯示你的總市值、總成本、未實現損益與今日漲跌。",
  },
  {
    target: '[data-tour="holdings-positions"]',
    titleKey: "onboarding.tour.holdings.step4_title",
    contentKey: "onboarding.tour.holdings.step4_content",
    titleFallback: "持股清單",
    contentFallback:
      "依股票列出單檔持股、平均成本、現價與未實現損益。",
  },
  {
    target: '[data-tour="holdings-currency"]',
    titleKey: "onboarding.tour.holdings.step5_title",
    contentKey: "onboarding.tour.holdings.step5_content",
    titleFallback: "多幣別 Portfolio",
    contentFallback:
      "Pro 方案解鎖多幣別檢視 — 自動換算成你選擇的基準幣別。",
  },
  {
    target: null,
    titleKey: "onboarding.tour.holdings.step6_title",
    contentKey: "onboarding.tour.holdings.step6_content",
    titleFallback: "完成！",
    contentFallback:
      "你已掌握 Holdings 的核心功能。隨時可以從設定重新打開導覽。",
  },
];
