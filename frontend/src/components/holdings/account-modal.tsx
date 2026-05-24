"use client";

/**
 * Account Modal — Phase 3 frontend X3.
 *
 * Dual-purpose: create OR edit a HoldingAccount. Submits to:
 *   - POST  /holdings/accounts  via `useCreateHoldingAccount`
 *   - PATCH /holdings/accounts/:id via `useUpdateHoldingAccount`
 *
 * Backend wire contract (HoldingAccountCreateRequest):
 *   - `name` + `market` are required.
 *   - `broker`, `currency`, `description` optional (currency defaults TWD).
 *
 * The task spec lists only name / broker / currency, but `market` is a
 * backend-required field on creation. We therefore also expose it (hidden
 * default = TW_TWSE) so creates don't 422 on an invisible field.
 */

import { useState } from "react";
import { ClippedButton } from "@/components/stratos/primitives";
import {
  useCreateHoldingAccount,
  useUpdateHoldingAccount,
} from "@/hooks/use-holdings";
import {
  ApiError,
  type HoldingAccount,
  type HoldingMarket,
} from "@/lib/api-client";

interface AccountModalProps {
  mode: "create" | "edit";
  account?: HoldingAccount;
  onClose: () => void;
  onSuccess?: (account: HoldingAccount) => void;
}

const inputCls =
  "w-full px-3 py-2 bg-[var(--bg-secondary)] border border-[var(--border-subtle)] text-sm text-[var(--foreground)] placeholder-[var(--text-muted)] focus:border-[var(--accent-cyan)] outline-none tabular-nums";

const labelCls =
  "text-[10px] font-bold uppercase tracking-[0.1em] text-[var(--text-muted)] mb-1 block";

const COMMON_BROKERS = [
  "元大",
  "永豐金",
  "凱基",
  "富邦",
  "國泰",
  "玉山",
  "群益",
  "Firstrade",
  "Charles Schwab",
  "Interactive Brokers",
  "Robinhood",
];

const CURRENCIES = ["TWD", "USD", "HKD", "JPY"];

const MARKETS: { value: HoldingMarket; label: string }[] = [
  { value: "TW_TWSE", label: "TW 上市 (TWSE)" },
  { value: "TW_TPEX", label: "TW 上櫃 (TPEX)" },
  { value: "US_NYSE", label: "US NYSE" },
  { value: "US_NASDAQ", label: "US NASDAQ" },
];

function mapAccountError(err: unknown): string {
  if (!(err instanceof ApiError)) {
    return err instanceof Error ? err.message : "操作失敗，請稍後再試";
  }
  const { status, code, message } = err;
  if (status === 403) {
    if (code?.startsWith("limit_exceeded:max_accounts")) {
      return "帳戶上限已達，升級 Basic / Pro 解鎖";
    }
    if (code?.startsWith("feature_unavailable:multi_account")) {
      return "升級 Basic / Pro 解鎖多帳戶";
    }
    if (code?.startsWith("feature_unavailable")) {
      return "升級 Basic / Pro 解鎖此功能";
    }
    return message || "權限不足";
  }
  if (status === 422) {
    return message || "帳戶資料格式有誤";
  }
  if (status === 404) return "帳戶不存在";
  return message || "操作失敗";
}

export function AccountModal({
  mode,
  account,
  onClose,
  onSuccess,
}: AccountModalProps) {
  const [name, setName] = useState(account?.name ?? "");
  const [broker, setBroker] = useState(account?.broker ?? "");
  const [customBroker, setCustomBroker] = useState("");
  const [isCustomBroker, setIsCustomBroker] = useState(
    Boolean(account?.broker && !COMMON_BROKERS.includes(account.broker)),
  );
  const [currency, setCurrency] = useState(account?.currency ?? "TWD");
  const [market, setMarket] = useState<HoldingMarket>(
    account?.market ?? "TW_TWSE",
  );
  const [description, setDescription] = useState(account?.description ?? "");
  const [error, setError] = useState<string | null>(null);

  const createAccount = useCreateHoldingAccount();
  const updateAccount = useUpdateHoldingAccount();

  const isPending = createAccount.isPending || updateAccount.isPending;

  /* Resolve the effective broker — custom input takes precedence */
  const resolvedBroker = isCustomBroker ? customBroker.trim() : broker.trim();

  async function handleSubmit() {
    setError(null);

    if (!name.trim()) {
      setError("請輸入帳戶名稱");
      return;
    }

    try {
      if (mode === "create") {
        const created = await createAccount.mutateAsync({
          name: name.trim(),
          market,
          broker: resolvedBroker || null,
          currency: currency || "TWD",
          description: description.trim() || null,
        });
        onSuccess?.(created);
      } else if (mode === "edit" && account) {
        const updated = await updateAccount.mutateAsync({
          id: account.id,
          body: {
            name: name.trim(),
            market,
            broker: resolvedBroker || null,
            currency: currency || "TWD",
            description: description.trim() || null,
          },
        });
        onSuccess?.(updated);
      }
      onClose();
    } catch (e) {
      setError(mapAccountError(e));
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
        className="p-4 sm:p-6 max-h-[calc(100vh-32px)] overflow-y-auto"
        style={{
          background: "var(--glass-bg)",
          border: "1px solid var(--border-color)",
          width: "100%",
          maxWidth: 480,
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
            {mode === "create" ? "新增券商帳戶" : "編輯帳戶"}
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
          {/* Name */}
          <div>
            <label className={labelCls}>帳戶名稱</label>
            <input
              className={inputCls}
              placeholder="主力 / 美股 / 存股..."
              value={name}
              onChange={(e) => setName(e.target.value)}
              disabled={isPending}
            />
          </div>

          {/* Market */}
          <div>
            <label className={labelCls}>主要市場</label>
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

          {/* Broker */}
          <div>
            <label className={labelCls}>券商</label>
            {!isCustomBroker ? (
              <select
                className={inputCls}
                value={broker}
                onChange={(e) => {
                  if (e.target.value === "__custom__") {
                    setIsCustomBroker(true);
                    setBroker("");
                  } else {
                    setBroker(e.target.value);
                  }
                }}
                disabled={isPending}
              >
                <option value="">— 未指定 —</option>
                {COMMON_BROKERS.map((b) => (
                  <option key={b} value={b}>
                    {b}
                  </option>
                ))}
                <option value="__custom__">自訂...</option>
              </select>
            ) : (
              <div style={{ display: "flex", gap: 6 }}>
                <input
                  className={inputCls}
                  placeholder="輸入自訂券商名稱"
                  value={customBroker}
                  onChange={(e) => setCustomBroker(e.target.value)}
                  disabled={isPending}
                />
                <button
                  onClick={() => {
                    setIsCustomBroker(false);
                    setCustomBroker("");
                  }}
                  disabled={isPending}
                  style={{
                    fontSize: 11,
                    color: "var(--text-muted)",
                    background: "transparent",
                    border: "1px solid var(--border-subtle)",
                    padding: "0 10px",
                    cursor: isPending ? "not-allowed" : "pointer",
                    whiteSpace: "nowrap",
                  }}
                >
                  選清單
                </button>
              </div>
            )}
          </div>

          {/* Currency */}
          <div>
            <label className={labelCls}>計價幣別</label>
            <select
              className={inputCls}
              value={currency}
              onChange={(e) => setCurrency(e.target.value)}
              disabled={isPending}
            >
              {CURRENCIES.map((c) => (
                <option key={c} value={c}>
                  {c}
                </option>
              ))}
            </select>
          </div>

          {/* Description (optional) */}
          <div>
            <label className={labelCls}>備註（可選）</label>
            <input
              className={inputCls}
              placeholder="用途、策略..."
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              disabled={isPending}
            />
          </div>

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
              {isPending
                ? "處理中..."
                : mode === "create"
                ? "建立帳戶"
                : "儲存變更"}
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
