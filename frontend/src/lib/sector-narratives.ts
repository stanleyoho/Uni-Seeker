/**
 * Static industry-chain narratives for TW market sectors.
 *
 * Surfaces on home sector cards as an info-popover (Ⓘ icon) and, for
 * the top 3 hot sectors, a one-sentence sub-headline. Hardcoded for
 * the top 16 known TW industries; future iteration could move to a
 * CMS / DB / LLM-generated daily refresh.
 *
 * The JSON is the single source of truth — this module is a typed
 * accessor so callers don't have to remember the fallback dance.
 */
import raw from "./sector-narratives.json";

interface SectorNarrativesFile {
  _meta: {
    version: number;
    updated: string;
    description: string;
    fallback: string;
  };
  // dynamic keys for industry names
  [industry: string]: string | SectorNarrativesFile["_meta"];
}

const file = raw as SectorNarrativesFile;

/**
 * Return the full narrative for an industry name, or the generic
 * fallback line when we don't have a hardcoded entry yet.
 *
 * The fallback always reads naturally — never returns null — so
 * callers can render unconditionally without an "if".
 */
export function getSectorNarrative(industry: string | undefined | null): string {
  if (!industry) return file._meta.fallback;
  const entry = file[industry];
  if (typeof entry === "string") return entry;
  return file._meta.fallback;
}

/**
 * Whether the industry has a hand-written narrative (vs fallback).
 * Used to decide whether to surface the sub-headline on FocusTile —
 * we don't want to print the generic fallback line as a teaser.
 */
export function hasSectorNarrative(industry: string | undefined | null): boolean {
  if (!industry) return false;
  const entry = file[industry];
  return typeof entry === "string";
}

/**
 * Return the first sentence (split on 。) of an industry's narrative,
 * used as the FocusTile sub-headline for hot top-3 sectors. Falls
 * back to empty string when no narrative — caller should branch on
 * `hasSectorNarrative` first to skip the line entirely.
 */
export function getSectorLeadSentence(industry: string | undefined | null): string {
  const full = getSectorNarrative(industry);
  if (!full) return "";
  // Split on Chinese full-stop. `。` is the standard sentence terminator
  // in the narratives JSON; trim and return the first non-empty chunk.
  const first = full.split("。")[0]?.trim() ?? "";
  return first ? `${first}。` : full;
}
