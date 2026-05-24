/**
 * Holdings component barrel — single import path for pages assembled
 * in Round 3 (`src/app/holdings/page.tsx` and friends).
 */

// Types & helpers
export {
  type HoldingAccount,
  type HoldingPosition,
  type HoldingSummary,
  type HoldingMarket,
  toNumber,
  fmt,
  fmtSigned,
  pnlColor,
  pnlDirection,
} from "./types";

// Components
export {
  HoldingsKpiRow,
  type HoldingsKpiRowProps,
} from "./holdings-kpi-row";

export {
  HoldingsTable,
  type HoldingsTableProps,
} from "./holdings-table";

export {
  HoldingsCardList,
  type HoldingsCardListProps,
} from "./holdings-card-list";

export { HoldingsTableResponsive } from "./holdings-table-responsive";

export { PullToRefreshWrapper } from "./pull-to-refresh-wrapper";

export {
  BulkActionsBar,
  type BulkActionsBarProps,
} from "./bulk-actions-bar";

export {
  AccountSwitcher,
  type AccountSwitcherProps,
} from "./account-switcher";

export {
  CurrencySwitcher,
  CURRENCY_SYMBOL,
  type CurrencySwitcherProps,
} from "./currency-switcher";

export {
  PositionsEmptyState,
  type PositionsEmptyStateProps,
} from "./positions-empty-state";

// Modals (X3)
export { AddHoldingTradeModal } from "./add-trade-modal";
export { AddHoldingDividendModal } from "./add-dividend-modal";
export { AccountModal } from "./account-modal";
export { RebalanceModal } from "./rebalance-modal";

// CSV export (Phase 4 tax-export hook)
export {
  CsvExportDropdown,
  type CsvExportDropdownProps,
} from "./csv-export-dropdown";

// CSV import (Phase 4 broker-import hook)
export { CsvImportModal } from "./csv-import-modal";
