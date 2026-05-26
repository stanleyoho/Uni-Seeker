"use client";

/**
 * Portfolio Rebalance Modal — Phase 5+ Pro-tier preview.
 *
 * Two-column layout:
 *   Left  : current positions (read-only); shows symbol / qty / value / current %.
 *   Right : target allocation table — one row per position with an editable
 *           target_pct input. Sum is enforced client-side (must equal 100
 *           before the preview button is enabled).
 *
 * On "preview" we call `usePreviewRebalance()` and render the suggested
 * trades + skipped reasons + final allocation pie totals below.
 *
 * Phase 1 scope: PREVIEW ONLY. The "apply" button stub clicks through
 * each suggested trade by opening the existing AddHoldingTradeModal one
 * at a time (the backend's POST /holdings/trades is the single source of
 * truth for inserting trades — there is no bulk-execute endpoint yet).
 *
 * Decimal-as-string contract: backend strings (`qty`, `estimated_price`,
 * `estimated_value`, `target_pct`) are kept as strings end-to-end; only
 * `Number()` at the render boundary. Same convention as add-trade-modal.tsx.
 */

import { useMemo, useState } from "react";
import { ClippedButton } from "@/components/stratos/primitives";
import {
  useExecuteRebalance,
  usePreviewRebalance,
} from "@/hooks/use-holdings";
import { useI18n } from "@/i18n/context";
import {
  ApiError,
  type HoldingAccount,
  type HoldingMarket,
  type HoldingPosition,
  type RebalanceExecuteResponse,
  type RebalanceResponse,
  type RebalanceTarget,
  type SuggestedTrade,
  type SkippedTrade,
} from "@/lib/api-client";

interface RebalanceModalProps {
  positions: HoldingPosition[];
  accounts: HoldingAccount[];
  /** Optional pre-selected account (matches page-level state). */
  defaultAccountId?: number | null;
  onClose: () => void;
  /**
   * Optional callback fired when the user clicks "apply" on a suggested
   * trade. The parent should open the AddHoldingTradeModal with these
   * defaults pre-filled. When omitted, the apply button is hidden.
   */
  onApplyTrade?: (trade: SuggestedTrade) => void;
}

// ── styling tokens (kept inline so this file is self-contained) ──────────

const labelCls =
  "text-[10px] font-bold uppercase tracking-[0.1em] text-[var(--text-muted)] mb-1 block";

const inputCls =
  "w-full px-2 py-1 bg-[var(--bg-secondary)] border border-[var(--border-subtle)] text-xs text-[var(--foreground)] focus:border-[var(--accent-cyan)] outline-none tabular-nums";

const tableCellCls =
  "px-2 py-1.5 text-xs tabular-nums border-b border-[var(--border-subtle)]";

// ── error mapper (mirrors add-trade-modal mapTradeError) ─────────────────

function mapPreviewError(
  err: unknown,
  t: (key: string) => string,
): string {
  if (!(err instanceof ApiError)) {
    return err instanceof Error ? err.message : t("error_generic");
  }
  const { status, code, message } = err;
  if (status === 403) {
    if (code?.startsWith("feature_unavailable")) return t("error_upgrade");
    return message || t("error_upgrade");
  }
  if (status === 404) return t("error_account_not_found");
  if (status === 422) return t("error_invalid");
  return message || t("error_generic");
}

/**
 * Map execute-specific errors. Reuses the preview mapper for the shared
 * 403/404 cases but distinguishes the two 422 strings the execute
 * endpoint can emit: `account_id_required_for_execute` vs the generic
 * `invalid_rebalance_input`. The backend's FastAPI `detail` lands in
 * `ApiError.message` (apiFetch falls back to `body.detail`), so we
 * sniff both `code` and `message` for the canonical string.
 */
function mapExecuteError(
  err: unknown,
  t: (key: string) => string,
): string {
  if (err instanceof ApiError && err.status === 422) {
    const tag = err.code ?? err.message;
    if (tag === "account_id_required_for_execute") {
      return t("error_account_required");
    }
  }
  return mapPreviewError(err, t);
}

// ── row model for the editable right-hand table ──────────────────────────

interface TargetRow {
  symbol: string;
  market: HoldingMarket;
  /** User-input string; preserves leading zeros / decimals during typing. */
  target_pct: string;
}

/**
 * Seed the target rows from the current positions: each open position
 * gets a row pre-filled with its current allocation percentage. The user
 * then nudges the values up/down.
 */
function seedTargets(positions: HoldingPosition[]): TargetRow[] {
  const open = positions.filter((p) => !p.is_closed && Number(p.qty) > 0);
  const totalValue = open.reduce((sum, p) => {
    const v = Number(p.last_price ?? 0) * Number(p.qty);
    return sum + (Number.isFinite(v) ? v : 0);
  }, 0);
  return open.map((p) => {
    const v = Number(p.last_price ?? 0) * Number(p.qty);
    const pct = totalValue > 0 && Number.isFinite(v) ? (v / totalValue) * 100 : 0;
    return {
      symbol: p.symbol,
      market: p.market,
      target_pct: pct.toFixed(2),
    };
  });
}

// ── main component ───────────────────────────────────────────────────────

export function RebalanceModal({
  positions,
  accounts,
  defaultAccountId,
  onClose,
  onApplyTrade,
}: RebalanceModalProps) {
  const { t } = useI18n();
  // Local lookup so we can write `tr("title")` without a deep guard chain.
  const tr = (key: string): string => {
    const node = (t.holdings as { rebalance?: Record<string, string> } | undefined)
      ?.rebalance;
    return node?.[key] ?? key;
  };

  const open = useMemo(
    () => positions.filter((p) => !p.is_closed && Number(p.qty) > 0),
    [positions],
  );
  const [targets, setTargets] = useState<TargetRow[]>(() =>
    seedTargets(positions),
  );
  const [accountId, setAccountId] = useState<number | null>(
    defaultAccountId ?? null,
  );
  const [minTradeValue, setMinTradeValue] = useState<string>("100");
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<RebalanceResponse | null>(null);
  // Execute flow: confirmation gate + result. We keep the preview `result`
  // visible alongside the execute summary so the user can compare planned
  // vs actual; `executeResult` is the per-trade outcome from the server.
  const [confirmOpen, setConfirmOpen] = useState(false);
  const [executeResult, setExecuteResult] =
    useState<RebalanceExecuteResponse | null>(null);

  const previewMutation = usePreviewRebalance();
  const executeMutation = useExecuteRebalance();
  const isPending = previewMutation.isPending || executeMutation.isPending;

  // ── derived ──────────────────────────────────────────────────────────

  const totalValue = useMemo(
    () =>
      open.reduce((sum, p) => {
        const v = Number(p.last_price ?? 0) * Number(p.qty);
        return sum + (Number.isFinite(v) ? v : 0);
      }, 0),
    [open],
  );

  const sumTargets = useMemo(
    () =>
      targets.reduce((s, row) => {
        const n = Number(row.target_pct);
        return s + (Number.isFinite(n) ? n : 0);
      }, 0),
    [targets],
  );

  const sumValid = Math.abs(sumTargets - 100) < 0.01;

  // ── handlers ─────────────────────────────────────────────────────────

  function updateTargetPct(idx: number, value: string) {
    setTargets((rows) =>
      rows.map((r, i) => (i === idx ? { ...r, target_pct: value } : r)),
    );
  }

  async function handlePreview() {
    setError(null);
    setResult(null);
    setExecuteResult(null);
    if (!sumValid) {
      setError(tr("error_sum"));
      return;
    }
    const payload: RebalanceTarget[] = targets.map((r) => ({
      symbol: r.symbol,
      market: r.market,
      target_pct: r.target_pct || "0",
    }));
    try {
      const res = await previewMutation.mutateAsync({
        targets: payload,
        account_id: accountId ?? undefined,
        min_trade_value: minTradeValue || "100",
      });
      setResult(res);
    } catch (e) {
      setError(mapPreviewError(e, tr));
    }
  }

  /**
   * Build the request payload using the same `targets` shape that produced
   * the visible preview. We re-serialize from current state (not the
   * preview response) so the server's re-compute uses identical input —
   * mirroring exactly what the user saw.
   */
  function buildRequest() {
    return {
      targets: targets.map((r) => ({
        symbol: r.symbol,
        market: r.market,
        target_pct: r.target_pct || "0",
      })) as RebalanceTarget[],
      account_id: accountId ?? undefined,
      min_trade_value: minTradeValue || "100",
    };
  }

  async function handleExecute() {
    setError(null);
    setConfirmOpen(false);
    try {
      const res = await executeMutation.mutateAsync(buildRequest());
      setExecuteResult(res);
    } catch (e) {
      setError(mapExecuteError(e, tr));
    }
  }

  const selectedAccount = useMemo(
    () => accounts.find((a) => a.id === accountId) ?? null,
    [accounts, accountId],
  );
  const tradesToExecute = result?.suggested_trades ?? [];
  // Execute button visibility: per backend contract, account_id is REQUIRED
  // for /execute (preview supports aggregate mode but execute does not),
  // and we must have at least one trade — otherwise the button is a no-op.
  const canExecute =
    accountId != null && tradesToExecute.length > 0 && !executeResult;

  // ── render helpers ───────────────────────────────────────────────────

  function renderCurrentTable() {
    if (open.length === 0) {
      return (
        <div
          style={{
            padding: 12,
            fontSize: 12,
            color: "var(--text-muted)",
            border: "1px solid var(--border-subtle)",
          }}
        >
          —
        </div>
      );
    }
    return (
      <div
        style={{
          border: "1px solid var(--border-subtle)",
          maxHeight: 220,
          overflowY: "auto",
        }}
      >
        <table style={{ width: "100%", borderCollapse: "collapse" }}>
          <thead>
            <tr style={{ background: "var(--bg-secondary)" }}>
              <th className={tableCellCls} style={{ textAlign: "left" }}>
                {tr("symbol")}
              </th>
              <th className={tableCellCls} style={{ textAlign: "right" }}>
                {tr("qty")}
              </th>
              <th className={tableCellCls} style={{ textAlign: "right" }}>
                {tr("value")}
              </th>
              <th className={tableCellCls} style={{ textAlign: "right" }}>
                {tr("current_pct")}
              </th>
            </tr>
          </thead>
          <tbody>
            {open.map((p) => {
              const v = Number(p.last_price ?? 0) * Number(p.qty);
              const pct = totalValue > 0 ? (v / totalValue) * 100 : 0;
              return (
                <tr key={`${p.symbol}|${p.market}`}>
                  <td className={tableCellCls}>{p.symbol}</td>
                  <td className={tableCellCls} style={{ textAlign: "right" }}>
                    {Number(p.qty).toLocaleString()}
                  </td>
                  <td className={tableCellCls} style={{ textAlign: "right" }}>
                    {Number.isFinite(v) ? v.toLocaleString() : "—"}
                  </td>
                  <td className={tableCellCls} style={{ textAlign: "right" }}>
                    {pct.toFixed(2)}%
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    );
  }

  function renderTargetTable() {
    return (
      <div
        style={{
          border: "1px solid var(--border-subtle)",
          maxHeight: 220,
          overflowY: "auto",
        }}
      >
        <table style={{ width: "100%", borderCollapse: "collapse" }}>
          <thead>
            <tr style={{ background: "var(--bg-secondary)" }}>
              <th className={tableCellCls} style={{ textAlign: "left" }}>
                {tr("symbol")}
              </th>
              <th className={tableCellCls} style={{ textAlign: "right" }}>
                {tr("target_pct")}
              </th>
            </tr>
          </thead>
          <tbody>
            {targets.map((row, idx) => (
              <tr key={`${row.symbol}|${row.market}`}>
                <td className={tableCellCls}>{row.symbol}</td>
                <td
                  className={tableCellCls}
                  style={{ textAlign: "right", width: 100 }}
                >
                  <input
                    className={inputCls}
                    style={{ textAlign: "right", width: 80 }}
                    value={row.target_pct}
                    onChange={(e) => updateTargetPct(idx, e.target.value)}
                    inputMode="decimal"
                    disabled={isPending}
                  />
                </td>
              </tr>
            ))}
            <tr>
              <td className={tableCellCls} style={{ fontWeight: 700 }}>
                {tr("sum_total")}
              </td>
              <td
                className={tableCellCls}
                style={{
                  textAlign: "right",
                  fontWeight: 700,
                  color: sumValid
                    ? "var(--stock-down)"
                    : "var(--accent-primary)",
                }}
              >
                {sumTargets.toFixed(2)}%
              </td>
            </tr>
          </tbody>
        </table>
      </div>
    );
  }

  function renderSuggestedTrades(trades: SuggestedTrade[]) {
    if (trades.length === 0) {
      return (
        <div
          style={{
            padding: 12,
            fontSize: 12,
            color: "var(--text-muted)",
            border: "1px solid var(--border-subtle)",
          }}
        >
          {tr("no_trades_needed")}
        </div>
      );
    }
    return (
      <div
        style={{
          border: "1px solid var(--border-subtle)",
          maxHeight: 240,
          overflowY: "auto",
        }}
      >
        <table style={{ width: "100%", borderCollapse: "collapse" }}>
          <thead>
            <tr style={{ background: "var(--bg-secondary)" }}>
              <th className={tableCellCls} style={{ textAlign: "left" }}>
                {tr("symbol")}
              </th>
              <th className={tableCellCls} style={{ textAlign: "center" }}>
                {/* action */}
              </th>
              <th className={tableCellCls} style={{ textAlign: "right" }}>
                {tr("qty")}
              </th>
              <th className={tableCellCls} style={{ textAlign: "right" }}>
                {tr("value")}
              </th>
              {onApplyTrade && (
                <th className={tableCellCls} style={{ textAlign: "center" }}>
                  {/* apply col */}
                </th>
              )}
            </tr>
          </thead>
          <tbody>
            {trades.map((trd) => {
              const isBuy = trd.action === "BUY";
              return (
                <tr
                  key={`${trd.symbol}|${trd.market}|${trd.action}`}
                  title={trd.rationale}
                >
                  <td className={tableCellCls}>{trd.symbol}</td>
                  <td
                    className={tableCellCls}
                    style={{
                      textAlign: "center",
                      color: isBuy
                        ? "var(--stock-up)"
                        : "var(--stock-down)",
                      fontWeight: 700,
                    }}
                  >
                    {isBuy ? tr("buy_label") : tr("sell_label")}
                  </td>
                  <td className={tableCellCls} style={{ textAlign: "right" }}>
                    {Number(trd.qty).toLocaleString(undefined, {
                      maximumFractionDigits: 4,
                    })}
                  </td>
                  <td className={tableCellCls} style={{ textAlign: "right" }}>
                    {Number(trd.estimated_value).toLocaleString(undefined, {
                      maximumFractionDigits: 2,
                    })}
                  </td>
                  {onApplyTrade && (
                    <td
                      className={tableCellCls}
                      style={{ textAlign: "center" }}
                    >
                      <ClippedButton
                        variant="cyan-ghost"
                        size="sm"
                        onClick={() => onApplyTrade(trd)}
                      >
                        →
                      </ClippedButton>
                    </td>
                  )}
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    );
  }

  function renderSkipped(skipped: SkippedTrade[]) {
    if (skipped.length === 0) return null;
    return (
      <div
        style={{
          marginTop: 8,
          padding: "8px 10px",
          background: "var(--card-hover)",
          fontSize: 11,
          color: "var(--text-muted)",
        }}
      >
        <strong style={{ color: "var(--foreground)" }}>
          {tr("skipped_trades")}:
        </strong>{" "}
        {skipped
          .map((s) => {
            const reasonKey =
              s.reason === "below_min_trade_value"
                ? tr("skip_reason_below_min")
                : s.reason === "exit_below_min_trade_value"
                  ? tr("skip_reason_exit_below_min")
                  : s.reason.startsWith("missing_price")
                    ? tr("skip_reason_missing_price")
                    : s.reason;
            return `${s.symbol} (${reasonKey})`;
          })
          .join(", ")}
      </div>
    );
  }

  function renderExecuteSummary(res: RebalanceExecuteResponse) {
    return (
      <div
        style={{
          marginTop: 12,
          border: "1px solid var(--border-subtle)",
          padding: 12,
          background: "var(--card-hover)",
        }}
      >
        <div
          style={{
            fontSize: 11,
            fontWeight: 700,
            color: "var(--text-muted)",
            textTransform: "uppercase",
            letterSpacing: "0.1em",
            marginBottom: 8,
          }}
        >
          {tr("execute_result")}
        </div>
        <div
          style={{
            display: "flex",
            gap: 16,
            fontSize: 12,
            fontFamily: "monospace",
            marginBottom: 8,
          }}
        >
          <span style={{ color: "var(--stock-up)" }}>
            {tr("executed_count")}: <strong>{res.executed.length}</strong>
          </span>
          <span style={{ color: "var(--text-muted)" }}>
            {tr("skipped_count")}: <strong>{res.skipped.length}</strong>
          </span>
          <span
            style={{
              color:
                res.failed.length > 0
                  ? "var(--accent-primary)"
                  : "var(--text-muted)",
            }}
          >
            {tr("failed_count")}: <strong>{res.failed.length}</strong>
          </span>
        </div>
        <div
          style={{
            fontSize: 11,
            color: "var(--text-muted)",
            marginBottom: res.failed.length > 0 ? 8 : 0,
          }}
        >
          {tr("total_executed_value")}:{" "}
          <span style={{ color: "var(--foreground)", fontFamily: "monospace" }}>
            {Number(res.total_executed_value).toLocaleString(undefined, {
              maximumFractionDigits: 2,
            })}
          </span>
        </div>
        {res.failed.length > 0 && (
          <div
            style={{
              borderTop: "1px solid var(--border-subtle)",
              paddingTop: 8,
              fontSize: 11,
            }}
          >
            <strong
              style={{
                color: "var(--accent-primary)",
                display: "block",
                marginBottom: 4,
              }}
            >
              {tr("failed_trades")}:
            </strong>
            <ul style={{ margin: 0, paddingLeft: 16, color: "var(--text-muted)" }}>
              {res.failed.map((f, i) => (
                <li key={`${f.symbol}|${f.action}|${i}`}>
                  {f.symbol} ({f.action}) — {f.error_code}
                  {f.message ? `: ${f.message}` : ""}
                </li>
              ))}
            </ul>
          </div>
        )}
      </div>
    );
  }

  function renderFinalAlloc(result: RebalanceResponse) {
    const entries = Object.entries(result.final_allocation_pct).sort(
      ([, a], [, b]) => Number(b) - Number(a),
    );
    if (entries.length === 0) return null;
    return (
      <div style={{ marginTop: 12 }}>
        <div
          style={{
            fontSize: 11,
            fontWeight: 700,
            color: "var(--text-muted)",
            textTransform: "uppercase",
            letterSpacing: "0.1em",
            marginBottom: 6,
          }}
        >
          {tr("final_allocation")}
        </div>
        <div
          style={{
            display: "flex",
            flexWrap: "wrap",
            gap: 6,
            fontSize: 11,
            fontFamily: "monospace",
          }}
        >
          {entries.map(([k, v]) => {
            const [symbol] = k.split("|");
            return (
              <span
                key={k}
                style={{
                  padding: "3px 8px",
                  background: "var(--bg-secondary)",
                  border: "1px solid var(--border-subtle)",
                }}
              >
                {symbol}: {Number(v).toFixed(2)}%
              </span>
            );
          })}
        </div>
        <div
          style={{
            marginTop: 6,
            fontSize: 11,
            color: "var(--text-muted)",
          }}
        >
          {tr("cash_residual")}:{" "}
          <span style={{ color: "var(--foreground)", fontFamily: "monospace" }}>
            {Number(result.cash_residual).toLocaleString(undefined, {
              maximumFractionDigits: 2,
            })}
          </span>
        </div>
      </div>
    );
  }

  // ── main render ──────────────────────────────────────────────────────

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
          maxWidth: 880,
          maxHeight: "92vh",
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
            marginBottom: 6,
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
            {tr("title")}
          </span>
          <button
            onClick={onClose}
            disabled={isPending}
            aria-label={tr("close_btn")}
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
        <div
          style={{
            marginBottom: 16,
            fontSize: 11,
            color: "var(--text-muted)",
          }}
        >
          {tr("subtitle")}
        </div>

        {/* Account selector + min trade value */}
        <div
          style={{
            display: "grid",
            gridTemplateColumns: "1fr 1fr",
            gap: 12,
            marginBottom: 16,
          }}
        >
          <div>
            <label className={labelCls}>
              {(t.holdings as { actions?: { add_account?: string } })?.actions
                ?.add_account ?? "Account"}
            </label>
            <select
              className={inputCls}
              style={{ padding: "6px 8px" }}
              value={accountId ?? ""}
              onChange={(e) =>
                setAccountId(e.target.value ? Number(e.target.value) : null)
              }
              disabled={isPending}
            >
              <option value="">— all —</option>
              {accounts.map((a) => (
                <option key={a.id} value={a.id}>
                  {a.name} ({a.currency})
                </option>
              ))}
            </select>
          </div>
          <div>
            <label className={labelCls}>{tr("min_trade_value")}</label>
            <input
              className={inputCls}
              style={{ padding: "6px 8px" }}
              value={minTradeValue}
              onChange={(e) => setMinTradeValue(e.target.value)}
              inputMode="decimal"
              disabled={isPending}
            />
          </div>
        </div>

        {/* Two-column current / target */}
        <div
          style={{
            display: "grid",
            gridTemplateColumns: "1fr 1fr",
            gap: 12,
            marginBottom: 12,
          }}
        >
          <div>
            <label className={labelCls}>{tr("current_holdings")}</label>
            {renderCurrentTable()}
          </div>
          <div>
            <label className={labelCls}>{tr("target_allocation")}</label>
            {renderTargetTable()}
          </div>
        </div>

        {/* Error banner */}
        {error && (
          <div
            role="alert"
            style={{
              marginBottom: 12,
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

        {/* Preview button */}
        <div
          style={{ display: "flex", gap: 8, marginBottom: 16 }}
        >
          <ClippedButton
            variant="cyan-ghost"
            size="md"
            onClick={handlePreview}
            disabled={isPending || !sumValid}
          >
            {isPending ? tr("computing") : tr("preview_btn")}
          </ClippedButton>
          <ClippedButton
            variant="white-solid"
            size="md"
            onClick={onClose}
            disabled={isPending}
          >
            {tr("cancel_btn")}
          </ClippedButton>
        </div>

        {/* Results */}
        {result && (
          <div>
            <label className={labelCls}>{tr("suggested_trades")}</label>
            {renderSuggestedTrades(result.suggested_trades)}
            {/* Asymmetry: RebalanceResponse.skipped_trades is typed as
                Record<string, unknown>[] on the wire (legacy looseness),
                while RebalanceExecuteResponse.skipped uses the proper
                SkippedTrade schema. Runtime shape is the same — cast. */}
            {renderSkipped(result.skipped_trades as unknown as SkippedTrade[])}
            {renderFinalAlloc(result)}
            {/* Execute button — visible only when we have suggestions AND
                an account_id (backend 422 without one). Hidden once the
                execute call returned (the summary takes its place). */}
            {canExecute && (
              <div
                style={{
                  display: "flex",
                  gap: 8,
                  marginTop: 12,
                  justifyContent: "flex-end",
                }}
              >
                <ClippedButton
                  variant="cyan-ghost"
                  size="md"
                  onClick={() => setConfirmOpen(true)}
                  disabled={isPending}
                >
                  {tr("execute_btn")}
                </ClippedButton>
              </div>
            )}
            {/* Hint when execute is unavailable because no account selected. */}
            {tradesToExecute.length > 0 &&
              accountId == null &&
              !executeResult && (
                <div
                  style={{
                    marginTop: 12,
                    padding: "8px 12px",
                    background: "var(--card-hover)",
                    fontSize: 11,
                    color: "var(--text-muted)",
                    border: "1px solid var(--border-subtle)",
                  }}
                >
                  {tr("execute_requires_account")}
                </div>
              )}
            {executeResult && renderExecuteSummary(executeResult)}
          </div>
        )}
      </div>

      {/* Confirmation modal — blocks accidental click on execute. */}
      {confirmOpen && (
        <div
          role="dialog"
          aria-modal="true"
          style={{
            position: "fixed",
            inset: 0,
            background: "rgba(0,0,0,0.6)",
            backdropFilter: "blur(4px)",
            zIndex: 1100,
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            padding: 16,
          }}
          onClick={(e) =>
            e.target === e.currentTarget &&
            !executeMutation.isPending &&
            setConfirmOpen(false)
          }
        >
          <div
            style={{
              background: "var(--glass-bg)",
              border: "1px solid var(--border-color)",
              width: "100%",
              maxWidth: 440,
              padding: 24,
              boxShadow: "var(--glass-shadow)",
              backgroundImage: "var(--glass-gradient)",
            }}
          >
            <div
              style={{
                fontSize: 14,
                fontWeight: 700,
                color: "var(--foreground)",
                letterSpacing: "-0.04em",
                textTransform: "uppercase",
                marginBottom: 12,
              }}
            >
              {tr("confirm_title")}
            </div>
            <div
              style={{
                fontSize: 12,
                color: "var(--text-muted)",
                marginBottom: 16,
                lineHeight: 1.6,
              }}
            >
              {tr("confirm_message")
                .replace("{count}", String(tradesToExecute.length))
                .replace(
                  "{account}",
                  selectedAccount?.name ?? String(accountId ?? ""),
                )}
            </div>
            {result && (
              <div
                style={{
                  fontSize: 11,
                  color: "var(--text-muted)",
                  marginBottom: 16,
                  padding: "8px 12px",
                  background: "var(--bg-secondary)",
                  border: "1px solid var(--border-subtle)",
                  fontFamily: "monospace",
                }}
              >
                {tr("confirm_total_value")}:{" "}
                <span style={{ color: "var(--foreground)" }}>
                  {tradesToExecute
                    .reduce(
                      (sum, t) =>
                        sum +
                        (Number.isFinite(Number(t.estimated_value))
                          ? Number(t.estimated_value)
                          : 0),
                      0,
                    )
                    .toLocaleString(undefined, { maximumFractionDigits: 2 })}
                </span>
              </div>
            )}
            <div
              style={{
                display: "flex",
                gap: 8,
                justifyContent: "flex-end",
              }}
            >
              <ClippedButton
                variant="white-solid"
                size="md"
                onClick={() => setConfirmOpen(false)}
                disabled={executeMutation.isPending}
              >
                {tr("cancel_btn")}
              </ClippedButton>
              <ClippedButton
                variant="cyan-ghost"
                size="md"
                onClick={handleExecute}
                disabled={executeMutation.isPending}
              >
                {executeMutation.isPending
                  ? tr("executing")
                  : tr("confirm_btn")}
              </ClippedButton>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
