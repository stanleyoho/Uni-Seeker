"use client";

/**
 * Add Holding Trade Modal — Phase 3 frontend X3.
 *
 * Mirrors `journal/add-trade-modal.tsx` pattern (native input, no form lib).
 * Submits to POST /holdings/trades via `useCreateHoldingTrade`.
 *
 * Backend wire contract reminders:
 *   - Action is "BUY" | "SELL" only (no DIVIDEND / SPLIT here — dividends
 *     have their own dedicated POST /holdings/dividends endpoint).
 *   - `qty` is the wire field on POST (NOT `quantity`).
 *   - All decimal fields are sent as strings (Decimal-as-string contract).
 *   - Backend may reject with 403 limit_exceeded / feature_unavailable,
 *     422 insufficient_shares (SELL only), 422 invalid_input, or 404.
 */

import { useState } from "react";
import { ClippedButton } from "@/components/stratos/primitives";
import { useCreateHoldingTrade } from "@/hooks/use-holdings";
import {
  ApiError,
  type HoldingAccount,
  type HoldingMarket,
  type HoldingTrade,
  type HoldingTradeAction,
} from "@/lib/api-client";

interface AddHoldingTradeModalProps {
  accounts: HoldingAccount[];
  defaultAccountId?: number;
  onClose: () => void;
  onSuccess?: (trade: HoldingTrade) => void;
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

const ACTION_COLORS: Record<HoldingTradeAction, string> = {
  BUY: "var(--stock-up)",
  SELL: "var(--stock-down)",
};

/**
 * Map ApiError → user-facing zh-TW message.
 *
 * Backend ships structured `code` strings (e.g. "limit_exceeded:max_trades_per_month").
 * The fetch wrapper lands them on `ApiError.code`; we also fall back on
 * `message` (set from response `detail`) for free-form text.
 */
function mapTradeError(err: unknown, action: HoldingTradeAction): string {
  if (!(err instanceof ApiError)) {
    return err instanceof Error ? err.message : "新增失敗，請稍後再試";
  }
  const { status, code, message } = err;
  if (status === 422) {
    if (code === "insufficient_shares" || message.includes("insufficient_shares")) {
      return action === "SELL" ? "持股不足" : "資料有誤";
    }
    if (code === "invalid_input" || message.includes("invalid_input")) {
      return "交易資料有誤，請檢查";
    }
    return message || "交易資料有誤，請檢查";
  }
  if (status === 403) {
    if (code?.startsWith("limit_exceeded:max_trades_per_month")) {
      return "本月交易上限已達，升級到 Pro 解鎖";
    }
    if (code?.startsWith("feature_unavailable")) {
      return "升級 Pro 解鎖此功能";
    }
    return message || "權限不足";
  }
  if (status === 404) return "帳戶不存在";
  return message || "新增失敗";
}

export function AddHoldingTradeModal({
  accounts,
  defaultAccountId,
  onClose,
  onSuccess,
}: AddHoldingTradeModalProps) {
  const initialAccount =
    accounts.find((a) => a.id === defaultAccountId) ?? accounts[0];

  const [accountId, setAccountId] = useState<number>(initialAccount?.id ?? 0);
  const [action, setAction] = useState<HoldingTradeAction>("BUY");
  const [symbol, setSymbol] = useState("");
  const [market, setMarket] = useState<HoldingMarket>(
    initialAccount?.market ?? "TW_TWSE",
  );
  const [quantity, setQuantity] = useState("");
  const [price, setPrice] = useState("");
  const [fee, setFee] = useState("0");
  const [tax, setTax] = useState("0");
  const [tradeDate, setTradeDate] = useState(
    new Date().toISOString().slice(0, 10),
  );
  const [note, setNote] = useState("");
  const [error, setError] = useState<string | null>(null);

  const createTrade = useCreateHoldingTrade();
  const selectedAccount = accounts.find((a) => a.id === accountId);

  /* Live preview — total cost (BUY) / total proceeds (SELL) */
  const qtyNum = Number(quantity);
  const priceNum = Number(price);
  const feeNum = Number(fee || "0");
  const taxNum = Number(tax || "0");
  const preview =
    Number.isFinite(qtyNum) && Number.isFinite(priceNum) && qtyNum > 0 && priceNum > 0
      ? action === "BUY"
        ? qtyNum * priceNum + feeNum
        : qtyNum * priceNum - feeNum - taxNum
      : null;

  async function handleSubmit() {
    setError(null);

    /* Client-side validation */
    if (!accountId || !selectedAccount) {
      setError("請選擇帳戶");
      return;
    }
    if (!symbol.trim()) {
      setError("請輸入標的代碼");
      return;
    }
    if (!Number.isFinite(qtyNum) || qtyNum <= 0) {
      setError("數量必須大於 0");
      return;
    }
    if (!Number.isFinite(priceNum) || priceNum <= 0) {
      setError("價格必須大於 0");
      return;
    }

    try {
      const created = await createTrade.mutateAsync({
        account_id: accountId,
        action,
        symbol: symbol.trim().toUpperCase(),
        market,
        qty: quantity,
        price,
        fee: fee || "0",
        tax: tax || "0",
        trade_date: tradeDate || null,
        note: note.trim() ? note.trim() : null,
      });
      onSuccess?.(created);
      onClose();
    } catch (e) {
      setError(mapTradeError(e, action));
    }
  }

  const isPending = createTrade.isPending;
  const submitVariant = action === "BUY" ? "red-solid" : "green-solid";

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
            新增持倉交易
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

        {/* BUY/SELL pill toggle */}
        <div
          style={{
            display: "flex",
            marginBottom: 16,
            border: "1px solid var(--border-subtle)",
          }}
          role="tablist"
          aria-label="交易方向"
        >
          {(["BUY", "SELL"] as HoldingTradeAction[]).map((a) => (
            <button
              key={a}
              role="tab"
              aria-selected={action === a}
              onClick={() => setAction(a)}
              disabled={isPending}
              style={{
                flex: 1,
                padding: "10px 8px",
                fontSize: 12,
                fontWeight: 700,
                border: "none",
                cursor: isPending ? "not-allowed" : "pointer",
                background: action === a ? ACTION_COLORS[a] : "transparent",
                color:
                  action === a
                    ? "#fff"
                    : "var(--text-muted)",
                transition: "all 0.15s",
                letterSpacing: "0.05em",
              }}
            >
              {a === "BUY" ? "買入 BUY" : "賣出 SELL"}
            </button>
          ))}
        </div>

        <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
          {/* Account selector */}
          <div>
            <label className={labelCls}>帳戶</label>
            <select
              className={inputCls}
              value={accountId}
              onChange={(e) => setAccountId(Number(e.target.value))}
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

          {/* Symbol + Market — stack on mobile, 1.5fr/1fr on sm+ */}
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

          {/* Quantity + Price — 2-col on all sizes (qty/price stay paired) */}
          <div className="grid grid-cols-2 gap-2">
            <div>
              <label className={labelCls}>數量（股）</label>
              <input
                className={inputCls}
                placeholder="0"
                value={quantity}
                onChange={(e) => setQuantity(e.target.value)}
                inputMode="decimal"
                disabled={isPending}
              />
            </div>
            <div>
              <label className={labelCls}>
                成交價 ({selectedAccount?.currency ?? "—"})
              </label>
              <input
                className={inputCls}
                placeholder="0.00"
                value={price}
                onChange={(e) => setPrice(e.target.value)}
                inputMode="decimal"
                disabled={isPending}
              />
            </div>
          </div>

          {/* Fee + Tax — 2-col on all sizes (numeric pair, stays paired) */}
          <div className="grid grid-cols-2 gap-2">
            <div>
              <label className={labelCls}>手續費</label>
              <input
                className={inputCls}
                placeholder="0"
                value={fee}
                onChange={(e) => setFee(e.target.value)}
                inputMode="decimal"
                disabled={isPending}
              />
            </div>
            <div>
              <label className={labelCls}>稅 / 證交稅</label>
              <input
                className={inputCls}
                placeholder="0"
                value={tax}
                onChange={(e) => setTax(e.target.value)}
                inputMode="decimal"
                disabled={isPending}
              />
            </div>
          </div>

          {/* Trade Date */}
          <div>
            <label className={labelCls}>交易日期</label>
            <input
              type="date"
              className={inputCls}
              value={tradeDate}
              onChange={(e) => setTradeDate(e.target.value)}
              disabled={isPending}
            />
          </div>

          {/* Note */}
          <div>
            <label className={labelCls}>備註</label>
            <input
              className={inputCls}
              placeholder="策略理由、標籤..."
              value={note}
              onChange={(e) => setNote(e.target.value)}
              disabled={isPending}
            />
          </div>

          {/* Preview */}
          {preview !== null && (
            <div
              style={{
                padding: "10px 12px",
                background:
                  action === "BUY"
                    ? "var(--stock-up-bg)"
                    : "var(--stock-down-bg)",
                border:
                  action === "BUY"
                    ? "1px solid rgba(238,63,44,0.2)"
                    : "1px solid rgba(16,185,129,0.2)",
                fontSize: 12,
                color: "var(--text-muted)",
                lineHeight: 1.8,
              }}
            >
              <span
                style={{
                  color:
                    action === "BUY"
                      ? "var(--stock-up)"
                      : "var(--stock-down)",
                  fontWeight: 700,
                }}
              >
                即時預覽{" "}
              </span>
              {action === "BUY" ? "總成本" : "總收入"} ≈{" "}
              <span
                style={{
                  color: "var(--foreground)",
                  fontFamily: "monospace",
                }}
              >
                {preview.toLocaleString("zh-TW", {
                  maximumFractionDigits: 2,
                })}{" "}
                {selectedAccount?.currency ?? ""}
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
              variant={submitVariant}
              size="md"
              onClick={handleSubmit}
              disabled={isPending}
            >
              {isPending
                ? "處理中..."
                : action === "BUY"
                ? "確認買入"
                : "確認賣出"}
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
