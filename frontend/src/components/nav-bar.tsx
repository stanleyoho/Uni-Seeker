"use client";

import { useState, useEffect } from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { useI18n } from "@/i18n/context";
import { useAuth } from "@/contexts/auth-context";
import { useTheme } from "@/contexts/theme-context";
import { CommandPalette } from "@/components/command-palette";

function NavDropdown({
  label,
  links,
  isActive,
}: {
  label: string;
  links: { href: string; label: string }[];
  isActive: (href: string) => boolean;
}) {
  const [open, setOpen] = useState(false);
  const hasActive = links.some((l) => isActive(l.href));

  return (
    <div className="relative">
      <button
        onClick={() => setOpen(!open)}
        onBlur={() => setTimeout(() => setOpen(false), 150)}
        className={`flex items-center gap-0.5 px-3 py-1.5 text-[13px] font-medium rounded-md transition-colors duration-200 ${
          hasActive
            ? "text-[var(--foreground)]"
            : "text-[var(--text-muted)] hover:text-[var(--foreground)]"
        }`}
      >
        {label}
        <svg className={`w-3 h-3 transition-transform duration-200 ${open ? "rotate-180" : ""}`} fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 9l-7 7-7-7" />
        </svg>
        {hasActive && (
          <span className="absolute bottom-0 left-1/2 -translate-x-1/2 w-4 h-[2px] bg-[var(--accent-blue)] rounded-full" />
        )}
      </button>
      {open && (
        <div className="absolute top-full left-0 mt-1 bg-[var(--card-bg)] border border-[var(--border-color)] rounded-lg shadow-xl shadow-black/40 z-50 min-w-[140px] overflow-hidden animate-slide-down">
          {links.map((link) => (
            <Link
              key={link.href}
              href={link.href}
              onClick={() => setOpen(false)}
              aria-current={isActive(link.href) ? "page" : undefined}
              className={`block px-4 py-2 text-[13px] transition-colors duration-150 ${
                isActive(link.href)
                  ? "text-[var(--foreground)] bg-[var(--card-hover)]"
                  : "text-[var(--text-muted)] hover:text-[var(--foreground)] hover:bg-[var(--card-hover)]"
              }`}
            >
              {link.label}
            </Link>
          ))}
        </div>
      )}
    </div>
  );
}

export function NavBar() {
  const { locale, t, setLocale } = useI18n();
  const { user, logout } = useAuth();
  const { theme, setTheme } = useTheme();
  const pathname = usePathname();
  const [mobileOpen, setMobileOpen] = useState(false);
  const [paletteOpen, setPaletteOpen] = useState(false);

  const cycleTheme = () => {
    const next: Record<string, "light" | "system" | "dark"> = {
      dark: "light",
      light: "system",
      system: "dark",
    };
    setTheme(next[theme]);
  };

  const themeIcon = {
    dark: (
      <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24" aria-hidden="true">
        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M20.354 15.354A9 9 0 018.646 3.646 9.003 9.003 0 0012 21a9.003 9.003 0 008.354-5.646z" />
      </svg>
    ),
    light: (
      <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24" aria-hidden="true">
        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 3v1m0 16v1m9-9h-1M4 12H3m15.364 6.364l-.707-.707M6.343 6.343l-.707-.707m12.728 0l-.707.707M6.343 17.657l-.707.707M16 12a4 4 0 11-8 0 4 4 0 018 0z" />
      </svg>
    ),
    system: (
      <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24" aria-hidden="true">
        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9.75 17L9 20l-1 1h8l-1-1-.75-3M3 13h18M5 17h14a2 2 0 002-2V5a2 2 0 00-2-2H5a2 2 0 00-2 2v10a2 2 0 002 2z" />
      </svg>
    ),
  };

  const themeLabel: Record<string, string> = { dark: "Dark", light: "Light", system: "System" };

  const toggleLocale = () => {
    setLocale(locale === "zh-TW" ? "en" : "zh-TW");
  };

  const directLinks = [
    { href: "/", label: t.nav.home },
    { href: "/watchlist", label: t.nav.watchlist },
  ];

  const analysisLinks = [
    { href: "/screener", label: t.nav.screener },
    { href: "/scanner", label: t.nav.scanner },
    { href: "/low-base", label: t.nav.lowBase },
  ];

  const tradingLinks = [
    { href: "/backtest", label: t.nav.backtest },
    { href: "/portfolio", label: t.nav.portfolio },
  ];

  const marketLinks = [
    { href: "/heatmap", label: t.nav.heatmap },
    { href: "/institutional", label: t.nav.institutional },
    { href: "/compare", label: t.nav.compare },
  ];

  const allLinks = [...directLinks, ...analysisLinks, ...tradingLinks, ...marketLinks, { href: "/notifications", label: t.nav.notifications }];

  const isActive = (href: string) => {
    if (href === "/") return pathname === "/";
    return pathname.startsWith(href);
  };

  /* Keyboard shortcut: press F to focus search */
  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      if (e.key === "f" && !e.metaKey && !e.ctrlKey && !e.altKey) {
        const active = document.activeElement;
        if (active && (active.tagName === "INPUT" || active.tagName === "TEXTAREA")) return;
        e.preventDefault();
        setPaletteOpen(true);
      }
    };
    window.addEventListener("keydown", handler);
    return () => window.removeEventListener("keydown", handler);
  }, []);

  return (
    <>
      <nav aria-label="Main navigation" className="nav-border-gradient bg-[var(--background)]/95 backdrop-blur-xl sticky top-0 z-50">
        <div className="max-w-[1440px] mx-auto flex items-center gap-4 px-4 h-12">
          {/* LEFT zone: Logo */}
          <Link
            href="/"
            className="font-bold text-base tracking-tight text-[var(--foreground)] hover:text-[var(--accent-blue)] transition-colors duration-200 shrink-0"
          >
            <span className="gradient-text">Uni-Seeker</span>
          </Link>

          {/* CENTER zone: Nav links + Search bar */}
          <div className="hidden md:flex flex-1 items-center justify-center gap-1">
            {directLinks.map((link) => (
              <Link
                key={link.href}
                href={link.href}
                aria-current={isActive(link.href) ? "page" : undefined}
                className={`relative px-3 py-1.5 text-[13px] font-medium rounded-md transition-colors duration-200 ${
                  isActive(link.href)
                    ? "text-[var(--foreground)]"
                    : "text-[var(--text-muted)] hover:text-[var(--foreground)]"
                }`}
              >
                {link.label}
                {isActive(link.href) && (
                  <span className="absolute bottom-0 left-1/2 -translate-x-1/2 w-4 h-[2px] bg-[var(--accent-blue)] rounded-full" />
                )}
              </Link>
            ))}

            <NavDropdown label={t.nav.analysis} links={analysisLinks} isActive={isActive} />
            <NavDropdown label={t.nav.trading} links={tradingLinks} isActive={isActive} />
            <NavDropdown label={t.nav.marketGroup} links={marketLinks} isActive={isActive} />

            {/* Notifications icon link */}
            <Link
              href="/notifications"
              aria-current={isActive("/notifications") ? "page" : undefined}
              className={`relative px-2 py-1.5 rounded-md transition-colors duration-200 ${
                isActive("/notifications")
                  ? "text-[var(--foreground)]"
                  : "text-[var(--text-muted)] hover:text-[var(--foreground)]"
              }`}
              title={t.nav.notifications}
            >
              <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 17h5l-1.405-1.405A2.032 2.032 0 0118 14.158V11a6.002 6.002 0 00-4-5.659V5a2 2 0 10-4 0v.341C7.67 6.165 6 8.388 6 11v3.159c0 .538-.214 1.055-.595 1.436L4 17h5m6 0v1a3 3 0 11-6 0v-1m6 0H9" />
              </svg>
              {isActive("/notifications") && (
                <span className="absolute bottom-0 left-1/2 -translate-x-1/2 w-4 h-[2px] bg-[var(--accent-blue)] rounded-full" />
              )}
            </Link>

            {/* Search bar (integrated in center zone) */}
            <button className="search-bar hidden lg:flex ml-2" aria-label="Search markets" onClick={() => setPaletteOpen(true)}>
              <svg className="w-3.5 h-3.5 text-[var(--text-muted)]" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z" />
              </svg>
              <span className="text-[var(--text-muted)]">{t.search.placeholder}</span>
              <kbd>F</kbd>
            </button>
          </div>

          {/* RIGHT zone: Theme, locale, auth */}
          <div className="hidden md:flex items-center gap-2 shrink-0">
            <button
              onClick={cycleTheme}
              className="text-[var(--text-muted)] hover:text-[var(--foreground)] transition-colors duration-200 text-xs px-2 py-1 rounded-md hover:bg-[var(--card-hover)] flex items-center gap-1"
              aria-label={`Theme: ${themeLabel[theme]}. Click to cycle.`}
              title={`Theme: ${themeLabel[theme]}`}
            >
              {themeIcon[theme]}
            </button>
            <button
              onClick={toggleLocale}
              className="text-[var(--text-muted)] hover:text-[var(--foreground)] transition-colors duration-200 text-xs px-2 py-1 rounded-md hover:bg-[var(--card-hover)]"
            >
              {locale === "zh-TW" ? "EN" : "繁中"}
            </button>
            {user ? (
              <>
                <span className="text-[var(--text-muted)] text-xs px-2">{user.username}</span>
                <button
                  onClick={logout}
                  className="text-[var(--text-muted)] hover:text-[var(--foreground)] transition-colors duration-200 text-xs px-2 py-1 rounded-md hover:bg-[var(--stock-up)]/10"
                >
                  {t.auth.logout}
                </button>
              </>
            ) : (
              <Link
                href="/login"
                className="text-white text-xs px-3 py-1.5 rounded-md bg-[var(--accent-blue)] hover:bg-[var(--accent-blue-hover)] transition-colors duration-200"
              >
                {t.auth.login}
              </Link>
            )}
          </div>

          {/* Mobile hamburger */}
          <button
            onClick={() => setMobileOpen(!mobileOpen)}
            className="md:hidden ml-auto p-2 text-[var(--text-muted)] hover:text-[var(--foreground)] transition-colors duration-200"
            aria-label="Toggle navigation menu"
          >
            <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              {mobileOpen ? (
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
              ) : (
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 6h16M4 12h16M4 18h16" />
              )}
            </svg>
          </button>
        </div>

        {/* Mobile menu */}
        {mobileOpen && (
          <div className="md:hidden border-t border-[var(--border-color)] animate-slide-down">
            <div className="px-4 py-3 space-y-1">
              {/* Direct links */}
              {directLinks.map((link) => (
                <Link
                  key={link.href}
                  href={link.href}
                  onClick={() => setMobileOpen(false)}
                  aria-current={isActive(link.href) ? "page" : undefined}
                  className={`block px-3 py-2.5 text-sm rounded-md transition-colors duration-200 ${
                    isActive(link.href)
                      ? "text-[var(--foreground)] bg-[var(--card-hover)]"
                      : "text-[var(--text-muted)] hover:text-[var(--foreground)] hover:bg-[var(--card-hover)]"
                  }`}
                >
                  {link.label}
                </Link>
              ))}

              {/* Grouped sections */}
              {[
                { label: t.nav.analysis, links: analysisLinks },
                { label: t.nav.trading, links: tradingLinks },
                { label: t.nav.marketGroup, links: marketLinks },
              ].map((group) => (
                <div key={group.label}>
                  <div className="px-3 pt-2 pb-1 text-[10px] text-[var(--text-muted)] uppercase tracking-wider font-medium">{group.label}</div>
                  {group.links.map((link) => (
                    <Link
                      key={link.href}
                      href={link.href}
                      onClick={() => setMobileOpen(false)}
                      aria-current={isActive(link.href) ? "page" : undefined}
                      className={`block px-3 py-2.5 text-sm rounded-md transition-colors duration-200 ${
                        isActive(link.href)
                          ? "text-[var(--foreground)] bg-[var(--card-hover)]"
                          : "text-[var(--text-muted)] hover:text-[var(--foreground)] hover:bg-[var(--card-hover)]"
                      }`}
                    >
                      {link.label}
                    </Link>
                  ))}
                </div>
              ))}

              {/* Notifications */}
              <Link
                href="/notifications"
                onClick={() => setMobileOpen(false)}
                aria-current={isActive("/notifications") ? "page" : undefined}
                className={`block px-3 py-2.5 text-sm rounded-md transition-colors duration-200 ${
                  isActive("/notifications")
                    ? "text-[var(--foreground)] bg-[var(--card-hover)]"
                    : "text-[var(--text-muted)] hover:text-[var(--foreground)] hover:bg-[var(--card-hover)]"
                }`}
              >
                {t.nav.notifications}
              </Link>

              <div className="flex items-center gap-2 pt-2 border-t border-[var(--border-color)]">
                <button
                  onClick={cycleTheme}
                  className="text-[var(--text-muted)] hover:text-[var(--foreground)] transition-colors duration-200 text-xs px-2.5 py-1.5 rounded-md border border-[var(--border-color)] flex items-center gap-1"
                  aria-label={`Theme: ${themeLabel[theme]}. Click to cycle.`}
                >
                  {themeIcon[theme]}
                  <span>{themeLabel[theme]}</span>
                </button>
                <button
                  onClick={toggleLocale}
                  className="text-[var(--text-muted)] hover:text-[var(--foreground)] transition-colors duration-200 text-xs px-2.5 py-1.5 rounded-md border border-[var(--border-color)]"
                >
                  {locale === "zh-TW" ? "EN" : "繁中"}
                </button>
                {user ? (
                  <button
                    onClick={() => { logout(); setMobileOpen(false); }}
                    className="text-[var(--text-muted)] hover:text-[var(--foreground)] transition-colors duration-200 text-xs px-2.5 py-1.5 rounded-md border border-[var(--border-color)]"
                  >
                    {t.auth.logout}
                  </button>
                ) : (
                  <Link
                    href="/login"
                    onClick={() => setMobileOpen(false)}
                    className="text-white text-xs px-3 py-1.5 rounded-md bg-[var(--accent-blue)] hover:bg-[var(--accent-blue-hover)] transition-colors duration-200"
                  >
                    {t.auth.login}
                  </Link>
                )}
              </div>
            </div>
          </div>
        )}
      </nav>
      <CommandPalette open={paletteOpen} onClose={() => setPaletteOpen(false)} />
    </>
  );
}

/** Global footer status bar -- render in layout below children */
export function FooterStatusBar() {
  return (
    <footer className="footer-status-bar mt-auto" role="contentinfo">
      <div className="flex items-center gap-2">
        <span className="status-dot" aria-hidden="true" />
        <span>Connected</span>
      </div>
      <div className="flex items-center gap-4">
        <span className="text-[var(--text-muted)]">Uni-Seeker Terminal</span>
      </div>
    </footer>
  );
}
