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

import { useState } from "react";
import { useI18n } from "@/i18n/context";
import { AmbientBackground } from "@/components/stratos/ambient";
import { GlassPanel, ClippedButton } from "@/components/stratos/primitives";
import {
  AccountSwitcher,
  AccountModal,
  AddHoldingDividendModal,
  AddHoldingTradeModal,
  BulkActionsBar,
  HoldingsKpiRow,
  HoldingsTable,
  PositionsEmptyState,
} from "@/components/holdings";
import {
  useHoldingAccounts,
  useHoldingPositions,
  useUserHoldingSummary,
} from "@/hooks/use-holdings";
import type { HoldingAccount } from "@/lib/api-client";

type AccountModalState =
  | { mode: "create" }
  | { mode: "edit"; account: HoldingAccount };

export default function HoldingsPage() {
  const { t } = useI18n();

  /* ----------------------------- State ----------------------------- */
  const [selectedAccountId, setSelectedAccountId] = useState<number | null>(
    null,
  );
  const [selectedSymbols, setSelectedSymbols] = useState<string[]>([]);
  const [tradeModalOpen, setTradeModalOpen] = useState(false);
  const [dividendModalOpen, setDividendModalOpen] = useState(false);
  const [accountModalState, setAccountModalState] =
    useState<AccountModalState | null>(null);

  /* ----------------------------- Data ------------------------------ */
  const { data: accounts, isLoading: accountsLoading } = useHoldingAccounts();
  const { data: positionsRes, isLoading: positionsLoading } =
    useHoldingPositions(selectedAccountId ?? undefined);
  const { data: summary, isLoading: summaryLoading } = useUserHoldingSummary();

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

        {/* KPI row */}
        <section>
          <HoldingsKpiRow summary={summary} loading={summaryLoading} />
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
    </main>
  );
}
