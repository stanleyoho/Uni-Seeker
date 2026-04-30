"use client";

import React from "react";

/* ------------------------------------------------------------------ */
/*  1. GlassPanel                                                      */
/* ------------------------------------------------------------------ */

interface GlassPanelProps {
  title?: string;
  icon?: React.ReactNode;
  children: React.ReactNode;
  className?: string;
  noPadding?: boolean;
}

const glassStyle: React.CSSProperties = {
  background: "rgba(255,255,255,0.03)",
  backdropFilter: "blur(40px) saturate(180%)",
  WebkitBackdropFilter: "blur(40px) saturate(180%)",
  border: "1px solid rgba(255,255,255,0.12)",
  backgroundImage:
    "linear-gradient(135deg, rgba(255,255,255,0.08) 0%, transparent 50%)",
  boxShadow:
    "inset 0 1px 0 rgba(255,255,255,0.1), 0 8px 32px rgba(0,0,0,0.4)",
  borderRadius: 0,
};

export function GlassPanel({
  title,
  icon,
  children,
  className = "",
  noPadding = false,
}: GlassPanelProps) {
  return (
    <div
      className={className}
      style={{
        ...glassStyle,
        padding: noPadding ? 0 : 24,
      }}
    >
      {title && (
        <div
          style={{
            display: "flex",
            alignItems: "center",
            gap: 8,
            marginBottom: 16,
          }}
        >
          {icon && <span>{icon}</span>}
          <span
            style={{
              fontSize: 14,
              fontWeight: 700,
              textTransform: "uppercase",
              letterSpacing: "-0.04em",
              color: "#9CA3AF",
            }}
          >
            {title}
          </span>
        </div>
      )}
      {children}
    </div>
  );
}

/* ------------------------------------------------------------------ */
/*  2. ClippedButton                                                   */
/* ------------------------------------------------------------------ */

type ButtonVariant =
  | "red-solid"
  | "white-solid"
  | "red-ghost"
  | "green-solid"
  | "cyan-ghost";

type ButtonSize = "sm" | "md" | "lg";

interface ClippedButtonProps {
  variant: ButtonVariant;
  size: ButtonSize;
  onClick?: () => void;
  children: React.ReactNode;
  className?: string;
}

const cutSize: Record<ButtonSize, number> = { sm: 8, md: 12, lg: 14 };

const variantStyles: Record<
  ButtonVariant,
  React.CSSProperties
> = {
  "red-solid": { background: "#EE3F2C", color: "#fff", border: "none" },
  "white-solid": { background: "#fff", color: "#000", border: "none" },
  "red-ghost": {
    background: "transparent",
    color: "#EE3F2C",
    border: "1px solid #EE3F2C",
  },
  "green-solid": { background: "#10B981", color: "#fff", border: "none" },
  "cyan-ghost": {
    background: "transparent",
    color: "#00E5FF",
    border: "1px solid #00E5FF",
  },
};

const sizeClasses: Record<ButtonSize, string> = {
  sm: "px-3 py-1 text-xs",
  md: "px-5 py-2 text-sm",
  lg: "px-7 py-3 text-base",
};

export function ClippedButton({
  variant,
  size,
  onClick,
  children,
  className = "",
}: ClippedButtonProps) {
  const c = cutSize[size];

  return (
    <button
      onClick={onClick}
      className={`${sizeClasses[size]} font-semibold ${className}`}
      style={{
        ...variantStyles[variant],
        clipPath: `polygon(0 0, calc(100% - ${c}px) 0, 100% ${c}px, 100% 100%, ${c}px 100%, 0 calc(100% - ${c}px))`,
        transition: "all 200ms",
        cursor: "pointer",
        outline: "none",
      }}
      onFocus={(e) => {
        e.currentTarget.style.outline = "1px solid #00E5FF";
        e.currentTarget.style.outlineOffset = "2px";
      }}
      onBlur={(e) => {
        e.currentTarget.style.outline = "none";
        e.currentTarget.style.outlineOffset = "0px";
      }}
    >
      {children}
    </button>
  );
}

/* ------------------------------------------------------------------ */
/*  3. KpiCard                                                         */
/* ------------------------------------------------------------------ */

interface KpiCardProps {
  label: string;
  value: string;
  delta: string;
  direction: "up" | "down" | "flat";
}

const directionConfig: Record<
  KpiCardProps["direction"],
  { arrow: string; color: string }
> = {
  up: { arrow: "▲", color: "#EE3F2C" },
  down: { arrow: "▼", color: "#10B981" },
  flat: { arrow: "—", color: "#9CA3AF" },
};

export function KpiCard({ label, value, delta, direction }: KpiCardProps) {
  const { arrow, color } = directionConfig[direction];

  return (
    <div
      style={{
        background: "rgba(255,255,255,0.04)",
        backdropFilter: "blur(40px) saturate(180%)",
        WebkitBackdropFilter: "blur(40px) saturate(180%)",
        border: "1px solid rgba(255,255,255,0.10)",
        backgroundImage:
          "linear-gradient(135deg, rgba(255,255,255,0.06) 0%, transparent 50%)",
        boxShadow:
          "inset 0 1px 0 rgba(255,255,255,0.08), 0 8px 32px rgba(0,0,0,0.3)",
        borderRadius: 0,
        padding: 20,
      }}
    >
      <div
        style={{
          fontSize: 11,
          fontWeight: 700,
          textTransform: "uppercase",
          letterSpacing: "0.05em",
          color: "#9CA3AF",
          marginBottom: 4,
        }}
      >
        {label}
      </div>
      <div
        style={{
          fontSize: 32,
          fontWeight: 600,
          color: "#fff",
          fontVariantNumeric: "tabular-nums",
          lineHeight: 1.1,
          marginBottom: 4,
        }}
      >
        {value}
      </div>
      <div style={{ fontSize: 13, fontWeight: 500, color }}>
        {arrow} {delta}
      </div>
    </div>
  );
}

/* ------------------------------------------------------------------ */
/*  4. AmbientBackground                                               */
/* ------------------------------------------------------------------ */

const keyframesId = "stratos-drift";

const driftKeyframes = `
@keyframes ${keyframesId} {
  0%   { transform: translateX(0)   translateY(0);   }
  25%  { transform: translateX(30px)  translateY(-20px); }
  50%  { transform: translateX(-20px) translateY(15px);  }
  75%  { transform: translateX(15px)  translateY(-10px); }
  100% { transform: translateX(0)   translateY(0);   }
}
@media (prefers-reduced-motion: reduce) {
  .stratos-drift-group { animation: none !important; }
}
`;

export function AmbientBackground() {
  return (
    <div
      style={{
        position: "fixed",
        inset: 0,
        pointerEvents: "none",
        zIndex: 0,
        overflow: "hidden",
      }}
      aria-hidden="true"
    >
      {/* inject keyframes */}
      <style dangerouslySetInnerHTML={{ __html: driftKeyframes }} />

      <svg
        width="100%"
        height="100%"
        xmlns="http://www.w3.org/2000/svg"
        style={{ position: "absolute", inset: 0 }}
      >
        <defs>
          {/* grid pattern */}
          <pattern
            id="stratos-grid"
            width="60"
            height="60"
            patternUnits="userSpaceOnUse"
          >
            <path
              d="M 60 0 L 0 0 0 60"
              fill="none"
              stroke="rgba(255,255,255,0.04)"
              strokeWidth="1"
            />
          </pattern>

          {/* blur filter for drifting lines */}
          <filter id="stratos-blur">
            <feGaussianBlur stdDeviation="6" />
          </filter>
        </defs>

        {/* grid */}
        <rect width="100%" height="100%" fill="url(#stratos-grid)" />

        {/* slow-drifting blurred chart-line shadows */}
        <g
          className="stratos-drift-group"
          style={{ animation: `${keyframesId} 60s ease-in-out infinite` }}
          filter="url(#stratos-blur)"
          opacity="0.06"
        >
          <path
            d="M0,300 Q200,250 400,320 T800,280 T1200,310 T1600,260 T2000,290"
            fill="none"
            stroke="#EE3F2C"
            strokeWidth="2"
          />
          <path
            d="M0,500 Q300,470 600,520 T1000,480 T1400,510 T1800,460"
            fill="none"
            stroke="#00E5FF"
            strokeWidth="2"
          />
          <path
            d="M0,700 Q250,680 500,720 T900,690 T1300,730 T1700,700 T2000,680"
            fill="none"
            stroke="#10B981"
            strokeWidth="2"
          />
        </g>
      </svg>
    </div>
  );
}
