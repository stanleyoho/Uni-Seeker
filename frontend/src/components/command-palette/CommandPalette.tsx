"use client";

/**
 * Global ⌘K Command Palette.
 *
 * Per Stanley's home polish brief — Koyfin / TradingView / OpenBB all ship
 * this pattern: a single search box with multiple item kinds in one ranked
 * list (ticker, sector, page). Mounted once via the root layout so the
 * shortcut works on every route.
 *
 * Items:
 *   - Pages    — hard-coded surface map (always available, filtered locally).
 *   - Sectors  — pulled from useHeatmap; activate → /heatmap?focus=...
 *   - Tickers  — type-ahead via searchStocks (existing /api/v1/stocks/search).
 *
 * Keyboard:
 *   - ⌘K / Ctrl+K → toggle (open if closed, close if open).
 *   - Esc          → close.
 *   - ↑ / ↓        → move active item.
 *   - Enter        → activate.
 *
 * The legacy `src/components/command-palette.tsx` (search-only modal that
 * accepts open/onClose as props) is migrated to dispatch the
 * `CMDK_OPEN_EVENT` CustomEvent — see `src/components/stratos/header.tsx`.
 */

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { useHeatmap } from "@/hooks/use-market-data";
import { searchStocks, type StockSearchResult } from "@/lib/api-client";
import { useI18n } from "@/i18n/context";
import { QuoteRow } from "@/components/quote-row";

/** CustomEvent name dispatched by the header search button to open the palette. */
export const CMDK_OPEN_EVENT = "uni-seeker:open-cmdk";

interface PageItem {
  kind: "page";
  id: string;
  label: string;
  href: string;
}

interface SectorItem {
  kind: "sector";
  id: string;
  label: string;
  changePercent: number;
  href: string;
}

interface TickerItem {
  kind: "ticker";
  id: string;
  symbol: string;
  name: string;
  market: string;
  href: string;
}

type PaletteItem = PageItem | SectorItem | TickerItem;

/**
 * Hard-coded surface map. Each entry corresponds to a real route under
 * src/app/. Update when adding new top-level pages so users can jump.
 */
const PAGES: PageItem[] = [
  { kind: "page", id: "home", label: "首頁 / Markets", href: "/" },
  { kind: "page", id: "research", label: "Research", href: "/research" },
  { kind: "page", id: "lowbase", label: "Research · 低基期", href: "/research/low-base" },
  { kind: "page", id: "compare", label: "Research · Compare", href: "/research/compare" },
  { kind: "page", id: "institutional", label: "機構持倉", href: "/institutional" },
  { kind: "page", id: "portfolio", label: "Portfolio", href: "/portfolio" },
  { kind: "page", id: "holdings", label: "Holdings", href: "/holdings" },
  { kind: "page", id: "heatmap", label: "Heatmap", href: "/heatmap" },
  { kind: "page", id: "journal", label: "Trade Journal", href: "/journal" },
  { kind: "page", id: "alerts", label: "Alerts", href: "/alerts" },
  { kind: "page", id: "login", label: "Login", href: "/login" },
];

/** True when the current platform is macOS (or jsdom's darwin host). */
function isMac(): boolean {
  if (typeof navigator === "undefined") return false;
  return (
    /mac/i.test(navigator.platform) ||
    /mac|darwin/i.test(navigator.userAgent)
  );
}

/** True when the keyboard event corresponds to ⌘K (mac) or Ctrl+K (others). */
export function isCmdK(e: KeyboardEvent): boolean {
  if (e.key !== "k" && e.key !== "K") return false;
  return isMac() ? e.metaKey : e.ctrlKey;
}

/** Case-insensitive substring filter used for Page + Sector items. */
function matches(haystack: string, needle: string): boolean {
  if (!needle) return true;
  return haystack.toLowerCase().includes(needle.toLowerCase());
}

export interface CommandPaletteProps {
  /**
   * When provided, controls the open state externally. When omitted,
   * the palette manages its own open state via ⌘K + CustomEvent.
   */
  open?: boolean;
  onClose?: () => void;
}

export function CommandPalette(props: CommandPaletteProps = {}) {
  const { open: openProp, onClose: onCloseProp } = props;
  const router = useRouter();
  const { t } = useI18n();
  const inputRef = useRef<HTMLInputElement>(null);
  const listRef = useRef<HTMLDivElement>(null);
  const debounceRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  const [internalOpen, setInternalOpen] = useState(false);
  const isControlled = openProp !== undefined;
  const open = isControlled ? !!openProp : internalOpen;

  const close = useCallback(() => {
    if (isControlled) {
      onCloseProp?.();
    } else {
      setInternalOpen(false);
    }
  }, [isControlled, onCloseProp]);

  // Heatmap data is used to build sector items. The hook does background
  // refetch, so this is cheap even when the palette is closed.
  const { data: heatmap } = useHeatmap();

  const [query, setQuery] = useState("");
  const [tickerResults, setTickerResults] = useState<StockSearchResult[]>([]);
  const [tickerLoading, setTickerLoading] = useState(false);
  const [selectedIndex, setSelectedIndex] = useState(0);

  /* ---------------------------------------------------------------------- */
  /* Global keyboard handling: ⌘K toggles open (only in uncontrolled mode);   */
  /* CustomEvent CMDK_OPEN_EVENT opens (used by the header search button).   */
  /* ---------------------------------------------------------------------- */
  useEffect(() => {
    if (isControlled) return;
    const onKey = (e: KeyboardEvent) => {
      if (isCmdK(e)) {
        e.preventDefault();
        setInternalOpen((v) => !v);
      }
    };
    const onCustom = () => setInternalOpen(true);
    window.addEventListener("keydown", onKey);
    window.addEventListener(CMDK_OPEN_EVENT, onCustom);
    return () => {
      window.removeEventListener("keydown", onKey);
      window.removeEventListener(CMDK_OPEN_EVENT, onCustom);
    };
  }, [isControlled]);

  /* ---------------------------------------------------------------------- */
  /* Reset local state every time the palette opens. Same rationale as the   */
  /* legacy palette: opening is a parent/global trigger; the input ref needs */
  /* the same DOM node across opens for focus management.                    */
  /* ---------------------------------------------------------------------- */
  useEffect(() => {
    if (open) {
      // eslint-disable-next-line react-hooks/set-state-in-effect -- reset modal-local state on open transition; remount alternative breaks focus management
      setQuery("");
      setTickerResults([]);
      setSelectedIndex(0);
      setTickerLoading(false);
      requestAnimationFrame(() => {
        inputRef.current?.focus();
      });
    }
  }, [open]);

  /* ---------------------------------------------------------------------- */
  /* Debounced ticker search. Pages + Sectors are filtered locally so they   */
  /* update instantly; tickers require a backend roundtrip.                  */
  /* ---------------------------------------------------------------------- */
  useEffect(() => {
    if (!open) return;
    if (debounceRef.current) clearTimeout(debounceRef.current);

    if (!query.trim()) {
      // eslint-disable-next-line react-hooks/set-state-in-effect -- clear ticker results when input goes empty
      setTickerResults([]);
      setTickerLoading(false);
      return;
    }

    setTickerLoading(true);
    debounceRef.current = setTimeout(async () => {
      try {
        const data = await searchStocks(query, 8);
        setTickerResults(data);
      } catch {
        setTickerResults([]);
      } finally {
        setTickerLoading(false);
      }
    }, 250);

    return () => {
      if (debounceRef.current) clearTimeout(debounceRef.current);
    };
  }, [query, open]);

  /* ---------------------------------------------------------------------- */
  /* Build the ranked item list. Page+Sector are filtered in-memory; ticker  */
  /* items come from state populated by the debounced search.                */
  /* ---------------------------------------------------------------------- */
  const items: PaletteItem[] = useMemo(() => {
    const q = query.trim();
    const pageItems = PAGES.filter((p) => matches(p.label, q));

    const sectorItems: SectorItem[] = (heatmap?.sectors ?? [])
      .filter((s) => matches(s.industry, q))
      .slice(0, 8)
      .map((s) => ({
        kind: "sector" as const,
        id: `sector:${s.industry}`,
        label: s.industry,
        changePercent: Number(s.avg_change_percent) || 0,
        href: `/heatmap?focus=${encodeURIComponent(s.industry)}`,
      }));

    const tickerItems: TickerItem[] = tickerResults.map((r) => ({
      kind: "ticker" as const,
      id: `ticker:${r.symbol}`,
      symbol: r.symbol,
      name: r.name,
      market: r.market,
      href: `/stocks/${encodeURIComponent(r.symbol)}`,
    }));

    // Order: tickers first when there's a query (most users press ⌘K to
    // jump to a stock), then sectors, then pages. With no query, pages
    // lead so the user sees the surface map.
    if (q) {
      return [...tickerItems, ...sectorItems, ...pageItems];
    }
    return [...pageItems, ...sectorItems];
  }, [query, heatmap?.sectors, tickerResults]);

  /* Clamp selected index whenever the list shrinks. */
  useEffect(() => {
    if (selectedIndex >= items.length) {
      // eslint-disable-next-line react-hooks/set-state-in-effect -- clamp the active row when filtering shrinks the list
      setSelectedIndex(items.length > 0 ? 0 : -1);
    }
  }, [items.length, selectedIndex]);

  /* Scroll the active row into view. */
  useEffect(() => {
    if (selectedIndex < 0 || !listRef.current) return;
    const nodes = listRef.current.querySelectorAll("[data-cmdk-item]");
    nodes[selectedIndex]?.scrollIntoView({ block: "nearest" });
  }, [selectedIndex]);

  const activate = useCallback(
    (item: PaletteItem) => {
      close();
      router.push(item.href);
    },
    [close, router],
  );

  const handleKeyDown = (e: React.KeyboardEvent<HTMLInputElement>) => {
    if (e.key === "ArrowDown") {
      e.preventDefault();
      setSelectedIndex((prev) =>
        items.length === 0 ? -1 : prev < items.length - 1 ? prev + 1 : 0,
      );
    } else if (e.key === "ArrowUp") {
      e.preventDefault();
      setSelectedIndex((prev) =>
        items.length === 0 ? -1 : prev > 0 ? prev - 1 : items.length - 1,
      );
    } else if (e.key === "Enter") {
      e.preventDefault();
      const target = items[selectedIndex];
      if (target) activate(target);
    } else if (e.key === "Escape") {
      e.preventDefault();
      close();
    }
  };

  if (!open) return null;

  return (
    <div
      data-testid="command-palette"
      className="fixed inset-0 z-[100] flex items-start justify-center pt-[15vh]"
      role="dialog"
      aria-modal="true"
      aria-label="Command palette"
    >
      <div
        className="absolute inset-0 backdrop-blur-[8px]"
        style={{ background: "rgba(0,0,0,0.7)" }}
        onClick={close}
        aria-hidden="true"
      />

      <div
        className="relative w-full max-w-xl mx-4 border rounded-xl overflow-hidden animate-slide-down"
        style={{
          background: "var(--glass-bg)",
          borderColor: "var(--border-color)",
          boxShadow: "var(--glass-shadow)",
          backdropFilter: "var(--glass-blur)",
          WebkitBackdropFilter: "var(--glass-blur)",
        }}
      >
        {/* Input row */}
        <div
          className="flex items-center gap-3 px-4 py-3"
          style={{
            background: "var(--bg-secondary)",
            borderBottom: "1px solid var(--border-color)",
          }}
        >
          <svg
            className="w-4 h-4 text-[var(--text-muted)] shrink-0"
            fill="none"
            stroke="currentColor"
            viewBox="0 0 24 24"
            aria-hidden="true"
          >
            <path
              strokeLinecap="round"
              strokeLinejoin="round"
              strokeWidth={2}
              d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z"
            />
          </svg>
          <input
            ref={inputRef}
            data-testid="command-palette-input"
            type="text"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            onKeyDown={handleKeyDown}
            placeholder={
              t.search?.placeholder ?? "Type a ticker, sector, or page..."
            }
            className="flex-1 bg-transparent text-[var(--foreground)] text-sm placeholder-[var(--text-muted)] outline-none mono-nums"
            autoComplete="off"
            spellCheck={false}
          />
          <kbd className="hidden sm:inline-flex items-center justify-center text-[10px] text-[var(--text-muted)] border border-[var(--border-color)] rounded px-1.5 py-0.5 font-mono leading-none">
            ESC
          </kbd>
        </div>

        {/* Results */}
        <div
          ref={listRef}
          data-testid="command-palette-list"
          className="max-h-[400px] overflow-y-auto overscroll-contain"
          role="listbox"
        >
          {tickerLoading && (
            <div className="px-4 py-2 text-[11px] text-[var(--text-muted)]">
              搜尋中...
            </div>
          )}

          {items.length === 0 && !tickerLoading && (
            <div
              data-testid="command-palette-empty"
              className="px-4 py-6 text-center text-[var(--text-muted)] text-xs"
            >
              {t.search?.noResults ?? "No results"}
            </div>
          )}

          {items.map((item, index) => (
            <PaletteRow
              key={item.id}
              item={item}
              active={index === selectedIndex}
              onActivate={() => activate(item)}
            />
          ))}
        </div>

        {/* Footer */}
        <div className="flex items-center gap-3 px-4 py-2 border-t border-[var(--border-color)] text-[10px] text-[var(--text-muted)]">
          <span className="flex items-center gap-1">
            <kbd className="inline-flex items-center justify-center border border-[var(--border-color)] rounded px-1 py-0.5 font-mono leading-none">
              &uarr;&darr;
            </kbd>
            navigate
          </span>
          <span className="flex items-center gap-1">
            <kbd className="inline-flex items-center justify-center border border-[var(--border-color)] rounded px-1 py-0.5 font-mono leading-none">
              &crarr;
            </kbd>
            select
          </span>
          <span className="flex items-center gap-1">
            <kbd className="inline-flex items-center justify-center border border-[var(--border-color)] rounded px-1 py-0.5 font-mono leading-none">
              esc
            </kbd>
            close
          </span>
          <span className="ml-auto">{items.length} 個項目</span>
        </div>
      </div>
    </div>
  );
}

/* ---------------------------------------------------------------------- */
/* Row renderer per item kind.                                            */
/* ---------------------------------------------------------------------- */

function PaletteRow({
  item,
  active,
  onActivate,
}: {
  item: PaletteItem;
  active: boolean;
  onActivate: () => void;
}) {
  if (item.kind === "ticker") {
    return (
      <QuoteRow
        symbol={item.symbol}
        name={item.name}
        market={item.market}
        onClick={onActivate}
        role="option"
        ariaSelected={active}
        dataAttributes={{ "data-cmdk-item": true, "data-cmdk-kind": "ticker" }}
        className={
          active
            ? "bg-[var(--card-active)]"
            : "hover:bg-[var(--card-hover)]"
        }
        style={
          active ? { borderLeft: "2px solid var(--accent-primary)" } : undefined
        }
      />
    );
  }

  // Sector + Page share the same row chrome — a single line with a kind
  // chip on the left and label on the right.
  const kindLabel = item.kind === "sector" ? "SECTOR" : "PAGE";
  const kindColor =
    item.kind === "sector" ? "var(--accent-cyan)" : "var(--text-muted)";

  return (
    <button
      type="button"
      role="option"
      aria-selected={active}
      data-cmdk-item
      data-cmdk-kind={item.kind}
      onClick={onActivate}
      className={[
        "flex items-center gap-3 w-full text-left px-3 py-2",
        active
          ? "bg-[var(--card-active)]"
          : "hover:bg-[var(--card-hover)]",
      ].join(" ")}
      style={
        active ? { borderLeft: "2px solid var(--accent-primary)" } : undefined
      }
    >
      <span
        className="text-[9px] font-bold tracking-[0.08em] px-1.5 py-0.5 border rounded shrink-0"
        style={{ color: kindColor, borderColor: "var(--border-color)" }}
      >
        {kindLabel}
      </span>
      <span className="text-[13px] text-[var(--foreground)] truncate flex-1">
        {item.label}
      </span>
      {item.kind === "sector" && (
        <span
          className="text-[11px] tabular-nums shrink-0 font-semibold"
          style={{
            color:
              item.changePercent >= 0
                ? "var(--stock-up)"
                : "var(--stock-down)",
          }}
        >
          {item.changePercent >= 0 ? "+" : ""}
          {item.changePercent.toFixed(2)}%
        </span>
      )}
    </button>
  );
}

export default CommandPalette;
