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
export { FilerListCard } from "./filer-list-card";
export { FilerListResponsive } from "./filer-list-responsive";
export {
  InstitutionalHoldingsTable,
  type InstitutionalHoldingsTableProps,
} from "./holdings-table";
export {
  InstitutionalHoldingsCardList,
  type InstitutionalHoldingsCardListProps,
} from "./holdings-card-list";
export { InstitutionalHoldingsTableResponsive } from "./holdings-table-responsive";
export { DiffView, type DiffViewProps } from "./diff-view";
export { RefreshButton, type RefreshButtonProps } from "./refresh-button";
export {
  HoldingsTimeline,
  type HoldingsTimelineProps,
} from "./holdings-timeline";
export { TopMovers, type TopMoversProps } from "./top-movers";

// Inline browser (default-view search + subscribe surface)
export { FilerBrowser, type FilerBrowserProps } from "./filer-browser";

// Modals
export { FilerSearchModal } from "./filer-search-modal";
export { BulkSubscribeModal } from "./bulk-subscribe-modal";
export {
  MultiFilerCompareModal,
  type MultiFilerCompareModalProps,
} from "./multi-filer-compare-modal";
