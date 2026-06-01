/**
 * Global footer — disclaimer + data-source attribution.
 *
 * Mounted once at the root in `app/layout.tsx`. Sits at the end of the
 * flex column, OUTSIDE the `flex-1` content row, so the dashboard's
 * single-screen budget is preserved (when the page content fills the
 * viewport the footer is below the fold; when it doesn't, the footer
 * pins to the bottom of the layout column).
 *
 * Copy is verbatim from the PR spec — DO NOT translate or shorten.
 * Includes:
 *   - 資料 (data sources: TWSE / FinMind / yfinance / SEC EDGAR)
 *   - 折溢價公式 explanation
 *   - 「僅供參考，不構成投資建議」 disclaimer
 *   - © year + brand
 *
 * Layout: single line on desktop with middle-dot separators, wraps to a
 * vertical stack on mobile (line-height + tracking-tighter keeps the
 * height close to ~40 px even when it wraps).
 */
export function Footer() {
  // Year derived at render time so we don't need a yearly content update.
  // The root layout is currently a Server Component (no `"use client"`),
  // so this Date call runs once per render on the server.
  const year = new Date().getFullYear();
  return (
    <footer
      role="contentinfo"
      // Border keeps the footer visually separated from the dashboard
      // KPIs but stays muted enough not to pull focus from the data.
      className="shrink-0 border-t border-[var(--border-subtle)] bg-[var(--background)]/95 backdrop-blur-sm"
    >
      <div
        className="
          max-w-[var(--page-max-width)] mx-auto
          px-[var(--page-padding)] md:px-[var(--page-padding-md)]
          py-2
          flex flex-wrap items-center justify-center
          gap-x-2 gap-y-1
          text-[11px] leading-snug text-gray-500
        "
      >
        <span>
          資料：TWSE / FinMind / yfinance / SEC EDGAR
        </span>
        <span aria-hidden="true">·</span>
        <span>折溢價=(市價−預估淨值)/預估淨值×100%</span>
        <span aria-hidden="true">·</span>
        <span>僅供參考，不構成投資建議</span>
        <span aria-hidden="true">·</span>
        <span>© {year} Uni-Seeker</span>
      </div>
    </footer>
  );
}

export default Footer;
