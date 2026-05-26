"use client";

/**
 * Holdings Page — Phase 3 assembly.
 *
 * Composes X1 (hooks) + X2 (components) + X3 (modals) into the live
 * `/holdings` route. Layout follows the STRATOS dark-luxe terminal
 * style; `AmbientBackground` lives at the page level. `StratosHeader`
 * is provided by the root layout, so it is NOT repeated here.
 *
 * Phase 1 decisions:
 *   - `selectedAccountId === null` means "all accounts" (matches
 *     AccountSwitcher's null-sentinel contract).
 *   - BulkActionsBar's delete is a stub (clears selection only). Real
 *     position-level delete is a Phase 4+ operation; positions are
 *     derived from trades, so deletion must walk the trade ledger.
 *   - No client-side auth gate: hooks return empty data when unauthed,
 *     and protected endpoints surface their own 401/403 via apiFetch.
 *     This matches the existing `journal` / `portfolio` pages.
 */

import { useCallback, useState, useSyncExternalStore } from "react";
import { useI18n } from "@/i18n/context";
import { AmbientBackground } from "@/components/stratos/ambient";
import { GlassPanel, ClippedButton } from "@/components/stratos/primitives";
import {
  AccountSwitcher,
  AccountModal,
  AddHoldingDividendModal,
  AddHoldingTradeModal,
  BulkActionsBar,
  CsvExportDropdown,
  CsvImportModal,
  CurrencySwitcher,
  HoldingsKpiRow,
  HoldingsTableResponsive,
  PositionsEmptyState,
  PullToRefreshWrapper,
  RebalanceModal,
} from "@/components/holdings";
import {
  useHoldingAccounts,
  useHoldingPositions,
  useUserHoldingSummary,
} from "@/hooks/use-holdings";
import { useAuth } from "@/contexts/auth-context";
import {
  SUPPORTED_CURRENCIES,
  type Currency,
  type HoldingAccount,
} from "@/lib/api-client";

// localStorage key for the user's preferred base currency. Scoped to
// `uni-seeker-` to avoid collision with future Stanley-ecosystem apps
// sharing the same origin.
const LS_BASE_CURRENCY = "uni-seeker-base-currency";
const CURRENCY_CHANGE_EVENT = "uni-seeker:base-currency-change";

function isCurrency(v: string | null): v is Currency {
  return v !== null && (SUPPORTED_CURRENCIES as string[]).includes(v);
}

function readStoredCurrency(): Currency {
  if (typeof window === "undefined") return "TWD";
  try {
    const saved = window.localStorage.getItem(LS_BASE_CURRENCY);
    return isCurrency(saved) ? saved : "TWD";
  } catch {
    return "TWD";
  }
}

function subscribeStoredCurrency(callback: () => void): () => void {
  if (typeof window === "undefined") return () => {};
  window.addEventListener("storage", callback);
  window.addEventListener(CURRENCY_CHANGE_EVENT, callback);
  return () => {
    window.removeEventListener("storage", callback);
    window.removeEventListener(CURRENCY_CHANGE_EVENT, callback);
  };
}

// SSR snapshot matches the historical default so the first HTML matches
// the server render even when localStorage already holds a non-TWD
// value -- the subscription triggers a client-only re-render to apply
// the saved preference.
const getServerCurrencySnapshot = (): Currency => "TWD";

// Tier gate — "pro" and above (e.g. "enterprise") get multi-currency.
// Backend gates with the `multi_currency_summary` feature flag; we
// mirror the tier_limits.yaml allowlist here so the UI doesn't fetch a
// guaranteed-403.
function isProTier(tier: string | undefined): boolean {
  if (!tier) return false;
  const t = tier.toLowerCase();
  return t === "pro" || t === "enterprise";
}

type AccountModalState =
  | { mode: "create" }
  | { mode: "edit"; account: HoldingAccount };

export default function HoldingsPage() {
  const { t } = useI18n();
  const { user } = useAuth();

  /* ----------------------------- State ----------------------------- */
  const [selectedAccountId, setSelectedAccountId] = useState<number | null>(
    null,
  );
  const [selectedSymbols, setSelectedSymbols] = useState<string[]>([]);
  const [tradeModalOpen, setTradeModalOpen] = useState(false);
  const [dividendModalOpen, setDividendModalOpen] = useState(false);
  const [csvImportModalOpen, setCsvImportModalOpen] = useState(false);
  const [rebalanceModalOpen, setRebalanceModalOpen] = useState(false);
  const [accountModalState, setAccountModalState] =
    useState<AccountModalState | null>(null);

  // Base currency for KPIs + summary. Sourced from localStorage via
  // useSyncExternalStore so the "TWD -> saved value" hydration step
  // happens without a setState-in-effect bootstrap. SSR snapshot is
  // "TWD" so we never issue a multi-currency request before the client
  // takes over (the gate below also checks selectedCurrency !== "TWD").
  const selectedCurrency = useSyncExternalStore(
    subscribeStoredCurrency,
    readStoredCurrency,
    getServerCurrencySnapshot,
  );
  const [upsellHint, setUpsellHint] = useState<string | null>(null);

  const handleSelectCurrency = useCallback((c: Currency) => {
    if (typeof window === "undefined") return;
    try {
      window.localStorage.setItem(LS_BASE_CURRENCY, c);
    } catch {
      /* quota / private mode */
    }
    window.dispatchEvent(new Event(CURRENCY_CHANGE_EVENT));
  }, []);

  const multiCurrencyAvailable = isProTier(user?.tier);

  /* ----------------------------- Data ------------------------------ */
  const {
    data: accounts,
    isLoading: accountsLoading,
    refetch: refetchAccounts,
  } = useHoldingAccounts();
  const {
    data: positionsRes,
    isLoading: positionsLoading,
    refetch: refetchPositions,
  } = useHoldingPositions(selectedAccountId ?? undefined);
  // For Pro+ users with a non-TWD selection, send `base_currency=`.
  // For everyone else, fall back to the legacy single-currency call so
  // the backend doesn't 403 us on the multi-currency feature flag.
  // SSR snapshot is "TWD" so the `!== "TWD"` clause inherently guards
  // against issuing a multi-currency request before the client store
  // has resolved -- no extra hydration flag required.
  const useMultiCurrencyCall =
    multiCurrencyAvailable && selectedCurrency !== "TWD";
  const {
    data: summary,
    isLoading: summaryLoading,
    refetch: refetchSummary,
  } = useUserHoldingSummary(
    useMultiCurrencyCall ? selectedCurrency : undefined,
  );

  // Pull-to-refresh handler (R.2 — Phase 8). Re-runs every page-level
  // query in parallel and resolves only when all three settle so the
  // mobile spinner stays visible for the full refresh window.
  const handlePullRefresh = async () => {
    await Promise.all([
      refetchAccounts(),
      refetchPositions(),
      refetchSummary(),
    ]);
  };

  const accountList: HoldingAccount[] = accounts ?? [];
  // Wire PositionResponse marks `qty` and `realized_pnl` as nullable
  // (e.g. fully closed positions). UI's local HoldingPosition expects
  // non-null strings for display ergonomics; coerce null → "0" at the
  // boundary so UI doesn't have to null-guard every cell.
  const positions = (positionsRes?.positions ?? []).map((p) => ({
    ...p,
    qty: p.qty ?? "0",
    realized_pnl: p.realized_pnl ?? "0",
  }));

  const holdingsTitle =
    (t.holdings && (t.holdings as { title?: string }).title) ?? "持倉對賬";
  const addAccountLabel =
    (t.holdings &&
      (t.holdings as { actions?: { add_account?: string } }).actions
        ?.add_account) ??
    "新增帳戶";
  const addTradeLabel =
    (t.holdings &&
      (t.holdings as { actions?: { add_trade?: string } }).actions
        ?.add_trade) ??
    "記錄交易";
  const addDividendLabel =
    (t.holdings &&
      (t.holdings as { actions?: { add_dividend?: string } }).actions
        ?.add_dividend) ??
    "記錄配息";
  const rebalanceLabel =
    (t.holdings &&
      (t.holdings as { actions?: { rebalance?: string } }).actions
        ?.rebalance) ??
    "再平衡";

  // Tier gate: rebalancing is Pro-only (see config/tier_limits.yaml).
  // Hide the button entirely for Free/Basic — the click would 403 anyway,
  // and we already surface the upgrade hint elsewhere on the page.
  const rebalanceAvailable = isProTier(user?.tier);

  const currencyTitle =
    (t.holdings &&
      (t.holdings as { currency?: { title?: string } }).currency?.title) ??
    "基準幣別";
  const currencyUpgradeHint =
    (t.holdings &&
      (t.holdings as { currency?: { upgrade_hint?: string } }).currency
        ?.upgrade_hint) ??
    "升級 Pro 解鎖多幣別 portfolio";
  const byCurrencyLabel =
    (t.holdings &&
      (t.holdings as { kpi?: { by_currency?: string } }).kpi?.by_currency) ??
    "幣別分布";

  /* ----------------------------- Render ---------------------------- */
  return (
    <main className="relative flex-1 overflow-y-auto">
      <AmbientBackground />

      <PullToRefreshWrapper onRefresh={handlePullRefresh}>
      <div className="relative max-w-[1440px] mx-auto px-3 sm:px-4 lg:px-6 py-4 lg:py-6 space-y-4 lg:space-y-6">
        {/* Page title */}
        <div className="flex items-center justify-between">
          <h1
            className="text-[18px] lg:text-[20px] font-bold uppercase"
            style={{
              color: "var(--foreground)",
              letterSpacing: "-0.04em",
            }}
          >
            {holdingsTitle}
          </h1>
        </div>

        {/* Currency switcher (Round 10 Z1) */}
        <section data-tour="holdings-currency">
          <CurrencySwitcher
            selectedCurrency={selectedCurrency}
            onSelect={handleSelectCurrency}
            multiCurrencyAvailable={multiCurrencyAvailable}
            title={currencyTitle}
            upgradeHint={currencyUpgradeHint}
            onUpsellAttempt={(ccy) => {
              setUpsellHint(
                `${currencyUpgradeHint}（${ccy}）`,
              );
              // Auto-dismiss after 3s — non-blocking inline toast.
              window.setTimeout(() => setUpsellHint(null), 3000);
            }}
          />
          {upsellHint && (
            <div
              role="status"
              aria-live="polite"
              style={{
                marginTop: 6,
                padding: "6px 10px",
                fontSize: 12,
                color: "var(--accent-cyan)",
                border: "1px solid var(--accent-cyan)",
                background: "var(--card-hover)",
              }}
            >
              {upsellHint}
            </div>
          )}
        </section>

        {/* KPI row */}
        <section data-tour="holdings-kpi">
          <HoldingsKpiRow
            summary={summary}
            loading={summaryLoading}
            displayCurrency={selectedCurrency}
            byCurrencyLabel={byCurrencyLabel}
          />
        </section>

        {/* Account switcher + action buttons */}
        <section
          style={{
            display: "flex",
            flexDirection: "column",
            gap: 12,
          }}
        >
          <AccountSwitcher
            accounts={accountList}
            selectedAccountId={selectedAccountId}
            onSelect={setSelectedAccountId}
            loading={accountsLoading}
          />
          <div className="grid grid-cols-2 sm:flex sm:flex-wrap gap-2">
            <div data-tour="holdings-add-account" style={{ display: "contents" }}>
              <ClippedButton
                variant="cyan-ghost"
                size="md"
                onClick={() => setAccountModalState({ mode: "create" })}
              >
                + {addAccountLabel}
              </ClippedButton>
            </div>
            <div data-tour="holdings-add-trade" style={{ display: "contents" }}>
              <ClippedButton
                variant="red-solid"
                size="md"
                onClick={() => setTradeModalOpen(true)}
              >
                + {addTradeLabel}
              </ClippedButton>
            </div>
            <ClippedButton
              variant="cyan-ghost"
              size="md"
              onClick={() => setDividendModalOpen(true)}
            >
              + {addDividendLabel}
            </ClippedButton>
            <ClippedButton
              variant="cyan-ghost"
              size="md"
              onClick={() => setCsvImportModalOpen(true)}
            >
              ↑ 匯入 CSV
            </ClippedButton>
            {rebalanceAvailable && (
              <ClippedButton
                variant="cyan-ghost"
                size="md"
                onClick={() => setRebalanceModalOpen(true)}
              >
                ⇄ {rebalanceLabel}
              </ClippedButton>
            )}
            <CsvExportDropdown selectedAccountId={selectedAccountId} />
          </div>
        </section>

        {/* Positions table */}
        <section data-tour="holdings-positions">
          {positions.length === 0 && !positionsLoading ? (
            <GlassPanel noPadding>
              <PositionsEmptyState
                onAddTrade={() => setTradeModalOpen(true)}
              />
            </GlassPanel>
          ) : (
            <HoldingsTableResponsive
              positions={positions}
              loading={positionsLoading}
              selectedSymbols={selectedSymbols}
              onSelectionChange={setSelectedSymbols}
              // Phase 8 R.1 — mobile swipe-left on a card reveals a
              // "Remove" action. We don't have a position-level delete
              // mutation (positions are derived from trades on the
              // backend; see BulkActionsBar.onDeleteSelected stub
              // below), so the swipe action funnels the symbol into the
              // existing bulk-selection state. The floating
              // BulkActionsBar then surfaces with its own delete path.
              // Keeps the gesture demonstrably wired without inventing
              // a back-end contract.
              onSwipeRemove={(symbol) =>
                setSelectedSymbols((prev) =>
                  prev.includes(symbol) ? prev : [...prev, symbol],
                )
              }
            />
          )}
        </section>
      </div>
      </PullToRefreshWrapper>

      {/* Floating bulk-actions bar (returns null when count === 0) */}
      <BulkActionsBar
        selectedCount={selectedSymbols.length}
        onClearSelection={() => setSelectedSymbols([])}
        onDeleteSelected={() => {
          /*
           * Phase 1 stub: position-level delete is intentionally a no-op
           * besides clearing the selection. Positions are derived from
           * trades on the backend, so a true "delete" requires walking
           * each symbol's trade ledger — that lives in Phase 4+ alongside
           * the trade-history drawer.
           */
          setSelectedSymbols([]);
        }}
      />

      {/* Modals */}
      {tradeModalOpen && (
        <AddHoldingTradeModal
          accounts={accountList}
          defaultAccountId={selectedAccountId ?? undefined}
          onClose={() => setTradeModalOpen(false)}
        />
      )}
      {dividendModalOpen && (
        <AddHoldingDividendModal
          accounts={accountList}
          defaultAccountId={selectedAccountId ?? undefined}
          onClose={() => setDividendModalOpen(false)}
        />
      )}
      {accountModalState && (
        <AccountModal
          mode={accountModalState.mode}
          account={
            accountModalState.mode === "edit"
              ? accountModalState.account
              : undefined
          }
          onClose={() => setAccountModalState(null)}
        />
      )}
      {csvImportModalOpen && (
        <CsvImportModal
          accounts={accountList}
          defaultAccountId={selectedAccountId ?? undefined}
          onClose={() => setCsvImportModalOpen(false)}
        />
      )}
      {rebalanceModalOpen && (
        <RebalanceModal
          positions={positions}
          accounts={accountList}
          defaultAccountId={selectedAccountId}
          onClose={() => setRebalanceModalOpen(false)}
        />
      )}
    </main>
  );
}
