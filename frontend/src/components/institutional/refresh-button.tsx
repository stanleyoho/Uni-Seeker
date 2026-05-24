"use client";

/**
 * Refresh Button — on-demand 13F fetch from SEC EDGAR.
 *
 * Phase 2 wraps the Pro-only `POST /filers/{id}/refresh` endpoint behind
 * a STRATOS ClippedButton. Click flow:
 *
 *   1. Disable + flip label to "REFRESHING..." while the mutation runs.
 *   2. On success, show a transient toast `filings_added / holdings_added`
 *      for ~4s. The hook handles cache invalidation.
 *   3. On 429 `f13_refresh_in_flight` show "另一個 refresh 進行中，請稍候".
 *      On 403 surface a tier upsell. Other errors fall through.
 *
 * The toast renders inside this component (no external toast provider in
 * the project yet); position is absolute below the button.
 */

import { useEffect, useState } from "react";
import { ClippedButton } from "@/components/stratos/primitives";
import { useRefreshFiler } from "@/hooks/use-institutional";
import { ApiError } from "@/lib/api-client";

export interface RefreshButtonProps {
  filerId: number;
  /** How many quarters back to ingest. Defaults to 4. */
  maxQuarters?: number;
  disabled?: boolean;
}

interface ToastState {
  kind: "success" | "error";
  text: string;
}

function mapRefreshError(err: unknown): string {
  if (!(err instanceof ApiError)) {
    return err instanceof Error ? err.message : "Refresh 失敗，請稍後再試";
  }
  const { status, code, message } = err;
  if (status === 429 || code === "f13_refresh_in_flight") {
    return "另一個 refresh 進行中，請稍候";
  }
  if (status === 403) {
    if (code?.startsWith("feature_unavailable:institutional_realtime_refresh")) {
      return "升級到 Pro 解鎖即時 refresh";
    }
    return message || "權限不足";
  }
  if (status === 502 || code === "f13_edgar_error") {
    return "SEC EDGAR 暫時無法存取";
  }
  if (status === 404) return "找不到此 filer";
  return message || "Refresh 失敗";
}

export function RefreshButton({
  filerId,
  maxQuarters = 4,
  disabled = false,
}: RefreshButtonProps) {
  const refresh = useRefreshFiler();
  const [toast, setToast] = useState<ToastState | null>(null);

  // Auto-dismiss toast after 4s
  useEffect(() => {
    if (!toast) return;
    const id = setTimeout(() => setToast(null), 4000);
    return () => clearTimeout(id);
  }, [toast]);

  async function handleClick() {
    setToast(null);
    try {
      const res = await refresh.mutateAsync({ filerId, maxQuarters });
      if (res.filings_added === 0 && res.holdings_added === 0) {
        setToast({
          kind: "success",
          text: "已是最新 — SEC EDGAR 無新 filing",
        });
      } else {
        setToast({
          kind: "success",
          text: `已更新 ${res.filings_added} 份 filing / ${res.holdings_added} 筆持倉`,
        });
      }
    } catch (e) {
      setToast({ kind: "error", text: mapRefreshError(e) });
    }
  }

  return (
    <div style={{ position: "relative", display: "inline-block" }}>
      <ClippedButton
        variant="cyan-ghost"
        size="md"
        onClick={handleClick}
        disabled={disabled || refresh.isPending}
      >
        {refresh.isPending ? "REFRESHING..." : "↻ Refresh"}
      </ClippedButton>
      {toast && (
        <div
          role="status"
          style={{
            position: "absolute",
            top: "calc(100% + 8px)",
            right: 0,
            zIndex: 50,
            minWidth: 260,
            padding: "10px 14px",
            fontSize: 12,
            fontWeight: 600,
            color: "#fff",
            background:
              toast.kind === "success"
                ? "var(--stock-down)"
                : "var(--accent-primary)",
            boxShadow: "var(--glass-shadow)",
            letterSpacing: "0.02em",
          }}
        >
          {toast.text}
        </div>
      )}
    </div>
  );
}
