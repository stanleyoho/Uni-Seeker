"use client";

/**
 * CSV Import Modal — Phase 4 broker import flow.
 *
 * Two-step flow:
 *   1. User selects account + drops a CSV file (or pastes text).
 *      Click "預覽" → dry_run=true → render parsed rows + errors.
 *   2. If errors == 0 → "確認匯入" button → dry_run=false commit.
 *      If errors > 0 → user must fix the CSV externally and re-paste.
 *
 * Backend wire contract reminders:
 *   - Raw text/csv body (NOT multipart) — see `importHoldingsCsv` for
 *     why.
 *   - Atomic: a commit with failed_rows > 0 means zero rows landed.
 *   - Tier gate: FREE/BASIC max_trades_per_month enforced as
 *     `limit_exceeded:max_trades_per_month` (403).
 */

import { useEffect, useMemo, useState } from "react";
import { ClippedButton } from "@/components/stratos/primitives";
import { useImportHoldingsCsv } from "@/hooks/use-holdings";
import {
  ApiError,
  type BrokerInfo,
  type HoldingAccount,
  type ImportResult,
  type ImportResultRow,
  listImportBrokers,
} from "@/lib/api-client";

interface CsvImportModalProps {
  accounts: HoldingAccount[];
  defaultAccountId?: number;
  onClose: () => void;
  onSuccess?: (result: ImportResult) => void;
}

const inputCls =
  "w-full px-3 py-2 bg-[var(--bg-secondary)] border border-[var(--border-subtle)] text-sm text-[var(--foreground)] placeholder-[var(--text-muted)] focus:border-[var(--accent-cyan)] outline-none tabular-nums";

const labelCls =
  "text-[10px] font-bold uppercase tracking-[0.1em] text-[var(--text-muted)] mb-1 block";

const HEADER_TEMPLATE =
  "trade_date,action,symbol,market,quantity,price,fee,tax,note";

/**
 * Map backend error codes → zh-TW labels rendered inside the per-row
 * error column. Anything we don't recognise falls through to the
 * raw snake_case identifier so unknown errors stay surfaced.
 */
const ROW_ERROR_LABELS: Record<string, string> = {
  invalid_action: "動作必須為 BUY 或 SELL",
  invalid_market: "市場代碼無效",
  invalid_quantity: "數量必須 > 0",
  invalid_price: "價格必須 > 0",
  invalid_fee: "手續費格式錯誤",
  invalid_tax: "稅額格式錯誤",
  invalid_trade_date: "日期格式錯誤 (需 ISO YYYY-MM-DD)",
  missing_symbol: "缺少標的代碼",
  dividend_actions_not_supported: "股利/拆股請改用股利匯入",
};

function labelForRowError(code: string | null | undefined): string {
  if (!code) return "";
  return ROW_ERROR_LABELS[code] ?? code;
}

function mapApiError(err: unknown): string {
  if (!(err instanceof ApiError)) {
    return err instanceof Error ? err.message : "匯入失敗，請稍後再試";
  }
  const { status, code, message } = err;
  if (status === 413 || code === "csv_too_large") return "檔案超過 1 MB 上限";
  if (status === 422) {
    if (code === "invalid_csv_format" || message.includes("invalid_csv_format")) {
      return "CSV 格式錯誤 — 請確認檔頭符合範本";
    }
    if (code === "insufficient_shares") return "持股不足 — 賣出列數量超過庫存";
    return message || "CSV 內容有誤";
  }
  if (status === 403) {
    if (code?.startsWith("limit_exceeded:max_trades_per_month")) {
      return "批次超過本月交易上限，請減少筆數或升級 Pro";
    }
    return "權限不足";
  }
  if (status === 404) return "帳戶不存在";
  if (status === 415) return "請上傳 CSV 檔（text/csv）";
  return message || "匯入失敗";
}

export function CsvImportModal({
  accounts,
  defaultAccountId,
  onClose,
  onSuccess,
}: CsvImportModalProps) {
  const initialAccount =
    accounts.find((a) => a.id === defaultAccountId) ?? accounts[0];

  const [accountId, setAccountId] = useState<number>(initialAccount?.id ?? 0);
  const [csvText, setCsvText] = useState("");
  const [filename, setFilename] = useState<string | null>(null);
  const [preview, setPreview] = useState<ImportResult | null>(null);
  const [bannerError, setBannerError] = useState<string | null>(null);
  // Round 10 — broker selection. Empty string = auto-detect (default).
  const [brokerKey, setBrokerKey] = useState<string>("");
  const [brokers, setBrokers] = useState<BrokerInfo[]>([]);
  const importMutation = useImportHoldingsCsv();

  // Fetch the broker registry once on modal mount. We don't gate the
  // UI on this — auto-detect (empty broker_key) still works even if
  // the list fetch fails.
  useEffect(() => {
    let cancelled = false;
    listImportBrokers()
      .then((list) => {
        if (!cancelled) setBrokers(list);
      })
      .catch(() => {
        // Non-fatal — user can still upload with auto-detect.
      });
    return () => {
      cancelled = true;
    };
  }, []);

  const isPending = importMutation.isPending;
  const canPreview = accountId > 0 && csvText.trim().length > 0 && !isPending;
  const canCommit =
    !!preview &&
    preview.dry_run &&
    preview.failed_rows === 0 &&
    preview.parsed_rows > 0 &&
    !isPending;

  // Successful row count to render in the summary line — derived from
  // preview state. Memo avoids the `?.` chain inside JSX.
  const summaryCounts = useMemo(() => {
    if (!preview) return null;
    return {
      parsed: preview.parsed_rows,
      ok: preview.successful_rows,
      failed: preview.failed_rows,
    };
  }, [preview]);

  function handleFile(file: File | null) {
    if (!file) return;
    setFilename(file.name);
    setBannerError(null);
    setPreview(null);
    const reader = new FileReader();
    reader.onload = () => {
      const text = String(reader.result ?? "");
      setCsvText(text);
    };
    reader.onerror = () => {
      setBannerError("檔案讀取失敗");
    };
    reader.readAsText(file, "utf-8");
  }

  async function runImport(dryRun: boolean) {
    setBannerError(null);
    try {
      const result = await importMutation.mutateAsync({
        accountId,
        file: csvText,
        dryRun,
        brokerKey: brokerKey || null,
      });
      setPreview(result);
      // On a committed success surface the result upward so the parent
      // page can close the modal / refresh its own state.
      if (!dryRun && result.failed_rows === 0) {
        onSuccess?.(result);
      }
    } catch (err) {
      setBannerError(mapApiError(err));
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
          maxWidth: 720,
          maxHeight: "90vh",
          overflowY: "auto",
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
            marginBottom: 20,
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
            CSV 匯入交易
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

        <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
          {/* Account selector */}
          <div>
            <label className={labelCls}>匯入到帳戶</label>
            <select
              className={inputCls}
              value={accountId}
              onChange={(e) => {
                setAccountId(Number(e.target.value));
                setPreview(null);
              }}
              disabled={isPending}
            >
              {accounts.length === 0 && <option value={0}>—</option>}
              {accounts.map((acc) => (
                <option key={acc.id} value={acc.id}>
                  {acc.name} ({acc.currency})
                </option>
              ))}
            </select>
          </div>

          {/* Broker selector — Round 10. Empty value = auto-detect. */}
          <div>
            <label className={labelCls}>券商格式（留空 = 自動偵測）</label>
            <select
              className={inputCls}
              value={brokerKey}
              onChange={(e) => {
                setBrokerKey(e.target.value);
                setPreview(null);
              }}
              disabled={isPending}
            >
              <option value="">自動偵測</option>
              {brokers.map((b) => (
                <option key={b.broker_key} value={b.broker_key}>
                  {b.display_name}
                </option>
              ))}
            </select>
          </div>

          {/* File drop / paste */}
          <div>
            <label className={labelCls}>CSV 檔案 / 貼上內容</label>
            <div
              style={{
                border: "1px dashed var(--border-color)",
                padding: 12,
                marginBottom: 8,
                fontSize: 11,
                color: "var(--text-muted)",
                fontFamily: "monospace",
                overflowX: "auto",
                whiteSpace: "nowrap",
              }}
            >
              範本檔頭：<span style={{ color: "var(--foreground)" }}>{HEADER_TEMPLATE}</span>
            </div>
            <input
              type="file"
              accept=".csv,text/csv,text/plain"
              onChange={(e) => handleFile(e.target.files?.[0] ?? null)}
              disabled={isPending}
              style={{
                fontSize: 12,
                color: "var(--text-muted)",
                marginBottom: 8,
              }}
            />
            {filename && (
              <div
                style={{
                  fontSize: 11,
                  color: "var(--accent-cyan)",
                  marginBottom: 8,
                }}
              >
                已選：{filename}
              </div>
            )}
            <textarea
              className={inputCls}
              style={{
                minHeight: 120,
                fontFamily: "monospace",
                fontSize: 11,
                whiteSpace: "pre",
              }}
              placeholder={`${HEADER_TEMPLATE}\n2026-05-01,BUY,2330,TW_TWSE,100,500,28,0,`}
              value={csvText}
              onChange={(e) => {
                setCsvText(e.target.value);
                setPreview(null);
              }}
              disabled={isPending}
            />
          </div>

          {/* Preview action buttons */}
          <div style={{ display: "flex", gap: 8 }}>
            <ClippedButton
              variant="cyan-ghost"
              size="md"
              onClick={() => runImport(true)}
              disabled={!canPreview}
            >
              {isPending && !preview ? "解析中..." : "預覽（不寫入）"}
            </ClippedButton>
            <ClippedButton
              variant="green-solid"
              size="md"
              onClick={() => runImport(false)}
              disabled={!canCommit}
            >
              {isPending && preview ? "匯入中..." : "確認匯入"}
            </ClippedButton>
            <ClippedButton
              variant="white-solid"
              size="md"
              onClick={onClose}
              disabled={isPending}
            >
              關閉
            </ClippedButton>
          </div>

          {/* Banner error */}
          {bannerError && (
            <div
              role="alert"
              style={{
                fontSize: 12,
                color: "#fff",
                background: "var(--stock-up)",
                padding: "8px 12px",
                fontWeight: 600,
              }}
            >
              {bannerError}
            </div>
          )}

          {/* Preview / commit result */}
          {summaryCounts && (
            <div
              style={{
                padding: "10px 12px",
                background: "var(--bg-secondary)",
                border: "1px solid var(--border-subtle)",
                fontSize: 12,
                color: "var(--text-muted)",
              }}
            >
              <span
                style={{
                  color: preview?.dry_run
                    ? "var(--accent-cyan)"
                    : "var(--stock-down)",
                  fontWeight: 700,
                  letterSpacing: "0.05em",
                  marginRight: 12,
                }}
              >
                {preview?.dry_run ? "預覽結果" : "匯入結果"}
              </span>
              共 {summaryCounts.parsed} 列 · 成功{" "}
              <span style={{ color: "var(--stock-down)" }}>
                {summaryCounts.ok}
              </span>{" "}
              · 失敗{" "}
              <span
                style={{
                  color:
                    summaryCounts.failed > 0
                      ? "var(--stock-up)"
                      : "var(--text-muted)",
                }}
              >
                {summaryCounts.failed}
              </span>
              {!preview?.dry_run && summaryCounts.failed === 0 && (
                <span style={{ marginLeft: 12, color: "var(--stock-down)" }}>
                  已寫入資料庫
                </span>
              )}
              {!preview?.dry_run && summaryCounts.failed > 0 && (
                <span style={{ marginLeft: 12, color: "var(--stock-up)" }}>
                  ⚠ 整批回滾，無任何寫入
                </span>
              )}
            </div>
          )}

          {/* Errors table */}
          {preview && preview.errors.length > 0 && (
            <div
              style={{
                border: "1px solid var(--border-subtle)",
                maxHeight: 260,
                overflowY: "auto",
              }}
            >
              <table
                style={{
                  width: "100%",
                  borderCollapse: "collapse",
                  fontSize: 11,
                  fontFamily: "monospace",
                }}
              >
                <thead
                  style={{
                    background: "var(--bg-secondary)",
                    position: "sticky",
                    top: 0,
                  }}
                >
                  <tr>
                    <Th>列</Th>
                    <Th>日期</Th>
                    <Th>動作</Th>
                    <Th>標的</Th>
                    <Th>數量</Th>
                    <Th>價格</Th>
                    <Th>錯誤</Th>
                  </tr>
                </thead>
                <tbody>
                  {preview.errors.map((row: ImportResultRow) => (
                    <tr
                      key={row.row_index}
                      style={{ borderTop: "1px solid var(--border-subtle)" }}
                    >
                      <Td>{row.row_index}</Td>
                      <Td>{row.trade_date ?? "—"}</Td>
                      <Td>{row.action ?? "—"}</Td>
                      <Td>{row.symbol ?? "—"}</Td>
                      <Td>{row.quantity ?? "—"}</Td>
                      <Td>{row.price ?? "—"}</Td>
                      <Td style={{ color: "var(--stock-up)" }}>
                        {labelForRowError(row.error)}
                      </Td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

// ── Tiny presentational helpers, scoped to this modal ─────────────────────

function Th({ children }: { children: React.ReactNode }) {
  return (
    <th
      style={{
        textAlign: "left",
        padding: "6px 8px",
        fontWeight: 700,
        color: "var(--text-muted)",
        fontSize: 10,
        textTransform: "uppercase",
        letterSpacing: "0.08em",
      }}
    >
      {children}
    </th>
  );
}

function Td({
  children,
  style,
}: {
  children: React.ReactNode;
  style?: React.CSSProperties;
}) {
  return (
    <td
      style={{
        padding: "6px 8px",
        color: "var(--foreground)",
        ...style,
      }}
    >
      {children}
    </td>
  );
}
