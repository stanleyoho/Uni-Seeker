"use client";

import Link from "next/link";
import { usePathname, useSearchParams } from "next/navigation";

interface SubTab {
  /** Target href for the tab link. May include `?key=value` query string. */
  href: string;
  label: string;
  /**
   * Optional query-param predicate that must also match for this tab to be
   * considered active. When set, the tab is active iff the pathname matches
   * AND the live URL has `?<key>=<value>`. Used by `/research` and
   * `/journal` to host secondary tabs as query-param views on the root
   * path rather than sibling routes — without this, the default
   * pathname-only match would keep the first tab highlighted even when
   * a `?tab=...` is present.
   */
  activeQuery?: { key: string; value: string };
  /**
   * Marks this tab as the "default" of a query-multiplex group — active
   * when the pathname matches and NO tracked `activeQuery.key` is set
   * to a non-empty value. The flag is documentation-driven (the
   * predicate below auto-detects the same condition from `href`); it's
   * surfaced for readers of the tab config without changing behaviour.
   */
  defaultWhenQueryMissing?: boolean;
}

export function SubTabs({ tabs }: { tabs: SubTab[] }) {
  const pathname = usePathname();
  const searchParams = useSearchParams();

  // Collect every query key any tab cares about, so the "default tab"
  // predicate can check "no tracked key set" in O(k) without re-walking
  // the tab list per render. Today this is small (≤1 key per route
  // group) but the helper future-proofs the rule.
  const trackedKeys = new Set<string>();
  for (const t of tabs) {
    if (t.activeQuery) trackedKeys.add(t.activeQuery.key);
  }

  const isActive = (tab: SubTab) => {
    // Strip the query off the href before comparing to the live
    // pathname — `usePathname()` never includes the query string.
    const hrefPath = tab.href.split("?")[0];

    if (tab.activeQuery) {
      // Query-scoped tab: pathname must match AND ?key=value present.
      return (
        pathname === hrefPath &&
        searchParams.get(tab.activeQuery.key) === tab.activeQuery.value
      );
    }

    // "Default" tab of a query-multiplex group: pathname matches AND
    // none of the tracked query keys are set to a non-empty value.
    // Falls back to legacy semantics for tab groups that don't use
    // the query-multiplex pattern at all.
    if (trackedKeys.size > 0 && tabs[0]?.href.split("?")[0] === hrefPath) {
      if (pathname !== hrefPath) return false;
      for (const k of trackedKeys) {
        if (searchParams.get(k)) return false;
      }
      return true;
    }

    // Legacy behaviour for non-multiplex tab groups:
    //   - first tab: exact match (so /journal doesn't stay highlighted
    //     when the user drills to /journal/accounts/123).
    //   - other tabs: prefix match (so /research/low-base/ABC keeps the
    //     Low-Base tab lit on a nested route).
    if (tabs[0]?.href === tab.href) {
      return pathname === hrefPath;
    }
    return pathname.startsWith(hrefPath);
  };

  return (
    <div
      className="flex items-center gap-1 px-6 py-2"
      style={{
        background: "var(--bg-secondary)",
        borderBottom: "1px solid var(--border-subtle)",
      }}
    >
      {tabs.map((tab) => (
        <Link
          key={tab.href}
          href={tab.href}
          className={`px-4 py-1.5 text-[13px] font-medium transition-colors duration-200 ${
            isActive(tab)
              ? "text-[var(--foreground)]"
              : "text-[var(--text-muted)] hover:text-[var(--foreground)]"
          }`}
          style={{
            clipPath: isActive(tab)
              ? "polygon(0 0, calc(100% - 8px) 0, 100% 8px, 100% 100%, 8px 100%, 0 calc(100% - 8px))"
              : undefined,
            background: isActive(tab) ? "var(--card-hover)" : undefined,
          }}
        >
          {tab.label}
        </Link>
      ))}
    </div>
  );
}
