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
  style?: React.CSSProperties;
}

const glassStyle: React.CSSProperties = {
  background: "var(--glass-bg)",
  backdropFilter: "var(--glass-blur)",
  WebkitBackdropFilter: "var(--glass-blur)",
  border: "1px solid var(--border-color)",
  backgroundImage: "var(--glass-gradient)",
  boxShadow: "var(--glass-shadow)",
  borderRadius: "var(--glass-radius, 0)",
};

export function GlassPanel({
  title,
  icon,
  children,
  className = "",
  noPadding = false,
  style: extraStyle,
}: GlassPanelProps) {
  return (
    <div
      className={className}
      style={{
        ...glassStyle,
        padding: noPadding ? 0 : 24,
        ...extraStyle,
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
  type?: "button" | "submit" | "reset";
  disabled?: boolean;
}

const cutSize: Record<ButtonSize, number> = { sm: 8, md: 12, lg: 14 };

const variantStyles: Record<
  ButtonVariant,
  React.CSSProperties
> = {
  "red-solid": { background: "var(--accent-primary)", color: "#fff", border: "none" },
  "white-solid": { background: "var(--foreground)", color: "var(--background)", border: "none" },
  "red-ghost": {
    background: "transparent",
    color: "var(--accent-primary)",
    border: "1px solid var(--accent-primary)",
  },
  "green-solid": { background: "var(--stock-down)", color: "#fff", border: "none" },
  "cyan-ghost": {
    background: "transparent",
    color: "var(--accent-cyan)",
    border: "1px solid var(--accent-cyan)",
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
  type = "button",
  disabled = false,
}: ClippedButtonProps) {
  const c = cutSize[size];

  return (
    <button
      type={type}
      onClick={onClick}
      disabled={disabled}
      className={`${sizeClasses[size]} font-semibold transition-all duration-200 active:scale-95 hover:brightness-110 ${className}`}
      style={{
        ...variantStyles[variant],
        clipPath: `polygon(0 0, calc(100% - ${c}px) 0, 100% ${c}px, 100% 100%, ${c}px 100%, 0 calc(100% - ${c}px))`,
        cursor: disabled ? "not-allowed" : "pointer",
        opacity: disabled ? 0.5 : 1,
        outline: "none",
      }}
      onFocus={(e) => {
        e.currentTarget.style.boxShadow = "0 0 0 2px var(--background), 0 0 0 4px var(--accent-cyan)";
      }}
      onBlur={(e) => {
        e.currentTarget.style.boxShadow = "none";
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
  up: { arrow: "\u25B2", color: "var(--stock-up)" },
  down: { arrow: "\u25BC", color: "var(--stock-down)" },
  flat: { arrow: "\u2014", color: "var(--text-muted)" },
};

export function KpiCard({ label, value, delta, direction }: KpiCardProps) {
  const { arrow, color } = directionConfig[direction];

  return (
    <div
      className="p-3 lg:p-5"
      style={glassStyle}
    >
      <div
        style={{
          fontSize: 11,
          fontWeight: 700,
          textTransform: "uppercase",
          letterSpacing: "0.05em",
          color: "var(--text-secondary)",
          marginBottom: 4,
        }}
      >
        {label}
      </div>
      <div
        className="text-[20px] lg:text-[32px]"
        style={{
          fontWeight: 600,
          color: "var(--foreground)",
          fontVariantNumeric: "tabular-nums",
          lineHeight: 1.1,
          marginBottom: 4,
          overflow: "hidden",
          textOverflow: "ellipsis",
        }}
      >
        {value}
      </div>
      <div className="text-[12px] lg:text-[13px]" style={{ fontWeight: 500, color }}>
        {arrow} {delta}
      </div>
    </div>
  );
}
