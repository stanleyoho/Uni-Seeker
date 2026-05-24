# 13F Real-EDGAR Smoke Run — Backlog Findings

**Run date**: 2026-05-19
**Script**: `backend/scripts/smoke_13f_real_edgar.py`
**Exit code**: 1
**Aggregate**: 0 pass / 0 partial / **5 fail** / 0 n/a

---

## Finding 1 — CRITICAL: EdgarClient fetches XSL-rendered HTML, not raw XML

**Affected filers**: ALL five (Berkshire, ARK, Renaissance, Citadel, Situational Awareness)
**Error**: `ParseError: malformed 13F XML: mismatched tag: line 33, column 2`

### Root cause
`EdgarClient.list_filings_for_filer()` builds `raw_xml_url` by appending the
SEC submissions API's `filings.recent.primaryDocument` field verbatim to the
archive path. For 13F-HR filings, SEC returns:

```
primaryDocument = "xslForm13F_X02/primary_doc.xml"
```

That `xslForm13F_X02/` prefix routes through SEC's XSL stylesheet renderer
which returns an **HTML body** (`<html><head><style>…`) wearing an `.xml`
extension. ElementTree chokes on line 33 (the `<style>` block).

### Real layout (verified with Berkshire `000119312526226661`)
- `Archives/.../primary_doc.xml` — **real cover-sheet XML** (legal, parseable;
  contains `<edgarSubmission>` with `coverPage`, `signatureBlock`. *NO infoTable*).
- `Archives/.../53405.xml` — **the actual `<informationTable>` XML containing
  `<infoTable>` rows** — filename is accession-derived and not directly
  surfaced in the submissions JSON.
- `Archives/.../xslForm13F_X02/primary_doc.xml` — XSL-rendered HTML view
  (what the client is currently fetching).

### Recommended fix (Phase 2 — production-blocking)
Two-step approach inside `EdgarClient.list_filings_for_filer` or a new
`fetch_infotable_xml()` method:

1. **Strip the `xslForm13F_X02/` prefix** when present in `primaryDocument`.
   That gives the real cover-sheet `primary_doc.xml` — useful for filing
   metadata (filing manager name, period, isAmendment flag) but **not**
   for holdings.
2. **Resolve the infotable XML** by either:
   - Fetching the filing index page (`{accession}-index.htm` or the bare
     directory listing) and grep for the `.xml` filename that is NOT
     `primary_doc.xml`; OR
   - Using the JSON index `{accession}-index.json` if SEC publishes one
     (less brittle than HTML scrape).

A clean signature:
```python
async def fetch_infotable_xml(self, filing: FilingMetadata) -> str: ...
async def fetch_coverpage_xml(self, filing: FilingMetadata) -> str: ...
```
keeps the two distinct concerns separated.

### Phase 1 mitigation (optional, lossy)
If we want any Phase 1 production traffic, hardcode the prefix strip and
attempt to enumerate sibling `.xml` files via filing-index scrape. But this
deserves its own ticket — too fragile to ship under "Phase 1 done".

---

## Finding 2 — POSITIVE: CIK discovery for Situational Awareness works

`search_filers_by_name("Situational Awareness")` returned `CIK 0002045724`,
display name "Situational Awareness LP". SALP **has filed 4 × 13F-HR**.
None of them parsed (same root cause as Finding 1), but the lookup pipeline
itself is sound.

**Phase 2 polish**: store the resolved CIK in our config / DB so we don't
search every cron tick.

---

## Finding 3 — POSITIVE: Namespace handling is correctly future-proofed

Every filer returned the same four xmlns URIs (consistent across years and
filers):
- `http://www.sec.gov/edgar/thirteenffiler` (cover sheet root)
- `http://www.sec.gov/edgar/document/thirteenf/informationtable` (infoTable root)
- `http://www.sec.gov/edgar/common` (shared elements like `<ns1:street1>`)
- `http://www.w3.org/2001/XMLSchema-instance` (xsi)

The parser's `{*}infoTable` wildcard search will handle all of these once
Finding 1 is fixed and the *actual* infotable XML reaches it.

---

## Finding 4 — Amendment filings exist in the wild

Berkshire returned 1 × `13F-HR/A` amendment in the latest 4 quarters
(accession `000095012325008361`). The other 4 filers had zero amendments
in this window. Parser would have handled it once the URL bug is fixed,
but worth a Phase 2 integration test once the pipeline runs end-to-end.

---

## Finding 5 — Rate-limiter held up

20 + filings fetched, no 429s, no transient errors. Token bucket worked
as designed against real SEC traffic. No further action.

---

## Recommendations for Phase 2 ticket queue

| Priority | Ticket | Notes |
|---|---|---|
| P0 | Fix `EdgarClient` infotable URL resolution | Production-blocking; current code parses 0 holdings on every real filing |
| P1 | Add `fetch_coverpage_xml()` for amendment metadata | Needed to surface `isAmendment` to UI |
| P2 | Cache resolved CIKs for tracked filers in DB | One-time SALP-style discovery, then steady-state |
| P3 | Add integration test using real (or recorded) Berkshire `informationtable.xml` | Lock down the parser against schemaVersion X0202 |

---

## Top 3 production-readiness observations

1. **The Phase 1 pipeline is structurally sound but fundamentally broken on
   real EDGAR data** — every single filer fails because we are pointing at
   the wrong document. This smoke run paid for itself in 90 seconds.
2. **The parser, diff, and rate-limiter are not at fault** — the bug is
   localized to one URL-construction line in `edgar_client.py`. The fix
   surface area is small but it does change the public contract
   (need to either split `raw_xml_url` into two URLs or introduce
   `fetch_infotable_xml`).
3. **Real EDGAR exposes infrastructure we hadn't modelled**: per-accession
   filing-index pages, multiple co-resident XML files per submission, and
   SEC's XSL stylesheet routing. Phase 2 design should explicitly model
   the filing-document hierarchy, not assume one URL per filing.
