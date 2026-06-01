"use client";

import { useState, useEffect, useRef } from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { Bell, Settings } from "lucide-react";
import { useI18n } from "@/i18n/context";
import { useAuth } from "@/contexts/auth-context";
import { useTheme } from "@/contexts/theme-context";
import { CMDK_OPEN_EVENT } from "@/components/command-palette/CommandPalette";
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
  const [settingsOpen, setSettingsOpen] = useState(false);
  const [overflowOpen, setOverflowOpen] = useState(false);
  const settingsRef = useRef<HTMLDivElement | null>(null);
  const overflowRef = useRef<HTMLDivElement | null>(null);
  // The legacy local `paletteOpen` state is gone — the global CommandPalette
  // (mounted by app/layout.tsx) owns its own open state and listens for
  // ⌘K / Ctrl+K plus the CMDK_OPEN_EVENT CustomEvent dispatched here.
  const openPalette = () => {
    if (typeof window !== "undefined") {
      window.dispatchEvent(new CustomEvent(CMDK_OPEN_EVENT));
    }
  };

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

  // Primary top-nav: the surfaces a day-trader actually opens in a
  // typical session. Heatmap + Institutional (13F) were demoted to
  // the "更多" overflow dropdown below because:
  //   - /heatmap is reachable from the home page's Hot Sectors cards
  //     (each card already links to `/heatmap?focus=<sector>`), so
  //     keeping it in the primary strip duplicated an entry that
  //     almost never gets clicked directly.
  //   - /institutional ships SEC 13F data, which is US-only +
  //     quarterly. PR #112 K5 added the TW 三大法人 row on the home
  //     page, so the TW day-trader's primary institutional flow now
  //     lives on /; 13F is a niche power-user surface that doesn't
  //     earn a top-nav slot.
  const navLinks = [
    { href: "/", label: t.nav.markets ?? "Markets" },
    { href: "/research", label: t.nav.research ?? "Research" },
    { href: "/portfolio", label: t.nav.portfolio ?? "Portfolio" },
    { href: "/holdings", label: t.nav.holdings ?? "Holdings" },
    { href: "/journal", label: t.nav.journal ?? "Journal" },
  ];

  // Secondary "更多" overflow menu — opt-in surfaces the user can
  // reach from the dropdown or from inline links elsewhere (e.g. Hot
  // Sectors cards → /heatmap). Pages themselves stay fully
  // functional; only the nav prominence changed.
  const overflowLinks = [
    { href: "/heatmap", label: t.nav.heatmap ?? "熱力圖" },
    { href: "/institutional", label: t.nav.institutional ?? "機構持倉" },
  ];

  /* Keyboard shortcut: press F to open the global CommandPalette (the new
     ⌘K palette also listens to ⌘K directly; this preserves the existing F
     muscle memory from PR #109 by dispatching the same CustomEvent.) */
  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      if (e.key === "f" && !e.metaKey && !e.ctrlKey && !e.altKey) {
        const active = document.activeElement;
        if (active && (active.tagName === "INPUT" || active.tagName === "TEXTAREA" || (active as HTMLElement).isContentEditable)) return;
        e.preventDefault();
        window.dispatchEvent(new CustomEvent(CMDK_OPEN_EVENT));
      }
    };
    window.addEventListener("keydown", handler);
    return () => window.removeEventListener("keydown", handler);
  }, []);

  // Close mobile menu + settings dropdown on route change. The rule
  // flags the sync setState pair; the documented derive-during-render
  // alternative requires a ref + same-render setState, which
  // react-hooks/refs flags in turn. Disable inline with rationale --
  // pathname is an external (router) transition that we mirror into
  // local UI state.
  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect -- collapse open menus when the router transitions to a new pathname
    setMobileOpen(false);
    setSettingsOpen(false);
    setOverflowOpen(false);
  }, [pathname]);

  // Close settings dropdown on outside click / Esc.
  useEffect(() => {
    if (!settingsOpen) return;
    const handleClick = (e: MouseEvent) => {
      if (
        settingsRef.current &&
        !settingsRef.current.contains(e.target as Node)
      ) {
        setSettingsOpen(false);
      }
    };
    const handleKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") setSettingsOpen(false);
    };
    window.addEventListener("mousedown", handleClick);
    window.addEventListener("keydown", handleKey);
    return () => {
      window.removeEventListener("mousedown", handleClick);
      window.removeEventListener("keydown", handleKey);
    };
  }, [settingsOpen]);

  // Mirror the settings-dropdown dismissal handlers for the new
  // "更多" overflow menu. Same shape so the two menus stay
  // behaviourally consistent — outside-click + Esc both close. A
  // shared util would be cleaner, but cloning the 4 lines keeps each
  // menu's lifecycle self-contained for the next reader.
  useEffect(() => {
    if (!overflowOpen) return;
    const handleClick = (e: MouseEvent) => {
      if (
        overflowRef.current &&
        !overflowRef.current.contains(e.target as Node)
      ) {
        setOverflowOpen(false);
      }
    };
    const handleKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") setOverflowOpen(false);
    };
    window.addEventListener("mousedown", handleClick);
    window.addEventListener("keydown", handleKey);
    return () => {
      window.removeEventListener("mousedown", handleClick);
      window.removeEventListener("keydown", handleKey);
    };
  }, [overflowOpen]);

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

            {/* 更多 (More) overflow — hosts demoted nav entries
                (heatmap + institutional). Styled to match the Settings
                dropdown so users learn the convention "secondary nav
                lives behind an inline dropdown trigger" once.  The
                active underline is preserved when the active route
                belongs to the overflow, so the user still knows where
                they are. */}
            <div className="relative" ref={overflowRef}>
              <button
                onClick={() => setOverflowOpen((v) => !v)}
                aria-haspopup="menu"
                aria-expanded={overflowOpen}
                aria-label={t.nav.more ?? "更多"}
                className={`relative px-3 py-1.5 text-[13px] font-medium rounded-md transition-colors duration-200 flex items-center gap-1 ${
                  overflowLinks.some((l) => isActive(l.href))
                    ? "text-[var(--foreground)]"
                    : "text-[var(--text-muted)] hover:text-[var(--foreground)]"
                }`}
              >
                {t.nav.more ?? "更多"}
                <svg className="w-3 h-3" fill="none" stroke="currentColor" viewBox="0 0 24 24" aria-hidden="true">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 9l-7 7-7-7" />
                </svg>
                {overflowLinks.some((l) => isActive(l.href)) && (
                  <span
                    className="absolute bottom-0 left-1/2 -translate-x-1/2 w-6 h-[2px] rounded-full"
                    style={{ background: "var(--accent-primary)" }}
                  />
                )}
              </button>
              {overflowOpen && (
                <div
                  role="menu"
                  className="absolute left-0 mt-2 min-w-[180px] py-1 z-50"
                  style={{
                    background: "var(--background)",
                    border: "1px solid var(--border-color)",
                    boxShadow:
                      "0 8px 24px color-mix(in srgb, #000 40%, transparent)",
                  }}
                >
                  {overflowLinks.map((link) => (
                    <Link
                      key={link.href}
                      href={link.href}
                      role="menuitem"
                      onClick={() => setOverflowOpen(false)}
                      aria-current={isActive(link.href) ? "page" : undefined}
                      className="block px-3 py-2 text-[13px] transition-colors duration-150 hover:bg-[var(--card-hover)]"
                      style={{
                        color: isActive(link.href)
                          ? "var(--foreground)"
                          : "var(--text-secondary)",
                      }}
                    >
                      {link.label}
                    </Link>
                  ))}
                </div>
              )}
            </div>

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
              onClick={openPalette}
            >
              <svg className="w-3.5 h-3.5 text-[var(--text-muted)]" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z" />
              </svg>
              <span className="text-[var(--text-muted)]">{t.nav.quickSearch ?? "Search"}</span>
              <kbd>⌘K</kbd>
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

            {/* Settings dropdown — gear icon → notification prefs (Round 9 Y7) */}
            <div className="relative" ref={settingsRef}>
              <button
                onClick={() => setSettingsOpen((v) => !v)}
                aria-haspopup="menu"
                aria-expanded={settingsOpen}
                aria-label={
                  (t.settings && (t.settings as { title?: string }).title) ??
                  "Settings"
                }
                className={`p-1.5 rounded-md transition-colors duration-200 hover:bg-[var(--card-hover)] ${
                  pathname.startsWith("/settings")
                    ? "text-[var(--foreground)]"
                    : "text-[var(--text-muted)] hover:text-[var(--foreground)]"
                }`}
              >
                <Settings className="w-4 h-4" />
              </button>
              {settingsOpen && (
                <div
                  role="menu"
                  className="absolute right-0 mt-2 min-w-[200px] py-1 z-50"
                  style={{
                    background: "var(--background)",
                    border: "1px solid var(--border-color)",
                    boxShadow:
                      "0 8px 24px color-mix(in srgb, #000 40%, transparent)",
                  }}
                >
                  <Link
                    href="/settings/notifications"
                    role="menuitem"
                    onClick={() => setSettingsOpen(false)}
                    className="block px-3 py-2 text-[13px] transition-colors duration-150 hover:bg-[var(--card-hover)]"
                    style={{
                      color: pathname.startsWith("/settings/notifications")
                        ? "var(--foreground)"
                        : "var(--text-secondary)",
                    }}
                  >
                    {(t.settings &&
                      (t.settings as { notifications?: { title?: string } })
                        .notifications?.title) ??
                      "通知設定"}
                  </Link>
                  <Link
                    href="/settings/audit"
                    role="menuitem"
                    onClick={() => setSettingsOpen(false)}
                    className="block px-3 py-2 text-[13px] transition-colors duration-150 hover:bg-[var(--card-hover)]"
                    style={{
                      color: pathname.startsWith("/settings/audit")
                        ? "var(--foreground)"
                        : "var(--text-secondary)",
                    }}
                  >
                    {(t.settings &&
                      (t.settings as { audit?: { title?: string } }).audit
                        ?.title) ??
                      "操作紀錄"}
                  </Link>
                  <Link
                    href="/settings/alerts"
                    role="menuitem"
                    onClick={() => setSettingsOpen(false)}
                    className="block px-3 py-2 text-[13px] transition-colors duration-150 hover:bg-[var(--card-hover)]"
                    style={{
                      color: pathname.startsWith("/settings/alerts")
                        ? "var(--foreground)"
                        : "var(--text-secondary)",
                    }}
                  >
                    {(t.settings &&
                      (t.settings as { alerts?: { title?: string } }).alerts
                        ?.title) ??
                      "我的提醒規則"}
                  </Link>
                </div>
              )}
            </div>

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

              {/* Mobile overflow surfaces — same demoted entries the
                  desktop "更多" dropdown owns. Inline here (rather
                  than a nested mobile dropdown) because the mobile
                  menu is already a vertical sheet; another
                  collapsible would be noise. The dimmer styling
                  subtly signals secondary priority without hiding
                  the rows. */}
              {overflowLinks.map((link) => (
                <Link
                  key={link.href}
                  href={link.href}
                  onClick={() => setMobileOpen(false)}
                  aria-current={isActive(link.href) ? "page" : undefined}
                  className={`block px-3 py-2.5 text-sm rounded-md transition-colors duration-200 opacity-80 ${
                    isActive(link.href)
                      ? "text-[var(--foreground)] bg-[var(--card-hover)] opacity-100"
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

              <Link
                href="/settings/notifications"
                onClick={() => setMobileOpen(false)}
                aria-current={
                  isActive("/settings/notifications") ? "page" : undefined
                }
                className={`flex items-center gap-2 px-3 py-2.5 text-sm rounded-md transition-colors duration-200 ${
                  isActive("/settings/notifications")
                    ? "text-[var(--foreground)] bg-[var(--card-hover)]"
                    : "text-[var(--text-muted)] hover:text-[var(--foreground)] hover:bg-[var(--card-hover)]"
                }`}
              >
                <Settings className="w-4 h-4" />
                {(t.settings &&
                  (t.settings as { notifications?: { title?: string } })
                    .notifications?.title) ??
                  "通知設定"}
              </Link>

              <Link
                href="/settings/audit"
                onClick={() => setMobileOpen(false)}
                aria-current={
                  isActive("/settings/audit") ? "page" : undefined
                }
                className={`flex items-center gap-2 px-3 py-2.5 text-sm rounded-md transition-colors duration-200 ${
                  isActive("/settings/audit")
                    ? "text-[var(--foreground)] bg-[var(--card-hover)]"
                    : "text-[var(--text-muted)] hover:text-[var(--foreground)] hover:bg-[var(--card-hover)]"
                }`}
              >
                <Settings className="w-4 h-4" />
                {(t.settings &&
                  (t.settings as { audit?: { title?: string } }).audit
                    ?.title) ??
                  "操作紀錄"}
              </Link>

              <Link
                href="/settings/alerts"
                onClick={() => setMobileOpen(false)}
                aria-current={
                  isActive("/settings/alerts") ? "page" : undefined
                }
                className={`flex items-center gap-2 px-3 py-2.5 text-sm rounded-md transition-colors duration-200 ${
                  isActive("/settings/alerts")
                    ? "text-[var(--foreground)] bg-[var(--card-hover)]"
                    : "text-[var(--text-muted)] hover:text-[var(--foreground)] hover:bg-[var(--card-hover)]"
                }`}
              >
                <Bell className="w-4 h-4" />
                {(t.settings &&
                  (t.settings as { alerts?: { title?: string } }).alerts
                    ?.title) ??
                  "我的提醒規則"}
              </Link>

              {/* Search button for mobile */}
              <button
                onClick={() => { setMobileOpen(false); openPalette(); }}
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

      {/* CommandPalette is mounted globally by app/layout.tsx — the search
          button + F shortcut above dispatch CMDK_OPEN_EVENT to open it. */}
    </>
  );
}

/* =========================================
   TickerStrip — 40px height, TW + US clusters
   =========================================
   Visually groups indices by region: TW cluster on the left
   (TAIEX / 0050 / OTC / 加權...), US cluster on the right
   (S&P / NDX / SOX / DJI...), separated by a vertical divider.
   Each cluster has a small "TW" / "US" label so the eye knows
   which market a quote belongs to without parsing the symbol.

   Horizontal scroll is preserved: the whole strip overflows-x and
   the inner row is `whitespace-nowrap`. The marquee animation
   from the previous version is intentionally removed so the
   region labels remain in place — users now scroll manually when
   the cluster overflows, which is more legible for a fixed
   2-cluster layout. */

/** Classify a MarketIndex into TW / US / Other by symbol + name patterns. */
function classifyIndexRegion(idx: MarketIndex): "TW" | "US" | "Other" {
  const s = idx.symbol || "";
  const n = idx.name || "";
  if (
    /\.TW$/i.test(s) ||
    /\.TWO$/i.test(s) ||
    /^\^TWII$/i.test(s) ||
    /^\^TPEX$/i.test(s) ||
    /TAIEX|加權|櫃買|OTC/i.test(n)
  ) {
    return "TW";
  }
  if (
    /^SPY$|^QQQ$|^DIA$|^IWM$/i.test(s) ||
    /^\^(GSPC|IXIC|DJI|NDX|SOX|RUT)$/i.test(s) ||
    /S&P|NASDAQ|Dow Jones|Russell|Philadelphia|Semiconductor|費半/i.test(n)
  ) {
    return "US";
  }
  return "Other";
}

function ClusterLabel({ label }: { label: string }) {
  return (
    <span
      className="text-[10px] font-bold uppercase tracking-[0.12em] px-2 py-0.5 shrink-0"
      style={{
        color: "var(--text-muted)",
        background: "color-mix(in srgb, var(--foreground) 6%, transparent)",
        border: "1px solid var(--border-subtle)",
        borderRadius: 2,
      }}
    >
      {label}
    </span>
  );
}

function TickerQuote({ item }: { item: MarketIndex }) {
  const chg = Number(item.change_percent);
  const isUp = chg >= 0;
  return (
    <div className="flex items-center gap-2 px-3 shrink-0">
      <span
        className="text-[12px] font-bold"
        style={{ color: "var(--foreground)" }}
      >
        {item.name || item.symbol}
      </span>
      <span
        className="text-[12px] tabular-nums"
        style={{ color: "var(--foreground)" }}
      >
        {Number(item.value).toLocaleString(undefined, {
          minimumFractionDigits: 2,
          maximumFractionDigits: 2,
        })}
      </span>
      <span
        className="text-[12px] tabular-nums font-medium"
        style={{ color: isUp ? "var(--stock-up)" : "var(--stock-down)" }}
      >
        {isUp ? "+" : ""}
        {chg.toFixed(2)}%
      </span>
    </div>
  );
}

function TickerCluster({
  label,
  items,
}: {
  label: string;
  items: MarketIndex[];
}) {
  if (items.length === 0) return null;
  return (
    <div className="flex items-center gap-1 h-full shrink-0">
      <ClusterLabel label={label} />
      {items.map((item) => (
        <TickerQuote key={item.symbol} item={item} />
      ))}
    </div>
  );
}

function ClusterDivider() {
  return (
    <span
      aria-hidden="true"
      className="shrink-0 mx-2"
      style={{
        width: 1,
        height: 20,
        background: "var(--border-color)",
      }}
    />
  );
}

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

  const tw: MarketIndex[] = [];
  const us: MarketIndex[] = [];
  const other: MarketIndex[] = [];
  for (const idx of indices) {
    const region = classifyIndexRegion(idx);
    if (region === "TW") tw.push(idx);
    else if (region === "US") us.push(idx);
    else other.push(idx);
  }

  return (
    <div
      className="h-10 overflow-x-auto overflow-y-hidden scrollbar-hide"
      style={{
        background: "var(--bg-secondary)",
        borderBottom: "1px solid var(--border-subtle)",
      }}
    >
      <div className="flex items-center h-full whitespace-nowrap px-4 gap-1">
        <TickerCluster label="TW" items={tw} />
        {tw.length > 0 && us.length > 0 && <ClusterDivider />}
        <TickerCluster label="US" items={us} />
        {other.length > 0 && (us.length > 0 || tw.length > 0) && (
          <ClusterDivider />
        )}
        <TickerCluster label="ETC" items={other} />
      </div>
    </div>
  );
}
