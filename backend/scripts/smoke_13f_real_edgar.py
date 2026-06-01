"""Real-EDGAR smoke run for 5 well-known 13F filers.

Hits SEC EDGAR API (rate-limited 10/sec, User-Agent required) to verify
Phase 1 13F backend handles real-world data: namespace variants, amendments,
edge cases in CUSIP / value / share fields.

Usage:
  cd backend && uv run python scripts/smoke_13f_real_edgar.py

Exit 0 if all 5 filers parsed successfully (no fail), exit 1 otherwise.

Notes:
- Read-only (no DB writes; just fetches XML and parses).
- Reports per-filer outcomes + aggregate stats.
- Rate-limited via EdgarRateLimiter to be polite to SEC.
- ParseError / fetch error is *flagged* in the report, not mock-fixed.
"""

from __future__ import annotations

import asyncio
import re
import sys
import traceback
from typing import Any

from app.modules.institutional.diff import compute_diff
from app.modules.institutional.edgar_client import (
    EdgarClient,
    EdgarTransientError,
    FilingMetadata,
)
from app.modules.institutional.parser import (
    ParseError,
    parse_infotable_xml,
    summarize_filing,
)

# ───────────────────────── known filer list ─────────────────────────

# Hardcoded CIKs come from SEC EDGAR's public submissions index.
# Situational Awareness LP CIK is unknown / may not exist yet — we
# discover it via search_filers_by_name and gracefully N/A if missing.
KNOWN_FILERS: list[dict[str, Any]] = [
    {"name": "Situational Awareness", "cik": None},  # Leopold Aschenbrenner
    {"name": "Berkshire Hathaway", "cik": "0001067983"},
    {"name": "ARK Investment Management", "cik": "0001697748"},
    {"name": "Renaissance Technologies", "cik": "0001037389"},
    {"name": "Citadel Advisors", "cik": "0001423053"},
]

_XMLNS_RE = re.compile(r'xmlns(?::[\w-]+)?="([^"]+)"')


def _extract_namespaces(xml: str) -> set[str]:
    """Pull every xmlns URI from the first 4KB of the XML body."""
    head = xml[:4096]
    return set(_XMLNS_RE.findall(head))


# ───────────────────────── per-filer smoke ─────────────────────────


async def smoke_run_filer(client: EdgarClient, filer: dict[str, Any]) -> dict[str, Any]:
    """Run the smoke pipeline for one filer; return a result dict.

    Never raises — exceptions are captured into ``result["errors"]``.
    """
    result: dict[str, Any] = {
        "name": filer["name"],
        "cik": filer.get("cik"),
        "status": "pending",
        "filings_found": 0,
        "filings_parsed_ok": 0,
        "holdings_parsed": 0,
        "errors": [],
        "namespace_variants_seen": set(),
        "amendment_filings": 0,
        "options_holdings": 0,
        "filings_with_holdings": 0,
        "diff_summary": {},
    }

    try:
        # 1. CIK lookup if missing (SALP path)
        if not filer.get("cik"):
            try:
                hits = await client.search_filers_by_name(filer["name"], limit=10)
            except Exception as exc:
                result["status"] = "fail"
                result["errors"].append(f"search_error: {exc.__class__.__name__}: {exc}")
                return result
            if not hits:
                result["status"] = "n/a"
                result["errors"].append(f"no_13F-HR_filings_for_query={filer['name']!r}")
                return result
            # First hit by relevance.
            result["cik"] = hits[0].cik
            result["resolved_name"] = hits[0].name

        # 2. List filings (latest 4 quarters: 13F-HR + 13F-HR/A)
        try:
            filings: list[FilingMetadata] = await client.list_filings_for_filer(
                result["cik"], max_count=4
            )
        except Exception as exc:
            result["status"] = "fail"
            result["errors"].append(f"list_filings_error: {exc.__class__.__name__}: {exc}")
            return result

        result["filings_found"] = len(filings)
        if not filings:
            result["status"] = "n/a"
            result["errors"].append("no_recent_13F_filings")
            return result

        # 3. Parse each filing
        parsed_per_filing: list[dict[str, Any]] = []
        for filing in filings:
            if filing.form_type == "13F-HR/A":
                result["amendment_filings"] += 1
            try:
                xml = await client.fetch_filing_xml(filing.raw_xml_url)
            except EdgarTransientError as exc:
                result["errors"].append(f"fetch_transient_{filing.accession_number}: {exc}")
                continue
            except Exception as exc:
                result["errors"].append(
                    f"fetch_error_{filing.accession_number}: {exc.__class__.__name__}: {exc}"
                )
                continue

            # Capture every distinct xmlns URI for visibility.
            for ns in _extract_namespaces(xml):
                result["namespace_variants_seen"].add(ns)

            try:
                holdings = parse_infotable_xml(xml)
            except ParseError as exc:
                # ParseError on primary_doc.xml is *expected* — primary_doc is
                # the cover sheet, not the infotable. We don't have a separate
                # listing of secondary docs in the recent API; flag and move on.
                result["errors"].append(
                    f"parse_error_{filing.accession_number} "
                    f"(form={filing.form_type}, url={filing.raw_xml_url}): {exc}"
                )
                continue
            except Exception as exc:
                result["errors"].append(
                    f"parse_unexpected_{filing.accession_number}: {exc.__class__.__name__}: {exc}"
                )
                continue

            summary = summarize_filing(holdings)
            result["filings_parsed_ok"] += 1
            result["holdings_parsed"] += len(holdings)
            result["options_holdings"] += sum(1 for h in holdings if h.put_call is not None)
            if holdings:
                result["filings_with_holdings"] += 1
                parsed_per_filing.append(
                    {"filing": filing, "holdings": holdings, "summary": summary}
                )

        # 4. Diff latest 2 non-empty filings (if available)
        if len(parsed_per_filing) >= 2:
            # parsed_per_filing preserves the listing order (newest first).
            curr = parsed_per_filing[0]["holdings"]
            prev = parsed_per_filing[1]["holdings"]
            try:
                changes = compute_diff(prev, curr)
                result["diff_summary"] = {
                    "NEW": sum(1 for c in changes if c.change_type.value == "NEW"),
                    "INCREASED": sum(1 for c in changes if c.change_type.value == "INCREASED"),
                    "DECREASED": sum(1 for c in changes if c.change_type.value == "DECREASED"),
                    "EXITED": sum(1 for c in changes if c.change_type.value == "EXITED"),
                    "UNCHANGED": sum(1 for c in changes if c.change_type.value == "UNCHANGED"),
                }
            except Exception as exc:
                result["errors"].append(f"diff_error: {exc.__class__.__name__}: {exc}")

        # 5. Final status: pass iff we have at least one filing parsed successfully
        # with holdings AND no fetch/parse errors at all.
        if result["filings_parsed_ok"] == 0:
            result["status"] = "fail"
        elif result["errors"]:
            result["status"] = "partial"
        else:
            result["status"] = "pass"
        return result

    except Exception as exc:
        result["status"] = "fail"
        result["errors"].append(
            f"top_level: {exc.__class__.__name__}: {exc}\n"
            + "".join(traceback.format_exception(exc))
        )
        return result


# ───────────────────────── reporting ─────────────────────────


def _print_report(results: list[dict[str, Any]]) -> tuple[int, int, int, int]:
    print("=" * 80)
    print("13F Real-EDGAR Smoke Run Report")
    print("=" * 80)

    for r in results:
        status = str(r["status"]).upper()
        cik = r.get("cik") or "?"
        resolved = f" (resolved={r['resolved_name']!r})" if r.get("resolved_name") else ""
        print(f"\n[{status}] {r['name']} (CIK {cik}){resolved}")
        print(f"  filings_found       : {r['filings_found']}")
        print(f"  filings_parsed_ok   : {r['filings_parsed_ok']}")
        print(f"  filings_with_hold.  : {r['filings_with_holdings']}")
        print(f"  holdings_parsed     : {r['holdings_parsed']}")
        print(f"  amendment_filings   : {r['amendment_filings']}")
        print(f"  options_holdings    : {r['options_holdings']}")
        if r["namespace_variants_seen"]:
            print(f"  xmlns variants seen : {len(r['namespace_variants_seen'])} unique URI(s)")
            for ns in sorted(r["namespace_variants_seen"]):
                print(f"      - {ns}")
        if r["diff_summary"]:
            print(f"  Q-over-Q diff       : {r['diff_summary']}")
        if r["errors"]:
            print(f"  ERRORS ({len(r['errors'])} total, showing up to 5):")
            for err in r["errors"][:5]:
                # Only first line of each error for readability.
                first_line = str(err).splitlines()[0]
                print(f"      ! {first_line}")

    passed = sum(1 for r in results if r["status"] == "pass")
    partial = sum(1 for r in results if r["status"] == "partial")
    failed = sum(1 for r in results if r["status"] == "fail")
    na = sum(1 for r in results if r["status"] == "n/a")

    print()
    print("=" * 80)
    print(f"AGGREGATE: {passed} pass / {partial} partial / {failed} fail / {na} n/a")
    print("=" * 80)
    return passed, partial, failed, na


# ───────────────────────── entrypoint ─────────────────────────


async def _amain() -> int:
    ua = "Uni-Seeker smoke-test stanly7768@gmail.com"
    async with EdgarClient(user_agent=ua) as client:
        # Sequential per-filer to keep wall-clock predictable and avoid
        # piling many in-flight bursts on the rate-limiter. Within a filer
        # we still fetch ≤4 filings — under the 10/sec budget easily.
        results: list[dict[str, Any]] = []
        for filer in KNOWN_FILERS:
            r = await smoke_run_filer(client, filer)
            results.append(r)

    _, _, failed, _ = _print_report(results)
    # Exit 1 if any hard failure. Partial / n/a are not script failures.
    return 0 if failed == 0 else 1


def main() -> None:
    sys.exit(asyncio.run(_amain()))


if __name__ == "__main__":
    main()
