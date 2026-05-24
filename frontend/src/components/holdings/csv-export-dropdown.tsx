"use client";

/**
 * CSV Export Dropdown — Phase 4 tax-export hook.
 *
 * Surfaces a single ClippedButton ("匯出 CSV ▾") that pops a four-option
 * menu (Trades / Positions / Dividends / Summary). Each option triggers
 * a Blob download via `downloadBlob`, bypassing JSON parsing.
 *
 * Backend wire contract reminders:
 *   - Endpoints under `/holdings/exports/*.csv` — all GET, all return
 *     `text/csv; charset=utf-8` with a UTF-8 BOM prefix for Excel.
 *   - Tier gate (`tax_export`) is PRO only. FREE / BASIC users see
 *     `403 feature_unavailable:tax_export`. We surface a zh-TW toast
 *     in that case rather than crashing.
 *   - Filters: `account_id`, `date_from`, `date_to` are query params.
 *     This component only forwards `selectedAccountId` for now — date
 *     range can be wired in later without changing the API shape.
 */

import { useEffect, useRef, useState } from "react";
import { ClippedButton } from "@/components/stratos/primitives";
import {
  ApiError,
  downloadBlob,
  exportHoldingsDividends,
  exportHoldingsPositions,
  exportHoldingsSummary,
  exportHoldingsTrades,
} from "@/lib/api-client";

export interface CsvExportDropdownProps {
  /**
   * Optional account scope. When provided the export endpoints receive
   * `?account_id=` and return rows for that account only. When null
   * we send no filter and the backend aggregates across every owned
   * account.
   */
  selectedAccountId: number | null;
}

type ExportType = "trades" | "positions" | "dividends" | "summary";

interface MenuOption {
  type: ExportType;
  label: string;
  hint: string;
}

const MENU_OPTIONS: MenuOption[] = [
  { type: "trades", label: "交易紀錄", hint: "Trades CSV" },
  { type: "positions", label: "持倉部位", hint: "Positions CSV" },
  { type: "dividends", label: "股利紀錄", hint: "Dividends CSV" },
  { type: "summary", label: "投組摘要", hint: "Summary CSV" },
];

/**
 * Map ApiError → user-facing zh-TW message.
 *
 * Mirrors the pattern in `add-trade-modal.tsx`. `tax_export` is the
 * only feature this dropdown gates on, so the 403 branch is narrow.
 */
function mapExportError(err: unknown): string {
  if (!(err instanceof ApiError)) {
    return err instanceof Error ? err.message : "下載失敗，請稍後再試";
  }
  const { status, code, message } = err;
  if (status === 403) {
    if (
      code?.startsWith("feature_unavailable") ||
      message.includes("feature_unavailable:tax_export")
    ) {
      return "升級 Pro 解鎖 CSV 匯出";
    }
    return message || "權限不足";
  }
  if (status === 408 || code === "TIMEOUT") return "下載逾時，請稍後再試";
  return message || "下載失敗";
}

/** Date slug used in default filenames — keeps download history sortable. */
function todaySlug(): string {
  return new Date().toISOString().slice(0, 10);
}

export function CsvExportDropdown({ selectedAccountId }: CsvExportDropdownProps) {
  const [open, setOpen] = useState(false);
  const [pending, setPending] = useState<ExportType | null>(null);
  const [error, setError] = useState<string | null>(null);
  const containerRef = useRef<HTMLDivElement | null>(null);

  /* Close on outside click + Escape — table-stakes for any dropdown */
  useEffect(() => {
    if (!open) return;
    function onClickOutside(e: MouseEvent) {
      if (!containerRef.current?.contains(e.target as Node)) setOpen(false);
    }
    function onKey(e: KeyboardEvent) {
      if (e.key === "Escape") setOpen(false);
    }
    document.addEventListener("mousedown", onClickOutside);
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("mousedown", onClickOutside);
      document.removeEventListener("keydown", onKey);
    };
  }, [open]);

  /* Clear any old error when the user re-opens the menu */
  useEffect(() => {
    if (open) setError(null);
  }, [open]);

  async function handleExport(type: ExportType) {
    setPending(type);
    setError(null);
    try {
      const accountOpt =
        selectedAccountId !== null ? { accountId: selectedAccountId } : {};
      let blob: Blob;
      switch (type) {
        case "trades":
          blob = await exportHoldingsTrades(accountOpt);
          break;
        case "positions":
          blob = await exportHoldingsPositions(accountOpt);
          break;
        case "dividends":
          blob = await exportHoldingsDividends(accountOpt);
          break;
        case "summary":
          blob = await exportHoldingsSummary();
          break;
      }
      downloadBlob(blob, `${type}-${todaySlug()}.csv`);
      setOpen(false);
    } catch (e) {
      setError(mapExportError(e));
    } finally {
      setPending(null);
    }
  }

  return (
    <div
      ref={containerRef}
      style={{ position: "relative", display: "inline-block" }}
    >
      <ClippedButton
        variant="cyan-ghost"
        size="md"
        onClick={() => setOpen((v) => !v)}
        disabled={pending !== null}
      >
        {pending !== null ? "下載中…" : "匯出 CSV ▾"}
      </ClippedButton>

      {open && (
        <div
          role="menu"
          aria-label="CSV 匯出選項"
          style={{
            position: "absolute",
            top: "calc(100% + 6px)",
            right: 0,
            minWidth: 220,
            background: "var(--glass-bg)",
            backgroundImage: "var(--glass-gradient)",
            border: "1px solid var(--border-color)",
            boxShadow: "var(--glass-shadow)",
            zIndex: 50,
            padding: 6,
            display: "flex",
            flexDirection: "column",
            gap: 2,
          }}
        >
          {MENU_OPTIONS.map((opt) => {
            const isLoading = pending === opt.type;
            return (
              <button
                key={opt.type}
                role="menuitem"
                onClick={() => handleExport(opt.type)}
                disabled={pending !== null}
                style={{
                  display: "flex",
                  justifyContent: "space-between",
                  alignItems: "center",
                  padding: "10px 12px",
                  background: "transparent",
                  border: "none",
                  cursor: pending !== null ? "not-allowed" : "pointer",
                  textAlign: "left",
                  color: "var(--foreground)",
                  fontSize: 12,
                  fontWeight: 600,
                  letterSpacing: "0.02em",
                  transition: "background 0.15s",
                }}
                onMouseEnter={(e) => {
                  if (pending === null) {
                    e.currentTarget.style.background =
                      "var(--bg-secondary)";
                  }
                }}
                onMouseLeave={(e) => {
                  e.currentTarget.style.background = "transparent";
                }}
              >
                <span>{opt.label}</span>
                <span
                  style={{
                    color: "var(--text-muted)",
                    fontSize: 10,
                    fontFamily: "monospace",
                    letterSpacing: "0.05em",
                  }}
                >
                  {isLoading ? "…" : opt.hint}
                </span>
              </button>
            );
          })}

          {error && (
            <div
              role="alert"
              style={{
                marginTop: 4,
                padding: "8px 10px",
                background: "var(--accent-primary)",
                color: "#fff",
                fontSize: 11,
                fontWeight: 600,
                letterSpacing: "0.02em",
              }}
            >
              {error}
            </div>
          )}
        </div>
      )}
    </div>
  );
}
