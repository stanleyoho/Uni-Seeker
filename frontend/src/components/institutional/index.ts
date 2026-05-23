/**
 * Institutional 13F — component barrel.
 *
 * Single import path for `src/app/institutional/page.tsx`. Mirrors the
 * shape of `components/holdings/index.ts`.
 */

// Types & helpers
export {
  toDecimal,
  fmtCompact,
  fmtInt,
  fmtPct,
  changeTypeColor,
  changeTypeLabel,
  holdingDisplaySymbol,
  type F13Filer,
  type F13Filing,
  type F13Holding,
  type F13HoldingChange,
  type F13ChangeType,
} from "./types";

// Components
export { FilerList, type FilerListProps } from "./filer-list";
export {
  InstitutionalHoldingsTable,
  type InstitutionalHoldingsTableProps,
} from "./holdings-table";
export { DiffView, type DiffViewProps } from "./diff-view";
export { RefreshButton, type RefreshButtonProps } from "./refresh-button";
export {
  HoldingsTimeline,
  type HoldingsTimelineProps,
} from "./holdings-timeline";
export { TopMovers, type TopMoversProps } from "./top-movers";

// Modals
export { FilerSearchModal } from "./filer-search-modal";
export { BulkSubscribeModal } from "./bulk-subscribe-modal";
export {
  MultiFilerCompareModal,
  type MultiFilerCompareModalProps,
} from "./multi-filer-compare-modal";
