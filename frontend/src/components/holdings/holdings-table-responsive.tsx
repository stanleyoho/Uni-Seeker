"use client";

/**
 * Holdings Table Responsive — Phase 7 mobile/desktop switch.
 *
 * Pure CSS responsive wrapper around the desktop table and the new
 * mobile card list. We render BOTH trees and let Tailwind toggle which
 * one is visible — this keeps SSR markup deterministic (no viewport
 * sniffing on the server) and lets the user resize between layouts
 * without React having to remount either tree.
 *
 * Breakpoint: Tailwind `md` (≥ 768 px) — chosen because the table's
 * minimum legible width with the U4 column-hiding rules in place is
 * roughly 720 px. Below that the desktop layout still scrolled
 * horizontally; the card list eliminates the scroll entirely.
 *
 * Both children accept the same `HoldingsTableProps` shape so callers
 * can swap `<HoldingsTable />` for `<HoldingsTableResponsive />` with
 * zero prop edits.
 */

import { HoldingsTable, type HoldingsTableProps } from "./holdings-table";
import { HoldingsCardList } from "./holdings-card-list";

export function HoldingsTableResponsive(props: HoldingsTableProps) {
  return (
    <>
      <div className="hidden md:block">
        <HoldingsTable {...props} />
      </div>
      <div className="block md:hidden">
        <HoldingsCardList {...props} />
      </div>
    </>
  );
}
