"use client";

/**
 * WelcomeModal — first-time user onboarding modal (Round 14).
 *
 * Four steps:
 *   1. Welcome / branding
 *   2. Core features (3 cards: Holdings / 13F / Watchlist)
 *   3. Optional notifications setup (link to /settings/notifications)
 *   4. CTA — "Start" jumps to /holdings (the most actionable first page)
 *
 * Driven entirely by props — the parent (OnboardingProvider) owns the
 * `open` flag and the completion callback. The modal itself only knows
 * about step navigation. That keeps it trivially testable: render it
 * with `open` and step through the buttons.
 *
 * STRATOS styling:
 *   - GlassPanel for the card chrome (no shadow inflation — already
 *     baked into --glass-shadow).
 *   - ClippedButton for primary CTAs.
 *   - Fixed-position overlay with dim backdrop (no portal — we render
 *     inline because the document body already has `var(--background)`).
 *   - Focus trap is minimal (initial focus on the primary button, Esc
 *     to close). A full trap is overkill for a 4-step linear flow.
 *
 * Accessibility:
 *   - role="dialog", aria-modal="true"
 *   - aria-labelledby pointing to the step title
 *   - Esc key closes (treated as skip — does NOT advance to /holdings)
 *   - Focus management: primary button auto-focuses on each step
 */

import React, { useCallback, useEffect, useMemo, useRef } from "react";
import { useRouter } from "next/navigation";
import {
  BarChart3,
  Bell,
  Briefcase,
  Eye,
  X,
} from "lucide-react";
import {
  ClippedButton,
  GlassPanel,
} from "@/components/stratos/primitives";
import { useI18n } from "@/i18n/context";

export interface WelcomeModalProps {
  open: boolean;
  /** User dismissed the modal (Esc / "略過"). Flag is still set so it
   *  won't reopen. */
  onClose: () => void;
  /** User completed the flow ("開始使用"). Parent navigates + flags. */
  onComplete: () => void;
}

type StepKey = "welcome" | "features" | "notifications" | "cta";

const STEPS: StepKey[] = ["welcome", "features", "notifications", "cta"];

const overlayStyle: React.CSSProperties = {
  position: "fixed",
  inset: 0,
  background: "rgba(0, 0, 0, 0.72)",
  backdropFilter: "blur(6px)",
  WebkitBackdropFilter: "blur(6px)",
  display: "flex",
  alignItems: "center",
  justifyContent: "center",
  padding: 16,
  zIndex: 1000,
};

const panelStyle: React.CSSProperties = {
  width: "100%",
  maxWidth: 560,
  position: "relative",
};

const closeButtonStyle: React.CSSProperties = {
  position: "absolute",
  top: 12,
  right: 12,
  background: "transparent",
  border: "none",
  color: "var(--text-muted)",
  cursor: "pointer",
  padding: 4,
  display: "flex",
  alignItems: "center",
  justifyContent: "center",
};

const dotsRowStyle: React.CSSProperties = {
  display: "flex",
  alignItems: "center",
  justifyContent: "center",
  gap: 8,
  marginTop: 20,
  marginBottom: 12,
};

const dotStyle = (active: boolean): React.CSSProperties => ({
  width: 8,
  height: 8,
  borderRadius: "50%",
  background: active ? "var(--accent-cyan)" : "var(--border-color)",
  transition: "background 0.2s",
});

const titleStyle: React.CSSProperties = {
  fontSize: 22,
  fontWeight: 700,
  color: "var(--foreground)",
  letterSpacing: "-0.02em",
  marginBottom: 8,
};

const subtitleStyle: React.CSSProperties = {
  fontSize: 14,
  color: "var(--text-muted)",
  lineHeight: 1.55,
  marginBottom: 16,
};

const featureCardStyle: React.CSSProperties = {
  display: "flex",
  alignItems: "flex-start",
  gap: 12,
  padding: 14,
  border: "1px solid var(--border-color)",
  background: "var(--bg-secondary, rgba(255,255,255,0.02))",
  borderRadius: "var(--glass-radius, 0)",
};

const featureIconStyle: React.CSSProperties = {
  display: "flex",
  alignItems: "center",
  justifyContent: "center",
  width: 36,
  height: 36,
  background: "var(--card-hover, rgba(0,229,255,0.08))",
  color: "var(--accent-cyan)",
  flexShrink: 0,
  borderRadius: "var(--glass-radius, 0)",
};

const actionsRowStyle: React.CSSProperties = {
  display: "flex",
  alignItems: "center",
  justifyContent: "space-between",
  gap: 12,
  marginTop: 24,
};

export function WelcomeModal({
  open,
  onClose,
  onComplete,
}: WelcomeModalProps) {
  const { t } = useI18n();
  const router = useRouter();
  const [stepIndex, setStepIndex] = React.useState(0);
  const primaryButtonRef = useRef<HTMLDivElement>(null);

  // Reset to step 0 each time the modal opens. We don't want a user who
  // dismissed mid-flow last time to land mid-flow again -- and the
  // parent never reopens the modal once `setOnboarded()` is called
  // anyway, so this only matters for dev/reset cycles.
  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect -- reset step pointer on parent-driven open transition (same justification as feature-tour.tsx)
    if (open) setStepIndex(0);
  }, [open]);

  // Esc key → close (treated as skip — parent still marks onboarded).
  useEffect(() => {
    if (!open) return;
    const handler = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    window.addEventListener("keydown", handler);
    return () => window.removeEventListener("keydown", handler);
  }, [open, onClose]);

  // Auto-focus the primary button on each step transition.
  useEffect(() => {
    if (!open) return;
    const btn = primaryButtonRef.current?.querySelector("button");
    if (btn instanceof HTMLButtonElement) btn.focus();
  }, [open, stepIndex]);

  const ob = (t.onboarding ?? {}) as Record<string, unknown>;
  const welcomeT = (ob.welcome ?? {}) as Record<string, string>;

  const stepKey = STEPS[stepIndex];

  const goNext = useCallback(() => {
    if (stepIndex < STEPS.length - 1) {
      setStepIndex((i) => i + 1);
    } else {
      onComplete();
      router.push("/holdings");
    }
  }, [stepIndex, onComplete, router]);

  const goNotifications = useCallback(() => {
    onComplete();
    router.push("/settings/notifications");
  }, [onComplete, router]);

  const headerId = useMemo(() => `welcome-modal-title-${stepKey}`, [stepKey]);

  if (!open) return null;

  return (
    <div
      style={overlayStyle}
      role="dialog"
      aria-modal="true"
      aria-labelledby={headerId}
      onClick={(e) => {
        // Click outside the panel → skip. Click *inside* panel does not
        // bubble here because stopPropagation on the panel below.
        if (e.target === e.currentTarget) onClose();
      }}
    >
      <div
        style={panelStyle}
        onClick={(e) => e.stopPropagation()}
      >
        <GlassPanel>
          <button
            type="button"
            aria-label={(welcomeT.close as string) ?? "關閉"}
            onClick={onClose}
            style={closeButtonStyle}
          >
            <X size={18} strokeWidth={2} />
          </button>

          {stepKey === "welcome" && (
            <>
              <div
                style={{
                  display: "flex",
                  alignItems: "center",
                  justifyContent: "center",
                  width: 64,
                  height: 64,
                  margin: "8px auto 16px",
                  background: "var(--card-hover, rgba(0,229,255,0.08))",
                  color: "var(--accent-cyan)",
                  borderRadius: "var(--glass-radius, 0)",
                }}
                aria-hidden="true"
              >
                <BarChart3 size={32} strokeWidth={1.5} />
              </div>
              <h2 id={headerId} style={{ ...titleStyle, textAlign: "center" }}>
                {welcomeT.step1_title ?? "歡迎來到 Uni-Seeker"}
              </h2>
              <p style={{ ...subtitleStyle, textAlign: "center" }}>
                {welcomeT.step1_subtitle ??
                  "一站式追蹤台美股持倉、機構動向，與你關心的個股。"}
              </p>
            </>
          )}

          {stepKey === "features" && (
            <>
              <h2 id={headerId} style={titleStyle}>
                {welcomeT.step2_title ?? "核心功能"}
              </h2>
              <p style={subtitleStyle}>
                {welcomeT.step2_subtitle ??
                  "三個你最常用的工作流，讓投資決策更有依據。"}
              </p>
              <div
                style={{
                  display: "flex",
                  flexDirection: "column",
                  gap: 10,
                }}
              >
                <FeatureCard
                  icon={<Briefcase size={20} strokeWidth={1.5} />}
                  title={welcomeT.feature_holdings_title ?? "Holdings 對賬"}
                  desc={
                    welcomeT.feature_holdings_desc ??
                    "多帳戶 / 多幣別追蹤持股、未實現損益、配息紀錄。"
                  }
                />
                <FeatureCard
                  icon={<BarChart3 size={20} strokeWidth={1.5} />}
                  title={welcomeT.feature_institutional_title ?? "13F 機構追蹤"}
                  desc={
                    welcomeT.feature_institutional_desc ??
                    "追蹤大型機構持倉變化，分析買賣動向與時序。"
                  }
                />
                <FeatureCard
                  icon={<Eye size={20} strokeWidth={1.5} />}
                  title={welcomeT.feature_watchlist_title ?? "自選股研究"}
                  desc={
                    welcomeT.feature_watchlist_desc ??
                    "建立關注清單，搭配技術 / 籌碼指標做深度研究。"
                  }
                />
              </div>
            </>
          )}

          {stepKey === "notifications" && (
            <>
              <div
                style={{
                  display: "flex",
                  alignItems: "center",
                  justifyContent: "center",
                  width: 56,
                  height: 56,
                  margin: "8px auto 14px",
                  background: "var(--card-hover, rgba(0,229,255,0.08))",
                  color: "var(--accent-cyan)",
                  borderRadius: "var(--glass-radius, 0)",
                }}
                aria-hidden="true"
              >
                <Bell size={28} strokeWidth={1.5} />
              </div>
              <h2 id={headerId} style={{ ...titleStyle, textAlign: "center" }}>
                {welcomeT.step3_title ?? "設定通知"}
              </h2>
              <p style={{ ...subtitleStyle, textAlign: "center" }}>
                {welcomeT.step3_subtitle ??
                  "選擇透過 Telegram、Email 或 Web Push 接收價格與持倉提醒。"}
              </p>
              <div
                style={{
                  display: "flex",
                  alignItems: "center",
                  justifyContent: "center",
                  marginTop: 8,
                }}
                ref={primaryButtonRef}
              >
                <ClippedButton
                  variant="cyan-ghost"
                  size="md"
                  onClick={goNotifications}
                >
                  {welcomeT.step3_cta ?? "前往通知設定"}
                </ClippedButton>
              </div>
            </>
          )}

          {stepKey === "cta" && (
            <>
              <h2 id={headerId} style={{ ...titleStyle, textAlign: "center" }}>
                {welcomeT.step4_title ?? "下一步"}
              </h2>
              <p style={{ ...subtitleStyle, textAlign: "center" }}>
                {welcomeT.step4_subtitle ??
                  "從建立你的第一個券商帳戶開始，體驗持倉對賬。"}
              </p>
            </>
          )}

          {/* Step dots */}
          <div style={dotsRowStyle} aria-hidden="true">
            {STEPS.map((s, i) => (
              <span key={s} style={dotStyle(i === stepIndex)} />
            ))}
          </div>

          {/* Actions */}
          <div style={actionsRowStyle}>
            <ClippedButton
              variant="red-ghost"
              size="md"
              onClick={onClose}
            >
              {(ob.skip as string) ?? "略過"}
            </ClippedButton>
            <div ref={stepKey === "notifications" ? null : primaryButtonRef}>
              <ClippedButton
                variant="red-solid"
                size="md"
                onClick={goNext}
              >
                {stepKey === "cta"
                  ? ((ob.start as string) ?? "開始使用")
                  : ((ob.next as string) ?? "下一步")}
              </ClippedButton>
            </div>
          </div>
        </GlassPanel>
      </div>
    </div>
  );
}

interface FeatureCardProps {
  icon: React.ReactNode;
  title: string;
  desc: string;
}

function FeatureCard({ icon, title, desc }: FeatureCardProps) {
  return (
    <div style={featureCardStyle}>
      <div style={featureIconStyle} aria-hidden="true">
        {icon}
      </div>
      <div style={{ flex: 1, minWidth: 0 }}>
        <div
          style={{
            fontSize: 13,
            fontWeight: 700,
            color: "var(--foreground)",
            marginBottom: 4,
          }}
        >
          {title}
        </div>
        <div
          style={{
            fontSize: 12,
            color: "var(--text-muted)",
            lineHeight: 1.5,
          }}
        >
          {desc}
        </div>
      </div>
    </div>
  );
}
