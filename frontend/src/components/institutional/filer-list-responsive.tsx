"use client";

/**
 * Filer List Responsive — mobile/desktop switch.
 *
 * Mirrors `holdings-table-responsive.tsx`. Desktop (md+) gets the
 * sortable `FilerList`; below md, the `FilerListCard` deck takes over.
 * Same prop contract (`FilerListProps`) for both.
 */

import { FilerList, type FilerListProps } from "./filer-list";
import { FilerListCard } from "./filer-list-card";

export function FilerListResponsive(props: FilerListProps) {
  return (
    <>
      <div className="hidden md:block">
        <FilerList {...props} />
      </div>
      <div className="block md:hidden">
        <FilerListCard {...props} />
      </div>
    </>
  );
}
