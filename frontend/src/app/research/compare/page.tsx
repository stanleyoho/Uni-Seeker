// Legacy `/research/compare` route. The Compare workflow was merged
// into the unified `/research` page as a query-param-driven tab — see
// `frontend/src/app/research/components/compare-panel.tsx` for the
// moved implementation and `frontend/src/app/research/layout.tsx` for
// the SubTabs entry. This file stays as a server-side permanent
// redirect so any old bookmark / external link lands on the new URL.
//
// `permanentRedirect` emits HTTP 308, the right semantic for "route
// content moved permanently" — distinct from `redirect` (307
// temporary), which `next/navigation` exposes for mid-render redirects
// we expect to undo later (none of those apply here).
import { permanentRedirect } from "next/navigation";

export default function LegacyResearchCompareRedirect(): never {
  permanentRedirect("/research?tab=compare");
}
