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

import { useEffect, useState } from "react";
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
  HoldingsTable,
  PositionsEmptyState,
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

function isCurrency(v: string | null): v is Currency {
  return v !== null && (SUPPORTED_CURRENCIES as string[]).includes(v);
}

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
  const [accountModalState, setAccountModalState] =
    useState<AccountModalState | null>(null);

  // Base currency for KPIs + summary. Defaults to TWD; we then upgrade
  // to localStorage on mount so the SSR pass doesn't differ from the
  // client-side hydration pass (hydration mismatch).
  const [selectedCurrency, setSelectedCurrency] = useState<Currency>("TWD");
  const [currencyHydrated, setCurrencyHydrated] = useState(false);
  const [upsellHint, setUpsellHint] = useState<string | null>(null);

  useEffect(() => {
    if (typeof window === "undefined") return;
    const saved = window.localStorage.getItem(LS_BASE_CURRENCY);
    if (isCurrency(saved)) setSelectedCurrency(saved);
    setCurrencyHydrated(true);
  }, []);

  const handleSelectCurrency = (c: Currency) => {
    setSelectedCurrency(c);
    if (typeof window !== "undefined") {
      window.localStorage.setItem(LS_BASE_CURRENCY, c);
    }
  };

  const multiCurrencyAvailable = isProTier(user?.tier);

  /* ----------------------------- Data ------------------------------ */
  const { data: accounts, isLoading: accountsLoading } = useHoldingAccounts();
  const { data: positionsRes, isLoading: positionsLoading } =
    useHoldingPositions(selectedAccountId ?? undefined);
  // For Pro+ users with a non-TWD selection, send `base_currency=`.
  // For everyone else, fall back to the legacy single-currency call so
  // the backend doesn't 403 us on the multi-currency feature flag.
  const useMultiCurrencyCall =
    currencyHydrated &&
    multiCurrencyAvailable &&
    selectedCurrency !== "TWD";
  const { data: summary, isLoading: summaryLoading } = useUserHoldingSummary(
    useMultiCurrencyCall ? selectedCurrency : undefined,
  );

  const accountList: HoldingAccount[] = accounts ?? [];
  const positions = positionsRes?.positions ?? [];

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

      <div className="relative max-w-[1440px] mx-auto px-6 py-6 space-y-6">
        {/* Page title */}
        <div className="flex items-center justify-between">
          <h1
            className="text-[20px] font-bold uppercase"
            style={{
              color: "var(--foreground)",
              letterSpacing: "-0.04em",
            }}
          >
            {holdingsTitle}
          </h1>
        </div>

        {/* Currency switcher (Round 10 Z1) */}
        <section>
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
        <section>
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
          <div
            style={{
              display: "flex",
              flexWrap: "wrap",
              gap: 8,
            }}
          >
            <ClippedButton
              variant="cyan-ghost"
              size="md"
              onClick={() => setAccountModalState({ mode: "create" })}
            >
              + {addAccountLabel}
            </ClippedButton>
            <ClippedButton
              variant="red-solid"
              size="md"
              onClick={() => setTradeModalOpen(true)}
            >
              + {addTradeLabel}
            </ClippedButton>
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
            <CsvExportDropdown selectedAccountId={selectedAccountId} />
          </div>
        </section>

        {/* Positions table */}
        <section>
          {positions.length === 0 && !positionsLoading ? (
            <GlassPanel noPadding>
              <PositionsEmptyState
                onAddTrade={() => setTradeModalOpen(true)}
              />
            </GlassPanel>
          ) : (
            <HoldingsTable
              positions={positions}
              loading={positionsLoading}
              selectedSymbols={selectedSymbols}
              onSelectionChange={setSelectedSymbols}
            />
          )}
        </section>
      </div>

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
    </main>
  );
}
