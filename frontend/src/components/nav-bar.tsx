"use client";

import Link from "next/link";
import { useI18n } from "@/i18n/context";

export function NavBar() {
  const { locale, t, setLocale } = useI18n();

  const toggleLocale = () => {
    setLocale(locale === "zh-TW" ? "en" : "zh-TW");
  };

  return (
    <nav className="border-b border-gray-800 bg-gray-900/80 backdrop-blur sticky top-0 z-50">
      <div className="max-w-6xl mx-auto flex items-center gap-6 px-4 h-12 text-sm">
        <Link href="/" className="font-bold text-white hover:text-blue-400 transition">
          Uni-Seeker
        </Link>
        <Link href="/" className="text-gray-400 hover:text-white transition">
          {t.nav.home}
        </Link>
        <Link href="/screener" className="text-gray-400 hover:text-white transition">
          {t.nav.screener}
        </Link>
        <Link href="/notifications" className="text-gray-400 hover:text-white transition">
          {t.nav.notifications}
        </Link>
        <div className="ml-auto">
          <button
            onClick={toggleLocale}
            className="text-gray-400 hover:text-white transition text-xs px-2 py-1 rounded border border-gray-700 hover:border-gray-500"
          >
            {locale === "zh-TW" ? "EN" : "繁中"}
          </button>
        </div>
      </div>
    </nav>
  );
}
