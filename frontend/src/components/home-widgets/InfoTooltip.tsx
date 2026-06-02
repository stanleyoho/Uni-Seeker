"use client";

/**
 * InfoTooltip — small Ⓘ icon that reveals a popover on hover / focus.
 *
 * Keyboard-accessible (tabbable, opens on focus). Mounts above the tile so
 * the popover never clips inside the home grid's overflow:hidden context.
 * Positioning is CSS-only (no portal needed for a 1-line label).
 */

import React, { useId, useRef, useState } from "react";

interface InfoTooltipProps {
  label: string;
  /** Optional aria-label override (defaults to "說明"). */
  ariaLabel?: string;
}

export function InfoTooltip({ label, ariaLabel = "說明" }: InfoTooltipProps) {
  const id = useId();
  const [open, setOpen] = useState(false);
  const closeTimer = useRef<ReturnType<typeof setTimeout> | null>(null);

  const show = () => {
    if (closeTimer.current) clearTimeout(closeTimer.current);
    setOpen(true);
  };
  // Tiny close delay so hover from icon → bubble doesn't immediately dismiss.
  const hide = () => {
    closeTimer.current = setTimeout(() => setOpen(false), 80);
  };

  return (
    <span
      style={{ position: "relative", display: "inline-flex" }}
      onMouseEnter={show}
      onMouseLeave={hide}
      onFocus={show}
      onBlur={hide}
    >
      <button
        type="button"
        aria-label={ariaLabel}
        aria-describedby={open ? id : undefined}
        tabIndex={0}
        style={{
          background: "transparent",
          border: "none",
          padding: 0,
          cursor: "help",
          color: "var(--text-muted, #9CA3AF)",
          fontSize: 11,
          lineHeight: 1,
          display: "inline-flex",
          alignItems: "center",
          justifyContent: "center",
          width: 14,
          height: 14,
          borderRadius: "50%",
        }}
      >
        {/* Use an outlined "i" glyph rather than an emoji to keep the
            terminal aesthetic. */}
        <svg
          width="11"
          height="11"
          viewBox="0 0 12 12"
          fill="none"
          aria-hidden="true"
        >
          <circle cx="6" cy="6" r="5" stroke="currentColor" strokeWidth="1" />
          <rect x="5.5" y="5" width="1" height="3.5" fill="currentColor" />
          <rect x="5.5" y="3" width="1" height="1" fill="currentColor" />
        </svg>
      </button>
      {open && (
        <span
          role="tooltip"
          id={id}
          style={{
            position: "absolute",
            top: "calc(100% + 6px)",
            right: 0,
            zIndex: 30,
            padding: "8px 10px",
            minWidth: 180,
            maxWidth: 260,
            fontSize: 11,
            lineHeight: 1.4,
            color: "var(--text-secondary, #cbd5e1)",
            background: "var(--background, #0b0b10)",
            border: "1px solid var(--border-color, rgba(255,255,255,0.12))",
            boxShadow: "0 8px 24px rgba(0,0,0,0.35)",
            borderRadius: "var(--glass-radius, 0)",
            whiteSpace: "normal",
            pointerEvents: "auto",
          }}
        >
          {label}
        </span>
      )}
    </span>
  );
}
