"use client";

import { useState, useEffect } from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { Bell } from "lucide-react";
import { useI18n } from "@/i18n/context";
import { useAuth } from "@/contexts/auth-context";
import { useTheme } from "@/contexts/theme-context";
import { CommandPalette } from "@/components/command-palette";
import { useMarketIndices } from "@/hooks/use-market-data";
import type { MarketIndex } from "@/lib/api-client";

/* =========================================
   StratosHeader — 64px fixed-height sticky
   ========================================= */

export function StratosHeader() {
  const { locale, t, setLocale } = useI18n();
  const { user, logout } = useAuth();
  const { theme, setTheme } = useTheme();
  const pathname = usePathname();
  const [mobileOpen, setMobileOpen] = useState(false);
  const [paletteOpen, setPaletteOpen] = useState(false);

  const isActive = (href: string) => {
    if (href === "/") return pathname === "/";
    return pathname.startsWith(href);
  };

  const cycleTheme = () => {
    const next: Record<string, "light" | "system" | "dark"> = {
      dark: "light",
      light: "system",
      system: "dark",
    };
    setTheme(next[theme]);
  };

  const themeIcon: Record<string, React.ReactNode> = {
    dark: (
      <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24" aria-hidden="true">
        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M20.354 15.354A9 9 0 018.646 3.646 9.003 9.003 0 0012 21a9.003 9.003 0 008.354-5.646z" />
      </svg>
    ),
    light: (
      <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24" aria-hidden="true">
        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 3v1m0 16v1m9-9h-1M4 12H3m15.364 6.364l-.707-.707M6.343 6.343l-.707-.707m12.728 0l-.707.707M6.343 17.657l-.707.707M16 12a4 4 0 11-8 0 4 4 0 018 0z" />
      </svg>
    ),
    system: (
      <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24" aria-hidden="true">
        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9.75 17L9 20l-1 1h8l-1-1-.75-3M3 13h18M5 17h14a2 2 0 002-2V5a2 2 0 00-2-2H5a2 2 0 00-2 2v10a2 2 0 002 2z" />
      </svg>
    ),
  };

  const themeLabel: Record<string, string> = {
    dark: "Dark",
    light: "Light",
    system: "System",
  };

  const toggleLocale = () => {
    setLocale(locale === "zh-TW" ? "en" : "zh-TW");
  };

  const navLinks = [
    { href: "/", label: t.nav.markets ?? "Markets" },
    { href: "/research", label: t.nav.research ?? "Research" },
    { href: "/portfolio", label: t.nav.portfolio ?? "Portfolio" },
  ];

  /* Keyboard shortcut: press F to open CommandPalette */
  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      if (e.key === "f" && !e.metaKey && !e.ctrlKey && !e.altKey) {
        const active = document.activeElement;
        if (active && (active.tagName === "INPUT" || active.tagName === "TEXTAREA" || (active as HTMLElement).isContentEditable)) return;
        e.preventDefault();
        setPaletteOpen(true);
      }
    };
    window.addEventListener("keydown", handler);
    return () => window.removeEventListener("keydown", handler);
  }, []);

  // Close mobile menu on route change
  useEffect(() => {
    setMobileOpen(false);
  }, [pathname]);

  return (
    <>
      <header
        className="nav-border-gradient sticky top-0 z-50 h-16"
        style={{
          background: "color-mix(in srgb, var(--background) 95%, transparent)",
          backdropFilter: "blur(20px)",
          WebkitBackdropFilter: "blur(20px)",
        }}
      >
        <div className="max-w-[1440px] mx-auto px-6 flex items-center h-full">
          {/* LEFT: Logo + Wordmark */}
          <Link href="/" className="flex items-center gap-2.5 shrink-0">
            {/* SVG triangle logo — abstract upward arrow */}
            <svg
              width="28"
              height="28"
              viewBox="0 0 28 28"
              fill="none"
              aria-hidden="true"
            >
              <path
                d="M14 3L25 23H3L14 3Z"
                fill="var(--foreground)"
                opacity="0.9"
              />
              <path
                d="M14 8L20 20H8L14 8Z"
                fill="var(--accent-primary, #ef4444)"
                opacity="0.8"
              />
            </svg>
            <span
              className="font-bold text-[18px] uppercase"
              style={{
                color: "var(--foreground)",
                letterSpacing: "-0.04em",
              }}
            >
              Uni-Seeker
            </span>
          </Link>

          {/* CENTER: Nav links + search */}
          <div className="hidden md:flex flex-1 items-center justify-center gap-1">
            {navLinks.map((link) => (
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
                  <span
                    className="absolute bottom-0 left-1/2 -translate-x-1/2 w-6 h-[2px] rounded-full"
                    style={{ background: "var(--accent-primary)" }}
                  />
                )}
              </Link>
            ))}

            {/* Bell icon — Alerts */}
            <Link
              href="/alerts"
              aria-current={isActive("/alerts") ? "page" : undefined}
              className={`relative px-2 py-1.5 rounded-md transition-colors duration-200 ${
                isActive("/alerts")
                  ? "text-[var(--foreground)]"
                  : "text-[var(--text-muted)] hover:text-[var(--foreground)]"
              }`}
              title={t.nav.alerts ?? "Alerts"}
            >
              <Bell className="w-4 h-4" />
              {isActive("/alerts") && (
                <span
                  className="absolute bottom-0 left-1/2 -translate-x-1/2 w-4 h-[2px] rounded-full"
                  style={{ background: "var(--accent-primary)" }}
                />
              )}
            </Link>

            {/* Search button — opens CommandPalette */}
            <button
              className="search-bar hidden lg:flex ml-2"
              aria-label={t.nav.quickSearch ?? "Search"}
              onClick={() => setPaletteOpen(true)}
            >
              <svg className="w-3.5 h-3.5 text-[var(--text-muted)]" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z" />
              </svg>
              <span className="text-[var(--text-muted)]">{t.nav.quickSearch ?? "Search"}</span>
              <kbd>F</kbd>
            </button>
          </div>

          {/* RIGHT: Theme, locale, auth */}
          <div className="hidden md:flex shrink-0 items-center gap-2">
            <button
              onClick={cycleTheme}
              className="text-[var(--text-muted)] hover:text-[var(--foreground)] transition-colors duration-200 p-1.5 rounded-md hover:bg-[var(--card-hover)]"
              aria-label={`Theme: ${themeLabel[theme]}. Click to cycle.`}
              title={`Theme: ${themeLabel[theme]}`}
            >
              {themeIcon[theme]}
            </button>

            <button
              onClick={toggleLocale}
              className="text-[var(--text-muted)] hover:text-[var(--foreground)] transition-colors duration-200 text-xs px-2 py-1 rounded-md hover:bg-[var(--card-hover)] font-medium"
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
                className="text-white text-xs px-3 py-1.5 rounded-md transition-colors duration-200"
                style={{
                  background: "var(--accent-primary)",
                }}
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

        {/* Mobile menu — slide down */}
        {mobileOpen && (
          <div className="md:hidden border-t border-[var(--border-color)] animate-slide-down" style={{ background: "var(--background)" }}>
            <div className="px-4 py-3 space-y-1">
              {navLinks.map((link) => (
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

              <Link
                href="/alerts"
                onClick={() => setMobileOpen(false)}
                aria-current={isActive("/alerts") ? "page" : undefined}
                className={`flex items-center gap-2 px-3 py-2.5 text-sm rounded-md transition-colors duration-200 ${
                  isActive("/alerts")
                    ? "text-[var(--foreground)] bg-[var(--card-hover)]"
                    : "text-[var(--text-muted)] hover:text-[var(--foreground)] hover:bg-[var(--card-hover)]"
                }`}
              >
                <Bell className="w-4 h-4" />
                {t.nav.alerts ?? "Alerts"}
              </Link>

              {/* Search button for mobile */}
              <button
                onClick={() => { setMobileOpen(false); setPaletteOpen(true); }}
                className="w-full flex items-center gap-2 px-3 py-2.5 text-sm text-[var(--text-muted)] hover:text-[var(--foreground)] hover:bg-[var(--card-hover)] rounded-md transition-colors duration-200"
              >
                <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z" />
                </svg>
                {t.nav.quickSearch ?? "Search"}
              </button>

              <div className="flex items-center gap-2 pt-2 border-t border-[var(--border-color)]">
                <button
                  onClick={cycleTheme}
                  className="text-[var(--text-muted)] hover:text-[var(--foreground)] transition-colors duration-200 text-xs px-2.5 py-1.5 rounded-md border border-[var(--border-color)] flex items-center gap-1"
                  aria-label={`Theme: ${themeLabel[theme]}`}
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
                    className="text-white text-xs px-3 py-1.5 rounded-md transition-colors duration-200"
                    style={{ background: "var(--accent-primary)" }}
                  >
                    {t.auth.login}
                  </Link>
                )}
              </div>
            </div>
          </div>
        )}
      </header>

      {/* Ticker strip right below header */}
      <TickerStrip />

      <CommandPalette open={paletteOpen} onClose={() => setPaletteOpen(false)} />
    </>
  );
}

/* =========================================
   TickerStrip — 40px height, CSS marquee
   ========================================= */

function TickerStrip() {
  const { data: indices, isLoading } = useMarketIndices();

  if (isLoading || !indices || indices.length === 0) {
    return (
      <div
        className="h-10 flex items-center justify-center text-xs"
        style={{
          background: "var(--bg-secondary)",
          borderBottom: "1px solid var(--border-subtle)",
          color: "var(--text-muted)",
        }}
      >
        Loading indices...
      </div>
    );
  }

  // If fewer than 3 indices, render a static row instead of scrolling marquee
  if (indices.length < 3) {
    return (
      <div className="h-10 flex items-center justify-center gap-6" style={{
        background: "var(--bg-secondary)",
        borderBottom: "1px solid var(--border-subtle)",
      }}>
        {indices.map((item) => {
          const chg = Number(item.change_percent);
          return (
            <div key={item.symbol} className="flex items-center gap-2">
              <span className="text-[12px] font-bold" style={{ color: "var(--foreground)" }}>{item.name}</span>
              <span className="text-[12px]" style={{ color: "var(--foreground)", fontVariantNumeric: "tabular-nums" }}>{Number(item.value).toLocaleString(undefined, { minimumFractionDigits: 2 })}</span>
              <span className="text-[12px] font-medium" style={{ color: chg >= 0 ? "var(--stock-up)" : "var(--stock-down)", fontVariantNumeric: "tabular-nums" }}>
                {chg >= 0 ? "+" : ""}{chg.toFixed(2)}%
              </span>
            </div>
          );
        })}
      </div>
    );
  }

  // Duplicate for seamless loop
  const items: MarketIndex[] = [...indices, ...indices];

  return (
    <div
      className="h-10 overflow-hidden relative group"
      style={{
        background: "var(--bg-secondary)",
        borderBottom: "1px solid var(--border-subtle)",
      }}
    >
      <div
        className="flex items-center h-full whitespace-nowrap"
        style={{
          animation: `ticker-scroll ${Math.max(indices.length * 4, 20)}s linear infinite`,
        }}
        onMouseEnter={(e) => { e.currentTarget.style.animationPlayState = 'paused'; }}
        onMouseLeave={(e) => { e.currentTarget.style.animationPlayState = 'running'; }}
      >
        {items.map((item, i) => {
          const chg = Number(item.change_percent);
          return (
            <div key={`${item.symbol}-${i}`} className="flex items-center gap-2 px-4 shrink-0">
              <span className="text-[12px] font-bold" style={{ color: "var(--foreground)" }}>
                {item.name || item.symbol}
              </span>
              <span className="text-[12px] tabular-nums" style={{ color: "var(--foreground)" }}>
                {Number(item.value).toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
              </span>
              <span
                className="text-[12px] tabular-nums font-medium"
                style={{
                  color: chg >= 0
                    ? "var(--stock-up)"
                    : "var(--stock-down)",
                }}
              >
                {chg >= 0 ? "+" : ""}
                {chg.toFixed(2)}%
              </span>
            </div>
          );
        })}
      </div>

      {/* CSS keyframe for marquee — injected inline */}
      <style>{`
        @keyframes ticker-scroll {
          0% { transform: translateX(0); }
          100% { transform: translateX(-50%); }
        }
      `}</style>
    </div>
  );
}
