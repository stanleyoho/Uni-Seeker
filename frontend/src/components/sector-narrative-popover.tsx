"use client";

/**
 * SectorNarrativePopover — Ⓘ icon that opens a popover with the
 * sector's industry-chain narrative + a "看完整供應鏈" link.
 *
 * Hand-rolled (no Radix dep) — the component fits in ~150 LOC, lives
 * inside a parent <Link> for the sector tile, and stops click
 * propagation so opening the popover doesn't navigate the tile.
 *
 * Accessibility:
 *   - icon is a real <button>, keyboard-focusable
 *   - aria-describedby + aria-expanded on the button
 *   - Esc dismisses; hover-out + blur close with a small delay so
 *     mouse-from-icon-to-bubble doesn't immediately collapse
 */

import React, { useEffect, useId, useRef, useState } from "react";
import Link from "next/link";

interface SectorNarrativePopoverProps {
  /** Full narrative text (~100-200 字 Chinese). */
  narrative: string;
  /** Sector display name (used in aria label). */
  sectorName: string;
  /** href for the "看完整供應鏈" CTA. */
  href: string;
  /** Optional aria-label override. */
  ariaLabel?: string;
  /** Anchor side; tiles in the bottom row look better with `top`. */
  side?: "top" | "bottom";
}

export function SectorNarrativePopover({
  narrative,
  sectorName,
  href,
  ariaLabel,
  side = "bottom",
}: SectorNarrativePopoverProps) {
  const id = useId();
  const [open, setOpen] = useState(false);
  const closeTimer = useRef<ReturnType<typeof setTimeout> | null>(null);

  const clearTimer = () => {
    if (closeTimer.current) {
      clearTimeout(closeTimer.current);
      closeTimer.current = null;
    }
  };
  const show = () => {
    clearTimer();
    setOpen(true);
  };
  const hide = () => {
    clearTimer();
    closeTimer.current = setTimeout(() => setOpen(false), 120);
  };

  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") setOpen(false);
    };
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [open]);

  const stop = (e: React.MouseEvent | React.PointerEvent) => {
    e.stopPropagation();
  };

  const popoverPos: React.CSSProperties =
    side === "top"
      ? { bottom: "calc(100% + 6px)", right: 0 }
      : { top: "calc(100% + 6px)", right: 0 };

  return (
    <span
      style={{ position: "relative", display: "inline-flex" }}
      onMouseEnter={show}
      onMouseLeave={hide}
      onFocus={show}
      onBlur={hide}
      onClick={stop}
    >
      <button
        type="button"
        aria-label={ariaLabel ?? `${sectorName} 產業說明`}
        aria-describedby={open ? id : undefined}
        aria-expanded={open}
        tabIndex={0}
        onClick={(e) => {
          stop(e);
          // Tap-to-toggle for touch devices where hover doesn't fire.
          setOpen((v) => !v);
        }}
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
          width: 16,
          height: 16,
          borderRadius: "50%",
        }}
      >
        <svg width="13" height="13" viewBox="0 0 12 12" fill="none" aria-hidden="true">
          <circle cx="6" cy="6" r="5" stroke="currentColor" strokeWidth="1" />
          <rect x="5.5" y="5" width="1" height="3.5" fill="currentColor" />
          <rect x="5.5" y="3" width="1" height="1" fill="currentColor" />
        </svg>
      </button>
      {open && (
        <span
          role="dialog"
          aria-label={`${sectorName} 產業鏈描述`}
          id={id}
          style={{
            position: "absolute",
            ...popoverPos,
            zIndex: 50,
            padding: "12px 14px",
            width: 320,
            maxWidth: "min(80vw, 360px)",
            fontSize: 12,
            lineHeight: 1.65,
            color: "var(--text-secondary, #cbd5e1)",
            background: "var(--background, #0b0b10)",
            border: "1px solid var(--border-color, rgba(255,255,255,0.12))",
            boxShadow: "0 8px 24px rgba(0,0,0,0.5)",
            borderRadius: "var(--glass-radius, 0)",
            whiteSpace: "normal",
            pointerEvents: "auto",
            textAlign: "left",
          }}
        >
          <div
            style={{
              fontSize: 10,
              fontWeight: 700,
              letterSpacing: "0.12em",
              textTransform: "uppercase",
              color: "var(--text-muted)",
              marginBottom: 6,
            }}
          >
            產業鏈描述
          </div>
          <p style={{ margin: 0, marginBottom: 10, color: "var(--foreground)" }}>{narrative}</p>
          <Link
            href={href}
            onClick={stop}
            style={{
              display: "inline-flex",
              alignItems: "center",
              gap: 4,
              fontSize: 11,
              fontWeight: 700,
              color: "var(--accent-cyan, #67e8f9)",
              textDecoration: "none",
              letterSpacing: "0.04em",
            }}
          >
            看完整供應鏈 →
          </Link>
        </span>
      )}
    </span>
  );
}
