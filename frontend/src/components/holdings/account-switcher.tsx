"use client";

/**
 * AccountSwitcher — horizontal tab strip for filtering holdings by
 * account. The "All accounts" sentinel uses `null` so callers can
 * distinguish from "I haven't picked yet" (undefined) vs "explicitly
 * everything" (null).
 *
 * STRATOS treatment:
 *   - Selected tab → bold + var(--accent-cyan) text + cyan underline.
 *   - Unselected → var(--text-muted), hover var(--card-hover).
 *   - Horizontally scrollable, scrollbar styled by globals.css.
 */
import React, { useRef } from "react";
import { Badge } from "@/components/ui/badge";
import { type HoldingAccount } from "./types";

export interface AccountSwitcherProps {
  accounts: HoldingAccount[];
  /** null sentinel = "All accounts" tab is active. */
  selectedAccountId: number | null;
  onSelect: (accountId: number | null) => void;
  loading?: boolean;
}

interface TabButtonProps {
  active: boolean;
  onClick: () => void;
  children: React.ReactNode;
}

const baseTabStyle: React.CSSProperties = {
  position: "relative",
  display: "inline-flex",
  alignItems: "center",
  gap: 8,
  padding: "10px 16px",
  background: "transparent",
  border: "none",
  borderBottom: "2px solid transparent",
  fontFamily: "inherit",
  fontSize: 13,
  cursor: "pointer",
  whiteSpace: "nowrap",
  transition: "color 0.12s, background 0.12s, border-color 0.12s",
};

function TabButton({ active, onClick, children }: TabButtonProps) {
  return (
    <button
      type="button"
      onClick={onClick}
      style={{
        ...baseTabStyle,
        color: active ? "var(--accent-cyan)" : "var(--text-muted)",
        fontWeight: active ? 700 : 500,
        borderBottomColor: active ? "var(--accent-cyan)" : "transparent",
      }}
      onMouseEnter={(e) => {
        if (!active) e.currentTarget.style.background = "var(--card-hover)";
      }}
      onMouseLeave={(e) => {
        if (!active) e.currentTarget.style.background = "transparent";
      }}
      aria-pressed={active}
    >
      {children}
    </button>
  );
}

/* ------------------------------------------------------------------ */
/*  Skeleton tab (loading)                                             */
/* ------------------------------------------------------------------ */

function SkeletonTab({ width }: { width: number }) {
  return (
    <div
      style={{
        height: 38,
        width,
        margin: "0 4px",
        background: "var(--card-hover)",
      }}
    />
  );
}

/* ------------------------------------------------------------------ */
/*  Main                                                               */
/* ------------------------------------------------------------------ */

export function AccountSwitcher({
  accounts,
  selectedAccountId,
  onSelect,
  loading = false,
}: AccountSwitcherProps) {
  const scrollRef = useRef<HTMLDivElement>(null);

  if (loading) {
    return (
      <div
        style={{
          display: "flex",
          alignItems: "center",
          gap: 0,
          borderBottom: "1px solid var(--border-color)",
          padding: "0 4px",
        }}
      >
        <SkeletonTab width={100} />
        <SkeletonTab width={140} />
        <SkeletonTab width={120} />
      </div>
    );
  }

  return (
    <div
      ref={scrollRef}
      style={{
        display: "flex",
        alignItems: "stretch",
        overflowX: "auto",
        overflowY: "hidden",
        borderBottom: "1px solid var(--border-color)",
        scrollbarWidth: "thin",
      }}
      role="tablist"
      aria-label="帳戶切換"
    >
      <TabButton
        active={selectedAccountId === null}
        onClick={() => onSelect(null)}
      >
        <span>全部帳戶</span>
        <span
          style={{
            fontSize: 11,
            color: "var(--text-muted)",
            fontVariantNumeric: "tabular-nums",
          }}
        >
          ({accounts.length})
        </span>
      </TabButton>

      {accounts.map((acc) => (
        <TabButton
          key={acc.id}
          active={selectedAccountId === acc.id}
          onClick={() => onSelect(acc.id)}
        >
          <span>{acc.name}</span>
          {acc.broker && (
            <Badge variant="default" className="text-[10px]">
              {acc.broker}
            </Badge>
          )}
        </TabButton>
      ))}
    </div>
  );
}
