"use client";

import { useState } from "react";
import { ClippedButton } from "@/components/stratos/primitives";
import { useCreateJournalTrade } from "@/hooks/use-journal";
import type { JournalAccount } from "@/lib/api-client";

interface AddTradeModalProps {
  accounts: JournalAccount[];
  defaultAccountId?: number;
  onClose: () => void;
}

const inputCls =
  "w-full px-3 py-2 bg-[var(--bg-secondary)] border border-[var(--border-subtle)] text-sm text-[var(--foreground)] placeholder-[var(--text-muted)] focus:border-[var(--accent-cyan)] outline-none tabular-nums";

const labelCls =
  "text-[10px] font-bold uppercase tracking-[0.1em] text-[var(--text-muted)] mb-1 block";

type Action = "BUY" | "SELL" | "DIVIDEND" | "SPLIT";

const ACTION_COLORS: Record<Action, string> = {
  BUY: "var(--stock-up)",
  SELL: "var(--stock-down)",
  DIVIDEND: "#f59e0b",
  SPLIT: "var(--accent-cyan)",
};

export function AddTradeModal({ accounts, defaultAccountId, onClose }: AddTradeModalProps) {
  const [action, setAction] = useState<Action>("BUY");
  const [accountId, setAccountId] = useState<number>(defaultAccountId ?? accounts[0]?.id ?? 0);
  const [symbol, setSymbol] = useState("");
  const [market, setMarket] = useState<"TW" | "US" | "CRYPTO">("TW");
  const [date, setDate] = useState(new Date().toISOString().slice(0, 10));
  const [price, setPrice] = useState("");
  const [quantity, setQuantity] = useState("");
  const [fee, setFee] = useState("0");
  const [tax, setTax] = useState("0");
  const [note, setNote] = useState("");
  const [splitRatio, setSplitRatio] = useState("");
  const [error, setError] = useState<string | null>(null);

  const createTrade = useCreateJournalTrade(accountId);

  const selectedAccount = accounts.find((a) => a.id === accountId);

  /* Live preview calculation */
  const previewCost =
    action === "BUY" && price && quantity
      ? (Number(price) * Number(quantity) + Number(fee || 0)).toLocaleString("zh-TW", {
          maximumFractionDigits: 2,
        })
      : null;

  async function handleSubmit() {
    setError(null);
    if (!symbol.trim()) { setError("請輸入標的代碼"); return; }
    if ((action === "BUY" || action === "SELL") && (!price || !quantity)) {
      setError("買賣交易需填寫價格與數量");
      return;
    }
    if (action === "SPLIT" && !splitRatio) {
      setError("請填寫分割比例 (如 2 表示 2:1)");
      return;
    }
    try {
      await createTrade.mutateAsync({
        symbol: symbol.trim().toUpperCase(),
        market,
        action,
        date,
        price: price || null,
        quantity: quantity || null,
        fee: fee || "0",
        tax: tax || "0",
        note: note || null,
        split_ratio: action === "SPLIT" ? splitRatio : null,
      });
      onClose();
    } catch (e: unknown) {
      const msg = e instanceof Error ? e.message : "新增失敗，請檢查欄位";
      setError(msg);
    }
  }

  return (
    /* Backdrop */
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
      onClick={(e) => e.target === e.currentTarget && onClose()}
    >
      <div
        style={{
          background: "var(--glass-bg)",
          border: "1px solid var(--border-color)",
          width: "100%",
          maxWidth: 480,
          padding: 24,
          boxShadow: "var(--glass-shadow)",
        }}
      >
        {/* Header */}
        <div style={{ display: "flex", justifyContent: "space-between", marginBottom: 20 }}>
          <span style={{ fontSize: 14, fontWeight: 700, color: "var(--foreground)", letterSpacing: "-0.04em" }}>
            新增交易
          </span>
          <button
            onClick={onClose}
            style={{ color: "var(--text-muted)", background: "none", border: "none", cursor: "pointer", fontSize: 18 }}
          >
            ×
          </button>
        </div>

        {/* Action Toggle */}
        <div style={{ display: "flex", marginBottom: 16, border: "1px solid var(--border-subtle)" }}>
          {(["BUY", "SELL", "DIVIDEND", "SPLIT"] as Action[]).map((a) => (
            <button
              key={a}
              onClick={() => setAction(a)}
              style={{
                flex: 1,
                padding: "8px 4px",
                fontSize: 11,
                fontWeight: 700,
                border: "none",
                cursor: "pointer",
                background: action === a ? ACTION_COLORS[a] : "transparent",
                color: action === a ? (a === "BUY" ? "#000" : "#fff") : "var(--text-muted)",
                transition: "all 0.15s",
              }}
            >
              {a}
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
            >
              {accounts.map((acc) => (
                <option key={acc.id} value={acc.id}>{acc.name}</option>
              ))}
            </select>
          </div>

          {/* Symbol + Market */}
          <div style={{ display: "grid", gridTemplateColumns: "1.5fr 1fr", gap: 8 }}>
            <div>
              <label className={labelCls}>標的代碼</label>
              <input
                className={inputCls}
                placeholder="2330.TW / AAPL / BTC"
                value={symbol}
                onChange={(e) => setSymbol(e.target.value)}
              />
            </div>
            <div>
              <label className={labelCls}>市場</label>
              <select
                className={inputCls}
                value={market}
                onChange={(e) => setMarket(e.target.value as "TW" | "US" | "CRYPTO")}
              >
                <option value="TW">TW 台股</option>
                <option value="US">US 美股</option>
                <option value="CRYPTO">CRYPTO</option>
              </select>
            </div>
          </div>

          {/* Date */}
          <div>
            <label className={labelCls}>交易日期</label>
            <input
              type="date"
              className={inputCls}
              value={date}
              onChange={(e) => setDate(e.target.value)}
            />
          </div>

          {/* Price + Quantity (BUY/SELL only) */}
          {(action === "BUY" || action === "SELL") && (
            <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 8 }}>
              <div>
                <label className={labelCls}>成交價格 ({selectedAccount?.currency ?? "—"})</label>
                <input
                  className={inputCls}
                  placeholder="0.00"
                  value={price}
                  onChange={(e) => setPrice(e.target.value)}
                  inputMode="decimal"
                />
              </div>
              <div>
                <label className={labelCls}>數量（股/單位）</label>
                <input
                  className={inputCls}
                  placeholder="0"
                  value={quantity}
                  onChange={(e) => setQuantity(e.target.value)}
                  inputMode="decimal"
                />
              </div>
            </div>
          )}

          {/* Fee + Tax (BUY/SELL only) */}
          {(action === "BUY" || action === "SELL") && (
            <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 8 }}>
              <div>
                <label className={labelCls}>手續費</label>
                <input
                  className={inputCls}
                  placeholder="0"
                  value={fee}
                  onChange={(e) => setFee(e.target.value)}
                  inputMode="decimal"
                />
              </div>
              <div>
                <label className={labelCls}>稅（證交稅）</label>
                <input
                  className={inputCls}
                  placeholder="0"
                  value={tax}
                  onChange={(e) => setTax(e.target.value)}
                  inputMode="decimal"
                />
              </div>
            </div>
          )}

          {/* Split ratio (SPLIT only) */}
          {action === "SPLIT" && (
            <div>
              <label className={labelCls}>分割比例（新股/舊股，如 2 = 2:1）</label>
              <input
                className={inputCls}
                placeholder="2"
                value={splitRatio}
                onChange={(e) => setSplitRatio(e.target.value)}
                inputMode="decimal"
              />
            </div>
          )}

          {/* Note */}
          <div>
            <label className={labelCls}>備註 / 標籤</label>
            <input
              className={inputCls}
              placeholder="策略理由、標籤..."
              value={note}
              onChange={(e) => setNote(e.target.value)}
            />
          </div>

          {/* Preview */}
          {previewCost && (
            <div
              style={{
                padding: "10px 12px",
                background: "rgba(34,197,94,0.06)",
                border: "1px solid rgba(34,197,94,0.15)",
                fontSize: 12,
                color: "var(--text-muted)",
                lineHeight: 1.8,
              }}
            >
              <span style={{ color: "var(--stock-up)", fontWeight: 700 }}>即時預覽 </span>
              總成本 ≈{" "}
              <span style={{ color: "var(--foreground)", fontFamily: "monospace" }}>
                {previewCost} {selectedAccount?.currency ?? ""}
              </span>
            </div>
          )}

          {/* Error */}
          {error && (
            <div style={{ fontSize: 12, color: "var(--stock-down)", padding: "6px 0" }}>{error}</div>
          )}

          {/* Buttons */}
          <div style={{ display: "flex", gap: 8, marginTop: 4 }}>
            <ClippedButton
              variant="green-solid"
              size="md"
              onClick={handleSubmit}
              disabled={createTrade.isPending}
            >
              {createTrade.isPending ? "處理中..." : "確認新增"}
            </ClippedButton>
            <ClippedButton variant="cyan-ghost" size="md" onClick={onClose}>
              取消
            </ClippedButton>
          </div>
        </div>
      </div>
    </div>
  );
}
