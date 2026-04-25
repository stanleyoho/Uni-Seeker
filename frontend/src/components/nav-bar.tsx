"use client";

import { useState, useEffect } from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { useI18n } from "@/i18n/context";
import { useAuth } from "@/contexts/auth-context";
import { CommandPalette } from "@/components/command-palette";

export function NavBar() {
  const { locale, t, setLocale } = useI18n();
  const { user, logout } = useAuth();
  const pathname = usePathname();
  const [mobileOpen, setMobileOpen] = useState(false);
  const [moreOpen, setMoreOpen] = useState(false);
  const [paletteOpen, setPaletteOpen] = useState(false);

  const toggleLocale = () => {
    setLocale(locale === "zh-TW" ? "en" : "zh-TW");
  };

  const primaryLinks = [
    { href: "/", label: t.nav.home },
    { href: "/watchlist", label: t.nav.watchlist },
    { href: "/screener", label: t.nav.screener },
    { href: "/backtest", label: t.nav.backtest },
    { href: "/heatmap", label: t.nav.heatmap },
  ];

  const moreLinks = [
    { href: "/compare", label: t.nav.compare },
    { href: "/low-base", label: t.nav.lowBase },
    { href: "/institutional", label: t.nav.institutional },
    { href: "/notifications", label: t.nav.notifications },
  ];

  const navLinks = [...primaryLinks, ...moreLinks];

  const isActive = (href: string) => {
    if (href === "/") return pathname === "/";
    return pathname.startsWith(href);
  };

  /* Keyboard shortcut: press F to focus search (placeholder for future) */
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
      <nav className="nav-border-gradient bg-[var(--background)]/95 backdrop-blur-xl sticky top-0 z-50">
        <div className="max-w-7xl mx-auto flex items-center justify-between px-4 h-12">
          {/* Logo - text only, Glint style */}
          <Link
            href="/"
            className="font-bold text-base tracking-tight text-white hover:text-[var(--accent-blue)] transition-colors duration-200 shrink-0"
          >
            <span className="gradient-text">Uni-Seeker</span>
          </Link>

          {/* Desktop nav links - text only, no icons */}
          <div className="hidden md:flex items-center gap-0.5">
            {primaryLinks.map((link) => (
              <Link
                key={link.href}
                href={link.href}
                className={`relative px-3 py-1.5 text-[13px] font-medium rounded-md transition-colors duration-200 ${
                  isActive(link.href)
                    ? "text-white"
                    : "text-[var(--text-muted)] hover:text-white"
                }`}
              >
                {link.label}
                {isActive(link.href) && (
                  <span className="absolute bottom-0 left-1/2 -translate-x-1/2 w-4 h-[2px] bg-[var(--accent-blue)] rounded-full" />
                )}
              </Link>
            ))}

            {/* More dropdown */}
            <div className="relative">
              <button
                onClick={() => setMoreOpen(!moreOpen)}
                onBlur={() => setTimeout(() => setMoreOpen(false), 150)}
                className={`px-3 py-1.5 text-[13px] font-medium rounded-md transition-colors duration-200 ${
                  moreLinks.some((l) => isActive(l.href))
                    ? "text-white"
                    : "text-[var(--text-muted)] hover:text-white"
                }`}
              >
                More
              </button>
              {moreOpen && (
                <div className="absolute top-full right-0 mt-1 bg-[var(--card-bg)] border border-[var(--border-color)] rounded-lg shadow-xl shadow-black/60 z-50 min-w-[160px] overflow-hidden animate-slide-down">
                  {moreLinks.map((link) => (
                    <Link
                      key={link.href}
                      href={link.href}
                      onClick={() => setMoreOpen(false)}
                      className={`block px-4 py-2.5 text-[13px] transition-colors duration-150 ${
                        isActive(link.href)
                          ? "text-white bg-[var(--card-hover)]"
                          : "text-[var(--text-muted)] hover:text-white hover:bg-[var(--card-hover)]"
                      }`}
                    >
                      {link.label}
                    </Link>
                  ))}
                </div>
              )}
            </div>
          </div>

          {/* Center search bar - Glint style */}
          <button className="search-bar hidden lg:flex" aria-label="Search markets" onClick={() => setPaletteOpen(true)}>
            <svg className="w-3.5 h-3.5 text-[var(--text-muted)]" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z" />
            </svg>
            <span className="text-[var(--text-muted)]">{t.search.placeholder}</span>
            <kbd>F</kbd>
          </button>

          {/* Right side actions */}
          <div className="hidden md:flex items-center gap-2">
            <button
              onClick={toggleLocale}
              className="text-[var(--text-muted)] hover:text-white transition-colors duration-200 text-xs px-2 py-1 rounded-md hover:bg-[var(--card-hover)]"
            >
              {locale === "zh-TW" ? "EN" : "繁中"}
            </button>
            {user ? (
              <>
                <span className="text-[var(--text-muted)] text-xs px-2">{user.username}</span>
                <button
                  onClick={logout}
                  className="text-[var(--text-muted)] hover:text-white transition-colors duration-200 text-xs px-2 py-1 rounded-md hover:bg-[var(--stock-up)]/10"
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
            className="md:hidden p-2 text-[var(--text-muted)] hover:text-white transition-colors duration-200"
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
              {navLinks.map((link) => (
                <Link
                  key={link.href}
                  href={link.href}
                  onClick={() => setMobileOpen(false)}
                  className={`block px-3 py-2.5 text-sm rounded-md transition-colors duration-200 ${
                    isActive(link.href)
                      ? "text-white bg-[var(--card-hover)]"
                      : "text-[var(--text-muted)] hover:text-white hover:bg-[var(--card-hover)]"
                  }`}
                >
                  {link.label}
                </Link>
              ))}
              <div className="flex items-center gap-2 pt-2 border-t border-[var(--border-color)]">
                <button
                  onClick={toggleLocale}
                  className="text-[var(--text-muted)] hover:text-white transition-colors duration-200 text-xs px-2.5 py-1.5 rounded-md border border-[var(--border-color)]"
                >
                  {locale === "zh-TW" ? "EN" : "繁中"}
                </button>
                {user ? (
                  <button
                    onClick={() => { logout(); setMobileOpen(false); }}
                    className="text-[var(--text-muted)] hover:text-white transition-colors duration-200 text-xs px-2.5 py-1.5 rounded-md border border-[var(--border-color)]"
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
