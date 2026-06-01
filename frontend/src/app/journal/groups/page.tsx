// Legacy `/journal/groups` route. The groups list was flattened into
// `/journal` as a query-param-driven tab — see
// `frontend/src/app/journal/components/groups-panel.tsx` for the
// moved component and `frontend/src/app/journal/layout.tsx` for the
// SubTabs entry. This file stays as a server-side permanent redirect
// so any old bookmark / external link lands on the new URL.
//
// The dynamic detail route `/journal/groups/[id]` is unaffected —
// detail pages still live where they always did, only the index/list
// view moved.
import { permanentRedirect } from "next/navigation";

export default function LegacyJournalGroupsRedirect(): never {
  permanentRedirect("/journal?tab=groups");
}
