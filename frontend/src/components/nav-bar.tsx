"use client";

import { useState } from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { useI18n } from "@/i18n/context";
import { useAuth } from "@/contexts/auth-context";

export function NavBar() {
  const { locale, t, setLocale } = useI18n();
  const { user, logout } = useAuth();
  const pathname = usePathname();
  const [mobileOpen, setMobileOpen] = useState(false);

  const toggleLocale = () => {
    setLocale(locale === "zh-TW" ? "en" : "zh-TW");
  };

  const navLinks = [
    { href: "/", label: t.nav.home },
    { href: "/screener", label: t.nav.screener },
    { href: "/notifications", label: t.nav.notifications },
    { href: "/backtest", label: t.nav.backtest },
  ];

  const isActive = (href: string) => {
    if (href === "/") return pathname === "/";
    return pathname.startsWith(href);
  };

  return (
    <nav className="nav-border-gradient bg-[#0a0e17]/80 backdrop-blur-xl sticky top-0 z-50">
      <div className="max-w-7xl mx-auto flex items-center justify-between px-4 h-14">
        {/* Logo */}
        <Link
          href="/"
          className="font-bold text-lg tracking-tight text-white hover:text-blue-400 transition-all duration-200"
        >
          <span className="gradient-text">Uni-Seeker</span>
        </Link>

        {/* Desktop nav links */}
        <div className="hidden md:flex items-center gap-1">
          {navLinks.map((link) => (
            <Link
              key={link.href}
              href={link.href}
              className={`relative px-3 py-2 text-sm font-medium rounded-lg transition-all duration-200 ${
                isActive(link.href)
                  ? "text-white bg-[#1e293b]"
                  : "text-[#94a3b8] hover:text-white hover:bg-[#1e293b]/50"
              }`}
            >
              {link.label}
              {isActive(link.href) && (
                <span className="absolute bottom-0 left-1/2 -translate-x-1/2 w-4 h-0.5 bg-blue-500 rounded-full" />
              )}
            </Link>
          ))}
        </div>

        {/* Right side actions */}
        <div className="hidden md:flex items-center gap-2">
          <button
            onClick={toggleLocale}
            className="text-[#94a3b8] hover:text-white transition-all duration-200 text-xs px-2.5 py-1.5 rounded-md border border-[#1e293b] hover:border-[#3b82f6]/50 hover:bg-[#1e293b]"
          >
            {locale === "zh-TW" ? "EN" : "繁中"}
          </button>
          {user ? (
            <>
              <span className="text-[#94a3b8] text-xs px-2">{user.username}</span>
              <button
                onClick={logout}
                className="text-[#94a3b8] hover:text-white transition-all duration-200 text-xs px-2.5 py-1.5 rounded-md border border-[#1e293b] hover:border-red-500/30 hover:bg-red-500/10"
              >
                {t.auth.logout}
              </button>
            </>
          ) : (
            <Link
              href="/login"
              className="text-white text-xs px-3 py-1.5 rounded-md bg-blue-600 hover:bg-blue-700 transition-all duration-200"
            >
              {t.auth.login}
            </Link>
          )}
        </div>

        {/* Mobile hamburger */}
        <button
          onClick={() => setMobileOpen(!mobileOpen)}
          className="md:hidden p-2 text-[#94a3b8] hover:text-white transition-all duration-200"
          aria-label="Toggle navigation menu"
        >
          <svg
            className="w-5 h-5"
            fill="none"
            stroke="currentColor"
            viewBox="0 0 24 24"
          >
            {mobileOpen ? (
              <path
                strokeLinecap="round"
                strokeLinejoin="round"
                strokeWidth={2}
                d="M6 18L18 6M6 6l12 12"
              />
            ) : (
              <path
                strokeLinecap="round"
                strokeLinejoin="round"
                strokeWidth={2}
                d="M4 6h16M4 12h16M4 18h16"
              />
            )}
          </svg>
        </button>
      </div>

      {/* Mobile menu */}
      {mobileOpen && (
        <div className="md:hidden border-t border-[#1e293b] animate-slide-down">
          <div className="px-4 py-3 space-y-1">
            {navLinks.map((link) => (
              <Link
                key={link.href}
                href={link.href}
                onClick={() => setMobileOpen(false)}
                className={`block px-3 py-2.5 text-sm rounded-lg transition-all duration-200 ${
                  isActive(link.href)
                    ? "text-white bg-[#1e293b]"
                    : "text-[#94a3b8] hover:text-white hover:bg-[#1e293b]/50"
                }`}
              >
                {link.label}
              </Link>
            ))}
            <div className="flex items-center gap-2 pt-2 border-t border-[#1e293b]">
              <button
                onClick={toggleLocale}
                className="text-[#94a3b8] hover:text-white transition-all duration-200 text-xs px-2.5 py-1.5 rounded-md border border-[#1e293b]"
              >
                {locale === "zh-TW" ? "EN" : "繁中"}
              </button>
              {user ? (
                <button
                  onClick={() => { logout(); setMobileOpen(false); }}
                  className="text-[#94a3b8] hover:text-white transition-all duration-200 text-xs px-2.5 py-1.5 rounded-md border border-[#1e293b]"
                >
                  {t.auth.logout}
                </button>
              ) : (
                <Link
                  href="/login"
                  onClick={() => setMobileOpen(false)}
                  className="text-white text-xs px-3 py-1.5 rounded-md bg-blue-600 hover:bg-blue-700 transition-all duration-200"
                >
                  {t.auth.login}
                </Link>
              )}
            </div>
          </div>
        </div>
      )}
    </nav>
  );
}
