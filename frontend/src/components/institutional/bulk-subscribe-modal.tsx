"use client";

/**
 * Bulk Subscribe Modal — paste a list of CIKs + names to subscribe in
 * one atomic batch.
 *
 * UX flow:
 *   1. User pastes lines into a textarea. Each line is `CIK[, name]` or
 *      just `CIK` (name is optional — backend resolves via EDGAR).
 *   2. Client-side: split on newlines, dedupe, validate CIK = digits,
 *      cap at 20 rows.
 *   3. Submit → `useBulkSubscribeFilers`. Tier-quota blocks the whole
 *      batch (403); per-row issues land in the response envelope's
 *      `errors[]`.
 *   4. Show a result summary: subscribed N / skipped N / failed N.
 *
 * Atomic contract: a 403 `limit_exceeded` aborts the whole batch with
 * a banner — nothing was inserted. Once the user reduces the count and
 * resubmits, partial-success can still occur (some rows in `errors[]`)
 * but those rows never inserted either, so the user can re-paste them
 * after fixing.
 */

import { useMemo, useState } from "react";
import { ClippedButton } from "@/components/stratos/primitives";
import { useBulkSubscribeFilers } from "@/hooks/use-institutional";
import {
  ApiError,
  type F13BulkSubscribeRequestItem,
  type F13BulkSubscribeResponse,
} from "@/lib/api-client";

interface BulkSubscribeModalProps {
  onClose: () => void;
  /** Called after a successful submit; receives the envelope. */
  onSuccess?: (response: F13BulkSubscribeResponse) => void;
}

const BULK_MAX_PER_CALL = 20;

const inputCls =
  "w-full px-3 py-2 bg-[var(--bg-secondary)] border border-[var(--border-subtle)] text-sm text-[var(--foreground)] placeholder-[var(--text-muted)] focus:border-[var(--accent-cyan)] outline-none";

const labelCls =
  "text-[10px] font-bold uppercase tracking-[0.1em] text-[var(--text-muted)] mb-1 block";

/**
 * Parse a textarea blob into items. One line per row, format:
 *   `0001234567`              — CIK only (backend auto-resolves name)
 *   `0001234567, Berkshire`   — CIK + display name
 *   `0001234567 Berkshire`    — same, whitespace-separated
 *
 * Empty lines + comments (#) are skipped. CIKs are NOT normalised here
 * because the backend pads to 10 digits canonical; we just verify the
 * input is digits-only.
 */
function parseRows(text: string): {
  items: F13BulkSubscribeRequestItem[];
  invalidLines: { line: string; lineNum: number }[];
} {
  const lines = text.split(/\r?\n/);
  const items: F13BulkSubscribeRequestItem[] = [];
  const invalidLines: { line: string; lineNum: number }[] = [];
  const seen = new Set<string>();

  lines.forEach((raw, idx) => {
    const line = raw.trim();
    if (!line || line.startsWith("#")) return;

    // Split on the first comma OR run of whitespace.
    const commaIdx = line.indexOf(",");
    let cikPart: string;
    let namePart: string | undefined;
    if (commaIdx >= 0) {
      cikPart = line.slice(0, commaIdx).trim();
      namePart = line.slice(commaIdx + 1).trim() || undefined;
    } else {
      const wsIdx = line.search(/\s/);
      if (wsIdx >= 0) {
        cikPart = line.slice(0, wsIdx).trim();
        namePart = line.slice(wsIdx + 1).trim() || undefined;
      } else {
        cikPart = line;
        namePart = undefined;
      }
    }

    // Strip any non-digit chars for validation but submit the original
    // (backend's _pad_cik strips again — defence in depth).
    const digits = cikPart.replace(/\D/g, "");
    if (!digits) {
      invalidLines.push({ line, lineNum: idx + 1 });
      return;
    }

    // Request-level dedupe (the backend does this too but flagging here
    // gives faster UX).
    const normalised = digits.padStart(10, "0");
    if (seen.has(normalised)) return;
    seen.add(normalised);

    items.push({ cik: cikPart, name: namePart });
  });

  return { items, invalidLines };
}

function mapBulkError(err: unknown): string {
  if (!(err instanceof ApiError)) {
    return err instanceof Error ? err.message : "批次訂閱失敗，請稍後再試";
  }
  const { status, code, message } = err;
  if (status === 403) {
    if (code?.startsWith("limit_exceeded:max_tracked_filers")) {
      return "批次超過 tier 上限，請減少數量或升級 Pro";
    }
    if (code?.startsWith("feature_unavailable")) {
      return "升級到 Pro 解鎖此功能";
    }
    return message || "權限不足";
  }
  if (status === 422) return "格式錯誤：CIK 必須是數字、每批次 1-20 筆";
  if (status === 409) return "批次中有 filer 已被訂閱（race condition），請重試";
  if (status === 502) return "SEC EDGAR 暫時無法存取，請稍候重試";
  return message || "批次訂閱失敗";
}

export function BulkSubscribeModal({
  onClose,
  onSuccess,
}: BulkSubscribeModalProps) {
  const [text, setText] = useState("");
  const [bannerError, setBannerError] = useState<string | null>(null);
  const [result, setResult] = useState<F13BulkSubscribeResponse | null>(null);

  const mutation = useBulkSubscribeFilers();
  const isPending = mutation.isPending;

  const { items, invalidLines } = useMemo(() => parseRows(text), [text]);
  const overLimit = items.length > BULK_MAX_PER_CALL;
  const canSubmit = items.length > 0 && !overLimit && !isPending;

  async function handleSubmit() {
    setBannerError(null);
    setResult(null);
    try {
      const resp = await mutation.mutateAsync(items);
      setResult(resp);
      onSuccess?.(resp);
      // Auto-close only when everything succeeded cleanly (no errors,
      // no skipped duplicates worth showing). Otherwise leave open so
      // the user reads the summary.
      if (resp.errors.length === 0 && resp.skipped_duplicates.length === 0) {
        onClose();
      }
    } catch (e) {
      setBannerError(mapBulkError(e));
    }
  }

  return (
    <div
      style={{
        position: "fixed",
        inset: 0,
        background: "rgba(0,0,0,0.7)",
        backdropFilter: "blur(4px)",
        zIndex: 1000,
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        padding: 16,
      }}
      onClick={(e) => e.target === e.currentTarget && !isPending && onClose()}
    >
      <div
        style={{
          background: "var(--glass-bg)",
          border: "1px solid var(--border-color)",
          width: "100%",
          maxWidth: 640,
          maxHeight: "90vh",
          display: "flex",
          flexDirection: "column",
          padding: 24,
          boxShadow: "var(--glass-shadow)",
          backgroundImage: "var(--glass-gradient)",
        }}
      >
        {/* Header */}
        <div
          style={{
            display: "flex",
            justifyContent: "space-between",
            alignItems: "center",
            marginBottom: 16,
          }}
        >
          <span
            style={{
              fontSize: 14,
              fontWeight: 700,
              color: "var(--foreground)",
              letterSpacing: "-0.04em",
              textTransform: "uppercase",
            }}
          >
            批次訂閱機構 / 基金
          </span>
          <button
            onClick={onClose}
            disabled={isPending}
            aria-label="關閉"
            style={{
              color: "var(--text-muted)",
              background: "none",
              border: "none",
              cursor: isPending ? "not-allowed" : "pointer",
              fontSize: 20,
              lineHeight: 1,
              padding: 4,
            }}
          >
            ×
          </button>
        </div>

        {/* Textarea */}
        <div>
          <label className={labelCls}>
            一行一筆：`CIK` 或 `CIK, 名稱` (最多 {BULK_MAX_PER_CALL} 筆)
          </label>
          <textarea
            className={inputCls}
            placeholder={
              "例如：\n0001067983, Berkshire Hathaway\n0001037389, Renaissance Tech\n0001350694"
            }
            value={text}
            onChange={(e) => {
              setText(e.target.value);
              setBannerError(null);
              setResult(null);
            }}
            rows={9}
            disabled={isPending}
            style={{
              fontFamily: "monospace",
              fontSize: 12,
              resize: "vertical",
              minHeight: 160,
            }}
          />
          <p
            style={{
              fontSize: 10,
              color: overLimit
                ? "var(--stock-down)"
                : "var(--text-muted)",
              marginTop: 6,
            }}
          >
            {overLimit
              ? `超過上限：${items.length} > ${BULK_MAX_PER_CALL}`
              : `${items.length} 筆已解析${
                  invalidLines.length > 0
                    ? ` · ${invalidLines.length} 筆格式錯誤`
                    : ""
                }`}
          </p>
        </div>

        {/* Banner error */}
        {bannerError && (
          <div
            role="alert"
            style={{
              marginTop: 12,
              fontSize: 12,
              color: "#fff",
              background: "var(--accent-primary)",
              padding: "8px 12px",
              fontWeight: 600,
            }}
          >
            {bannerError}
          </div>
        )}

        {/* Result summary */}
        {result && (
          <div
            style={{
              marginTop: 12,
              padding: "10px 12px",
              border: "1px solid var(--border-subtle)",
              background: "var(--bg-secondary)",
              fontSize: 12,
              color: "var(--foreground)",
              display: "flex",
              flexDirection: "column",
              gap: 6,
            }}
          >
            <div
              style={{ display: "flex", gap: 16, flexWrap: "wrap" }}
            >
              <span style={{ color: "var(--stock-up)" }}>
                成功 {result.subscribed.length}
              </span>
              <span style={{ color: "var(--text-muted)" }}>
                已在追蹤 {result.skipped_duplicates.length}
              </span>
              <span style={{ color: "var(--stock-down)" }}>
                失敗 {result.errors.length}
              </span>
            </div>
            {result.errors.length > 0 && (
              <ul
                style={{
                  margin: "6px 0 0",
                  paddingLeft: 16,
                  fontSize: 11,
                  color: "var(--text-muted)",
                  fontFamily: "monospace",
                  maxHeight: 120,
                  overflowY: "auto",
                }}
              >
                {result.errors.map((e) => (
                  <li key={e.cik}>
                    CIK {e.cik} — {e.reason}
                  </li>
                ))}
              </ul>
            )}
          </div>
        )}

        {/* Footer actions */}
        <div
          style={{
            display: "flex",
            justifyContent: "flex-end",
            gap: 8,
            marginTop: 16,
          }}
        >
          <ClippedButton
            variant="white-solid"
            size="md"
            onClick={onClose}
            disabled={isPending}
          >
            {result ? "完成" : "取消"}
          </ClippedButton>
          <ClippedButton
            variant="cyan-ghost"
            size="md"
            onClick={handleSubmit}
            disabled={!canSubmit}
          >
            {isPending ? "送出中..." : `訂閱 ${items.length} 筆`}
          </ClippedButton>
        </div>
      </div>
    </div>
  );
}
