"use client";

/**
 * PositionsEmptyState — shown when a user has zero holdings.
 * Encourages adding the first trade. CSV import is a Phase 4+ stub.
 */
import React from "react";
import { ClippedButton } from "@/components/stratos/primitives";

export interface PositionsEmptyStateProps {
  onAddTrade: () => void;
}

const wrapperStyle: React.CSSProperties = {
  display: "flex",
  flexDirection: "column",
  alignItems: "center",
  justifyContent: "center",
  padding: "56px 24px",
  gap: 16,
  textAlign: "center",
};

const iconStyle: React.CSSProperties = {
  width: 56,
  height: 56,
  display: "flex",
  alignItems: "center",
  justifyContent: "center",
  border: "1px dashed var(--border-color)",
  background: "var(--bg-secondary)",
  transform: "rotate(45deg)",
};

export function PositionsEmptyState({ onAddTrade }: PositionsEmptyStateProps) {
  return (
    <div style={wrapperStyle}>
      <div style={iconStyle}>
        <svg
          style={{ transform: "rotate(-45deg)", width: 22, height: 22 }}
          viewBox="0 0 24 24"
          fill="none"
          stroke="currentColor"
          strokeWidth={1.5}
          color="var(--text-muted)"
          aria-hidden="true"
        >
          <path strokeLinecap="round" strokeLinejoin="round" d="M12 4v16m8-8H4" />
        </svg>
      </div>

      <p
        style={{
          fontSize: 14,
          fontWeight: 700,
          color: "var(--foreground)",
          letterSpacing: "0.02em",
        }}
      >
        無持倉
      </p>

      <ClippedButton variant="red-solid" size="md" onClick={onAddTrade}>
        + 記錄交易
      </ClippedButton>

      <p style={{ fontSize: 11, color: "var(--text-muted)" }}>
        或從 CSV 匯入（Phase 4+）
      </p>
    </div>
  );
}
