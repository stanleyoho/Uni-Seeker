// Legacy `訊號掃描` route. The Filter + Signal Scanner tabs were merged
// into a single unified `/research` workflow (templates + condition
// builder + numeric thresholds + tooltips). This file stays as a
// server-side permanent redirect so any old bookmark / external link
// lands on the new page.
import { permanentRedirect } from "next/navigation";

export default function LegacyScannerRedirect(): never {
  permanentRedirect("/research");
}
