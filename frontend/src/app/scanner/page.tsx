// Legacy `/scanner` route. The Filter + Signal Scanner tabs were merged
// into a unified `/research` workflow (PR #108). This page mirrors the
// existing `/research/scanner` redirect so root-level bookmarks /
// external links also land on the new page rather than 404.
import { permanentRedirect } from "next/navigation";

export default function LegacyScannerRedirect(): never {
  permanentRedirect("/research");
}
