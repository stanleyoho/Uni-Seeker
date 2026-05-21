"use client";

/**
 * BulkActionsBar — floating action bar shown when one or more
 * holdings rows are selected.
 *
 * UX rules:
 *   - Fixed at bottom-center of viewport, slides up on mount.
 *   - Hidden entirely when selectedCount === 0 (component returns null,
 *     so the parent never has to gate the render manually).
 *   - Export button greys out when no handler is provided
 *     (Phase 4+ feature stub friendly).
 *   - Keyboard: `Escape` clears selection (a11y nicety).
 */
import React, { useEffect } from "react";
import { ClippedButton } from "@/components/stratos/primitives";

export interface BulkActionsBarProps {
  selectedCount: number;
  onClearSelection: () => void;
  onDeleteSelected: () => void;
  /** Optional — disables the Export button when omitted. */
  onExport?: () => void;
}

const containerStyle: React.CSSProperties = {
  position: "fixed",
  left: "50%",
  bottom: 24,
  transform: "translateX(-50%)",
  zIndex: 50,
  display: "flex",
  alignItems: "center",
  gap: 12,
  padding: "10px 16px",
  background: "var(--glass-bg)",
  backdropFilter: "var(--glass-blur)",
  WebkitBackdropFilter: "var(--glass-blur)",
  border: "1px solid var(--accent-cyan)",
  backgroundImage: "var(--glass-gradient)",
  boxShadow:
    "0 0 0 1px rgba(0,229,255,0.15), 0 12px 32px rgba(0,0,0,0.5), inset 0 1px 0 rgba(255,255,255,0.08)",
  borderRadius: "var(--glass-radius, 0)",
  animation: "holdings-bulk-slide-up 0.18s ease-out",
};

const countStyle: React.CSSProperties = {
  fontSize: 13,
  fontWeight: 700,
  color: "var(--accent-cyan)",
  fontVariantNumeric: "tabular-nums",
  paddingRight: 8,
  borderRight: "1px solid var(--border-color)",
  marginRight: 4,
  letterSpacing: "0.02em",
};

export function BulkActionsBar({
  selectedCount,
  onClearSelection,
  onDeleteSelected,
  onExport,
}: BulkActionsBarProps) {
  // Esc clears selection — handled here so any host page benefits.
  useEffect(() => {
    if (selectedCount === 0) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClearSelection();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [selectedCount, onClearSelection]);

  if (selectedCount === 0) return null;

  return (
    <>
      {/* keyframes injected inline so the file is fully self-contained */}
      <style>{`
        @keyframes holdings-bulk-slide-up {
          from { opacity: 0; transform: translate(-50%, 16px); }
          to   { opacity: 1; transform: translate(-50%, 0); }
        }
      `}</style>

      <div
        style={containerStyle}
        role="toolbar"
        aria-label="批次操作"
      >
        <span style={countStyle}>{selectedCount} selected</span>

        <ClippedButton
          variant="red-ghost"
          size="sm"
          onClick={onDeleteSelected}
        >
          刪除
        </ClippedButton>

        <ClippedButton
          variant="cyan-ghost"
          size="sm"
          onClick={onExport ?? (() => {})}
          disabled={!onExport}
        >
          匯出 CSV
        </ClippedButton>

        <ClippedButton
          variant="white-solid"
          size="sm"
          onClick={onClearSelection}
        >
          取消選取
        </ClippedButton>
      </div>
    </>
  );
}
