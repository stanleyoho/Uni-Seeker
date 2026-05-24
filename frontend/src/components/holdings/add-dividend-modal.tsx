"use client";

/**
 * Add Holding Dividend Modal — Phase 3 frontend X3.
 *
 * Dual-mode (CASH | STOCK) modal that submits to POST /holdings/dividends
 * via `useCreateHoldingDividend`.
 *
 * Backend wire contract (HoldingDividendCreateRequest):
 *   - `dividend_type` switches the required field on the body:
 *       CASH  → `amount_per_share` is required (per-share cash payout).
 *       STOCK → `ratio` is required (e.g. "0.1" = 10 股配 1 股).
 *   - `withholding_tax` only applies to CASH (predeclared tax withholding).
 *   - `pay_date` only applies to CASH; STOCK shares hit on ex-dividend.
 *   - `quantity_at_record` is the held qty at the record date.
 *
 * The frontend keeps a single `amountPerShare` field in state and routes
 * it to either `amount_per_share` (CASH) or `ratio` (STOCK) on submit.
 */

import { useState } from "react";
import { ClippedButton } from "@/components/stratos/primitives";
import { useCreateHoldingDividend } from "@/hooks/use-holdings";
import {
  ApiError,
  type HoldingAccount,
  type HoldingDividend,
  type HoldingDividendType,
  type HoldingMarket,
} from "@/lib/api-client";

interface AddHoldingDividendModalProps {
  accounts: HoldingAccount[];
  defaultAccountId?: number;
  onClose: () => void;
  onSuccess?: (dividend: HoldingDividend) => void;
}

const inputCls =
  "w-full px-3 py-2 bg-[var(--bg-secondary)] border border-[var(--border-subtle)] text-sm text-[var(--foreground)] placeholder-[var(--text-muted)] focus:border-[var(--accent-cyan)] outline-none tabular-nums";

const labelCls =
  "text-[10px] font-bold uppercase tracking-[0.1em] text-[var(--text-muted)] mb-1 block";

const MARKETS: { value: HoldingMarket; label: string }[] = [
  { value: "TW_TWSE", label: "TW 上市" },
  { value: "TW_TPEX", label: "TW 上櫃" },
  { value: "US_NYSE", label: "US NYSE" },
  { value: "US_NASDAQ", label: "US NASDAQ" },
];

function mapDividendError(err: unknown): string {
  if (!(err instanceof ApiError)) {
    return err instanceof Error ? err.message : "新增失敗，請稍後再試";
  }
  const { status, code, message } = err;
  if (status === 403) {
    if (code?.startsWith("feature_unavailable:dividends")) {
      return "升級到 Basic / Pro 解鎖配息追蹤";
    }
    if (code?.startsWith("feature_unavailable")) {
      return "升級 Basic / Pro 解鎖此功能";
    }
    return message || "權限不足";
  }
  if (status === 422) {
    if (
      code === "invalid_dividend_input" ||
      code === "invalid_input" ||
      message.includes("invalid_dividend_input")
    ) {
      return "配息資料格式有誤";
    }
    return message || "配息資料格式有誤";
  }
  if (status === 404) return "帳戶不存在";
  return message || "新增失敗";
}

export function AddHoldingDividendModal({
  accounts,
  defaultAccountId,
  onClose,
  onSuccess,
}: AddHoldingDividendModalProps) {
  const initialAccount =
    accounts.find((a) => a.id === defaultAccountId) ?? accounts[0];

  const [accountId, setAccountId] = useState<number>(initialAccount?.id ?? 0);
  const [dividendType, setDividendType] = useState<HoldingDividendType>("CASH");
  const [symbol, setSymbol] = useState("");
  const [market, setMarket] = useState<HoldingMarket>(
    initialAccount?.market ?? "TW_TWSE",
  );
  const [exDividendDate, setExDividendDate] = useState(
    new Date().toISOString().slice(0, 10),
  );
  const [payDate, setPayDate] = useState("");
  /** Routed to `amount_per_share` (CASH) or `ratio` (STOCK) on submit. */
  const [amountPerShare, setAmountPerShare] = useState("");
  const [quantityAtRecord, setQuantityAtRecord] = useState("");
  const [withholdingTax, setWithholdingTax] = useState("0");
  const [currency, setCurrency] = useState(initialAccount?.currency ?? "TWD");
  const [note, setNote] = useState("");
  const [error, setError] = useState<string | null>(null);

  const createDividend = useCreateHoldingDividend();

  const isCash = dividendType === "CASH";
  const amountNum = Number(amountPerShare);
  const qtyNum = Number(quantityAtRecord);
  const taxNum = Number(withholdingTax || "0");

  /* Live preview for CASH only — STOCK split is qty-rescale, no $ figure */
  const cashPreview =
    isCash &&
    Number.isFinite(amountNum) &&
    Number.isFinite(qtyNum) &&
    amountNum > 0 &&
    qtyNum > 0
      ? {
          gross: amountNum * qtyNum,
          net: amountNum * qtyNum - taxNum,
        }
      : null;

  async function handleSubmit() {
    setError(null);

    if (!accountId) {
      setError("請選擇帳戶");
      return;
    }
    if (!symbol.trim()) {
      setError("請輸入標的代碼");
      return;
    }
    if (!exDividendDate) {
      setError("請選擇除息日");
      return;
    }
    if (!Number.isFinite(amountNum) || amountNum <= 0) {
      setError(isCash ? "每股配息金額必須大於 0" : "配股比例必須大於 0");
      return;
    }
    if (!Number.isFinite(qtyNum) || qtyNum <= 0) {
      setError("除息日持股數必須大於 0");
      return;
    }

    try {
      const created = await createDividend.mutateAsync({
        account_id: accountId,
        symbol: symbol.trim().toUpperCase(),
        market,
        dividend_type: dividendType,
        ex_dividend_date: exDividendDate,
        pay_date: isCash && payDate ? payDate : null,
        amount_per_share: isCash ? amountPerShare : null,
        ratio: !isCash ? amountPerShare : null,
        quantity_at_record: quantityAtRecord,
        currency: currency || "TWD",
        withholding_tax: isCash ? withholdingTax || "0" : "0",
        note: note.trim() ? note.trim() : null,
      });
      onSuccess?.(created);
      onClose();
    } catch (e) {
      setError(mapDividendError(e));
    }
  }

  const isPending = createDividend.isPending;

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
        className="p-4 sm:p-6 max-h-[calc(100vh-32px)] overflow-y-auto"
        style={{
          background: "var(--glass-bg)",
          border: "1px solid var(--border-color)",
          width: "100%",
          maxWidth: 520,
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
            新增配息
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

        {/* CASH | STOCK tab toggle */}
        <div
          style={{
            display: "flex",
            marginBottom: 16,
            border: "1px solid var(--border-subtle)",
          }}
          role="tablist"
          aria-label="配息類型"
        >
          {(["CASH", "STOCK"] as HoldingDividendType[]).map((t) => (
            <button
              key={t}
              role="tab"
              aria-selected={dividendType === t}
              onClick={() => setDividendType(t)}
              disabled={isPending}
              style={{
                flex: 1,
                padding: "10px 8px",
                fontSize: 12,
                fontWeight: 700,
                border: "none",
                cursor: isPending ? "not-allowed" : "pointer",
                background:
                  dividendType === t ? "var(--accent-cyan)" : "transparent",
                color:
                  dividendType === t
                    ? "#000"
                    : "var(--text-muted)",
                transition: "all 0.15s",
                letterSpacing: "0.05em",
              }}
            >
              {t === "CASH" ? "現金股利 CASH" : "股票股利 STOCK"}
            </button>
          ))}
        </div>

        <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
          {/* Account */}
          <div>
            <label className={labelCls}>帳戶</label>
            <select
              className={inputCls}
              value={accountId}
              onChange={(e) => {
                const id = Number(e.target.value);
                setAccountId(id);
                const acc = accounts.find((a) => a.id === id);
                if (acc) setCurrency(acc.currency);
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

          {/* Symbol + Market */}
          <div className="grid grid-cols-1 sm:grid-cols-[1.5fr_1fr] gap-2">
            <div>
              <label className={labelCls}>標的代碼</label>
              <input
                className={inputCls}
                placeholder="2330 / AAPL"
                value={symbol}
                onChange={(e) => setSymbol(e.target.value.toUpperCase())}
                disabled={isPending}
              />
            </div>
            <div>
              <label className={labelCls}>市場</label>
              <select
                className={inputCls}
                value={market}
                onChange={(e) => setMarket(e.target.value as HoldingMarket)}
                disabled={isPending}
              >
                {MARKETS.map((m) => (
                  <option key={m.value} value={m.value}>
                    {m.label}
                  </option>
                ))}
              </select>
            </div>
          </div>

          {/* Ex-dividend date + Pay date — stack on mobile; CASH gets a 2-col
             layout on sm+, non-cash always single column. */}
          <div
            className={
              isCash
                ? "grid grid-cols-1 sm:grid-cols-2 gap-2"
                : "grid grid-cols-1 gap-2"
            }
          >
            <div>
              <label className={labelCls}>除息日 / 除權日</label>
              <input
                type="date"
                className={inputCls}
                value={exDividendDate}
                onChange={(e) => setExDividendDate(e.target.value)}
                disabled={isPending}
              />
            </div>
            {isCash && (
              <div>
                <label className={labelCls}>發放日（可選）</label>
                <input
                  type="date"
                  className={inputCls}
                  value={payDate}
                  onChange={(e) => setPayDate(e.target.value)}
                  disabled={isPending}
                />
              </div>
            )}
          </div>

          {/* Amount per share / Ratio + Quantity at record */}
          <div className="grid grid-cols-2 gap-2">
            <div>
              <label className={labelCls}>
                {isCash ? `每股配息 (${currency})` : "配股比例"}
              </label>
              <input
                className={inputCls}
                placeholder={isCash ? "5.00" : "0.1"}
                value={amountPerShare}
                onChange={(e) => setAmountPerShare(e.target.value)}
                inputMode="decimal"
                disabled={isPending}
              />
            </div>
            <div>
              <label className={labelCls}>除息日持股</label>
              <input
                className={inputCls}
                placeholder="0"
                value={quantityAtRecord}
                onChange={(e) => setQuantityAtRecord(e.target.value)}
                inputMode="decimal"
                disabled={isPending}
              />
            </div>
          </div>

          {/* STOCK helper hint */}
          {!isCash && (
            <div
              style={{
                fontSize: 11,
                color: "var(--text-muted)",
                lineHeight: 1.6,
                padding: "6px 10px",
                background: "rgba(0,229,255,0.04)",
                border: "1px solid rgba(0,229,255,0.12)",
              }}
            >
              比例 = 配發股 ÷ 原持股，例如 0.1 = 10 股配 1 股
            </div>
          )}

          {/* Withholding tax + Currency (CASH only shows tax) */}
          <div className="grid grid-cols-2 gap-2">
            {isCash ? (
              <div>
                <label className={labelCls}>預扣稅</label>
                <input
                  className={inputCls}
                  placeholder="0"
                  value={withholdingTax}
                  onChange={(e) => setWithholdingTax(e.target.value)}
                  inputMode="decimal"
                  disabled={isPending}
                />
              </div>
            ) : (
              <div />
            )}
            <div>
              <label className={labelCls}>幣別</label>
              <input
                className={inputCls}
                placeholder="TWD"
                value={currency}
                onChange={(e) => setCurrency(e.target.value.toUpperCase())}
                disabled={isPending}
              />
            </div>
          </div>

          {/* Note */}
          <div>
            <label className={labelCls}>備註</label>
            <input
              className={inputCls}
              placeholder="參與除息日期、來源..."
              value={note}
              onChange={(e) => setNote(e.target.value)}
              disabled={isPending}
            />
          </div>

          {/* Preview (CASH only) */}
          {cashPreview && (
            <div
              style={{
                padding: "10px 12px",
                background: "rgba(0,229,255,0.06)",
                border: "1px solid rgba(0,229,255,0.15)",
                fontSize: 12,
                color: "var(--text-muted)",
                lineHeight: 1.8,
              }}
            >
              <span
                style={{ color: "var(--accent-cyan)", fontWeight: 700 }}
              >
                即時預覽{" "}
              </span>
              總配息 ≈{" "}
              <span
                style={{
                  color: "var(--foreground)",
                  fontFamily: "monospace",
                }}
              >
                {cashPreview.gross.toLocaleString("zh-TW", {
                  maximumFractionDigits: 2,
                })}{" "}
                {currency}
              </span>
              {" · 稅後 ≈ "}
              <span
                style={{
                  color: "var(--foreground)",
                  fontFamily: "monospace",
                }}
              >
                {cashPreview.net.toLocaleString("zh-TW", {
                  maximumFractionDigits: 2,
                })}{" "}
                {currency}
              </span>
            </div>
          )}

          {/* Error banner */}
          {error && (
            <div
              role="alert"
              style={{
                fontSize: 12,
                color: "#fff",
                background: "var(--accent-primary)",
                padding: "8px 12px",
                fontWeight: 600,
                letterSpacing: "0.02em",
              }}
            >
              {error}
            </div>
          )}

          {/* Action buttons */}
          <div style={{ display: "flex", gap: 8, marginTop: 4 }}>
            <ClippedButton
              variant="cyan-ghost"
              size="md"
              onClick={handleSubmit}
              disabled={isPending}
            >
              {isPending ? "處理中..." : "確認新增"}
            </ClippedButton>
            <ClippedButton
              variant="white-solid"
              size="md"
              onClick={onClose}
              disabled={isPending}
            >
              取消
            </ClippedButton>
          </div>
        </div>
      </div>
    </div>
  );
}
