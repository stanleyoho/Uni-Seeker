"use client";

/**
 * Institutional Holdings Table Responsive — mobile/desktop switch.
 *
 * Mirrors `components/holdings/holdings-table-responsive.tsx`. Renders
 * the existing desktop table at `md+` and swaps in the new card list
 * below `md`. Both children consume the same
 * `InstitutionalHoldingsTableProps` shape, so callers can drop this in
 * with no prop changes.
 */

import {
  InstitutionalHoldingsTable,
  type InstitutionalHoldingsTableProps,
} from "./holdings-table";
import { InstitutionalHoldingsCardList } from "./holdings-card-list";

export function InstitutionalHoldingsTableResponsive(
  props: InstitutionalHoldingsTableProps,
) {
  return (
    <>
      <div className="hidden md:block">
        <InstitutionalHoldingsTable {...props} />
      </div>
      <div className="block md:hidden">
        <InstitutionalHoldingsCardList {...props} />
      </div>
    </>
  );
}
