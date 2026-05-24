# STRATOS Design System Migration — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Migrate all 14 Uni-Seeker frontend pages to the STRATOS design system with dual-theme support (dark luxury terminal + light racing red).

**Architecture:** Replace current Glint-style CSS variables and NavBar with STRATOS design tokens, Rubik font, GlassPanel/ClippedButton primitives, and a new 4-category navigation (Markets/Research/Portfolio/Alerts). All hooks, API calls, and business logic remain unchanged — only the UI layer is rebuilt.

**Tech Stack:** Next.js 16 (App Router), React 19, Tailwind CSS 4, Recharts, lightweight-charts, lucide-react, Rubik (Google Fonts)

**Spec:** `docs/superpowers/specs/2026-04-30-stratos-migration-design.md`

---

## Phase 1: Foundation Layer

### Task 1: Migrate STRATOS primitives to shared location

**Files:**
- Create: `src/components/stratos/primitives.tsx`
- Create: `src/components/stratos/ambient.tsx`
- Create: `src/components/stratos/charts.tsx`
- Source: `src/app/stratos/components/primitives.tsx` (copy + modify)
- Source: `src/app/stratos/components/charts.tsx` (copy + modify)

- [ ] **Step 1:** Copy `src/app/stratos/components/primitives.tsx` to `src/components/stratos/primitives.tsx`. Extract `AmbientBackground` into its own file `src/components/stratos/ambient.tsx`.

- [ ] **Step 2:** Copy `Sparkline` and `SectorHeatmap` from `src/app/stratos/components/charts.tsx` to `src/components/stratos/charts.tsx`. Do NOT copy `PrimaryChart` (it uses mock data; real chart stays on each page).

- [ ] **Step 3:** Update `GlassPanel` in `src/components/stratos/primitives.tsx` to support dual themes. Replace the hardcoded `glassStyle` object with CSS-variable-driven styles:

```tsx
const glassStyle: React.CSSProperties = {
  background: "var(--glass-bg)",
  backdropFilter: "var(--glass-blur)",
  WebkitBackdropFilter: "var(--glass-blur)",
  border: "1px solid var(--border-color)",
  backgroundImage: "var(--glass-gradient)",
  boxShadow: "var(--glass-shadow)",
  borderRadius: "var(--glass-radius, 0)",
};
```

- [ ] **Step 4:** Update `ClippedButton` to use CSS variable `--accent-primary` instead of hardcoded `#EE3F2C` for the `red-solid` variant. Similarly use `--stock-down` for `green-solid`.

- [ ] **Step 5:** Update `KpiCard` to use `--stock-up` / `--stock-down` CSS variables instead of hardcoded hex colors.

- [ ] **Step 6:** Verify imports compile:

Run: `cd /Users/stanley/Uni-Seeker/frontend && npx tsc --noEmit`

- [ ] **Step 7:** Commit

```bash
git add src/components/stratos/
git commit -m "refactor: migrate STRATOS primitives to shared components"
```

---

### Task 2: Rewrite globals.css with STRATOS dual-theme tokens

**Files:**
- Modify: `src/app/globals.css`

- [ ] **Step 1:** Replace `:root` CSS variables with STRATOS dark theme tokens:

```css
:root {
  /* STRATOS Terminal — Dark */
  --background: #000000;
  --bg-secondary: #0a0a0a;
  --foreground: #FFFFFF;
  --card-bg: rgba(255,255,255,0.03);
  --card-hover: rgba(255,255,255,0.06);
  --card-active: rgba(255,255,255,0.09);
  --border-color: rgba(255,255,255,0.12);
  --border-subtle: rgba(255,255,255,0.06);

  --accent-primary: #EE3F2C;
  --accent-primary-hover: #d63526;
  --accent-cyan: #00E5FF;
  --text-secondary: #9CA3AF;
  --text-muted: #6B7280;

  --stock-up: #EE3F2C;
  --stock-up-bg: rgba(238,63,44,0.1);
  --stock-down: #10B981;
  --stock-down-bg: rgba(16,185,129,0.1);
  --stock-flat: #9CA3AF;

  /* Glass panel tokens */
  --glass-bg: rgba(255,255,255,0.03);
  --glass-blur: blur(40px) saturate(180%);
  --glass-gradient: linear-gradient(135deg, rgba(255,255,255,0.08) 0%, transparent 50%);
  --glass-shadow: inset 0 1px 0 rgba(255,255,255,0.1), 0 8px 32px rgba(0,0,0,0.4);
  --glass-radius: 0;

  /* Typography scale */
  --font-xs: 0.6875rem;
  --font-sm: 0.75rem;
  --font-base: 0.875rem;
  --font-lg: 1.125rem;
  --font-xl: 1.5rem;
  --font-2xl: 2rem;

  /* Page spacing */
  --page-padding: 1rem;
  --page-padding-md: 1.5rem;
  --page-max-width: 90rem;
  --header-height: 64px;
  --ticker-height: 40px;
}
```

- [ ] **Step 2:** Replace `[data-theme="light"]` with Racing Red theme:

```css
[data-theme="light"] {
  --background: #FAFAFA;
  --bg-secondary: #F0F0F0;
  --foreground: #1A1A1A;
  --card-bg: #FFFFFF;
  --card-hover: #F5F5F5;
  --card-active: #EEEEEE;
  --border-color: rgba(0,0,0,0.10);
  --border-subtle: rgba(0,0,0,0.05);

  --accent-primary: #D42B1E;
  --accent-primary-hover: #B71C1C;
  --accent-cyan: #0288D1;
  --text-secondary: #4A4A4A;
  --text-muted: #7A7A7A;

  --stock-up: #D42B1E;
  --stock-up-bg: rgba(212,43,30,0.08);
  --stock-down: #1B8A4E;
  --stock-down-bg: rgba(27,138,78,0.08);
  --stock-flat: #7A7A7A;

  /* Light glass tokens — white card + shadow */
  --glass-bg: #FFFFFF;
  --glass-blur: none;
  --glass-gradient: none;
  --glass-shadow: 0 1px 3px rgba(0,0,0,0.06), 0 4px 16px rgba(0,0,0,0.04);
  --glass-radius: 2px;
}
```

- [ ] **Step 3:** Update `body` font-family fallback and add Rubik tabular-nums utility:

```css
body {
  background: var(--background);
  color: var(--foreground);
  font-family: var(--font-rubik), 'Rubik', sans-serif;
}

.tabular-nums {
  font-variant-numeric: tabular-nums;
}
```

- [ ] **Step 4:** Update scrollbar styles to use CSS variables instead of hardcoded colors. Update `.nav-border-gradient` to use `var(--border-subtle)`. Remove old `--accent-blue*` references (replace with `--accent-primary` / `--accent-cyan`).

- [ ] **Step 5:** Add light theme nav accent line:

```css
[data-theme="light"] .nav-border-gradient {
  border-bottom: 2px solid var(--accent-primary);
}
```

- [ ] **Step 6:** Build to verify no CSS errors:

Run: `npx next build 2>&1 | tail -5`

- [ ] **Step 7:** Commit

```bash
git add src/app/globals.css
git commit -m "feat: replace CSS tokens with STRATOS dark + Racing Red light theme"
```

---

### Task 3: Rewrite root layout.tsx with Rubik font

**Files:**
- Modify: `src/app/layout.tsx`

- [ ] **Step 1:** Replace Geist font imports with Rubik:

```tsx
import { Rubik } from "next/font/google";

const rubik = Rubik({
  weight: ["300", "400", "500", "600", "700"],
  subsets: ["latin"],
  variable: "--font-rubik",
});
```

- [ ] **Step 2:** Update the `<html>` and `<body>` tags to use Rubik and remove old Geist references:

```tsx
<html lang="en" className={`${rubik.variable} h-full antialiased`}>
  <body className="min-h-full flex flex-col bg-[var(--background)] text-[var(--foreground)]" style={{ fontFamily: "'Rubik', sans-serif" }}>
```

- [ ] **Step 3:** Replace `<NavBar />` and `<FooterStatusBar />` imports with new STRATOS header (placeholder — will be built in Task 4):

```tsx
import { StratosHeader, TickerStrip } from "@/components/stratos/header";
// Remove: import { NavBar, FooterStatusBar } from "@/components/nav-bar";
```

Render order: `<StratosHeader />` → `<TickerStrip />` → `{children}`

- [ ] **Step 4:** Remove Geist_Mono import if no longer used elsewhere. Keep `ServiceWorkerRegister`.

- [ ] **Step 5:** Build to verify:

Run: `npx next build 2>&1 | tail -5`

- [ ] **Step 6:** Commit

```bash
git add src/app/layout.tsx
git commit -m "feat: replace Geist with Rubik font, swap NavBar for StratosHeader"
```

---

### Task 4: Rebuild StratosHeader with real navigation + i18n

**Files:**
- Create: `src/components/stratos/header.tsx`
- Modify: `src/i18n/locales/zh-TW.json`
- Modify: `src/i18n/locales/en.json`

- [ ] **Step 1:** Add new i18n keys to both locale files:

zh-TW.json — add to `nav`:
```json
"markets": "Markets",
"research": "Research",
"portfolio": "投資組合",
"alerts": "通知",
"marketOpen": "盤中",
"marketClosed": "休市",
"quickSearch": "搜尋"
```

en.json — add to `nav`:
```json
"markets": "Markets",
"research": "Research",
"portfolio": "Portfolio",
"alerts": "Alerts",
"marketOpen": "MARKET OPEN",
"marketClosed": "CLOSED",
"quickSearch": "Search"
```

- [ ] **Step 2:** Create `src/components/stratos/header.tsx` with `StratosHeader` component:
  - 64px fixed height, `position: sticky`, `top: 0`, `z-index: 50`
  - Background: `var(--background)` at 95% opacity + `backdrop-filter: blur(20px)`
  - Border-bottom: `1px solid var(--border-subtle)`
  - Left: SVG triangle logo + "STRATOS" wordmark
  - Center: 3 nav links (Markets `/`, Research `/research`, Portfolio `/portfolio`) + bell icon link (`/alerts`)
  - Active state: `text-[var(--foreground)]` + 2px bottom accent line using `var(--accent-primary)`
  - Right: search button (opens CommandPalette), theme toggle (cycle dark/light/system), locale toggle, auth (login/user)
  - Import and use: `useI18n`, `useAuth`, `useTheme`, `usePathname`, `CommandPalette`
  - Navigation uses `isActive()` matching: `/` exact for Markets, `/research` startsWith for Research, `/portfolio` startsWith for Portfolio, `/alerts` for Alerts

- [ ] **Step 3:** Create `TickerStrip` in same file:
  - 40px height, scrolling marquee
  - Import `useMarketIndices` from `@/hooks/use-market-data`
  - Map real `MarketIndex[]` data to ticker items
  - Color: `var(--stock-up)` for positive, `var(--stock-down)` for negative
  - CSS animation: `translateX` with seamless loop (duplicate items)
  - Pause on hover

- [ ] **Step 4:** Build + visually verify header renders:

Run: `npx next build 2>&1 | tail -5`

- [ ] **Step 5:** Commit

```bash
git add src/components/stratos/header.tsx src/i18n/locales/
git commit -m "feat: STRATOS header with real nav, i18n, ticker strip"
```

---

### Task 5: Create SubTabs shared component

**Files:**
- Create: `src/components/stratos/sub-tabs.tsx`

- [ ] **Step 1:** Create `SubTabs` component:

```tsx
"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

interface SubTab {
  href: string;
  label: string;
}

export function SubTabs({ tabs }: { tabs: SubTab[] }) {
  const pathname = usePathname();

  const isActive = (href: string) => {
    // Exact match for root of group, startsWith for sub-routes
    if (tabs[0]?.href === href) {
      return pathname === href;
    }
    return pathname.startsWith(href);
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
            isActive(tab.href)
              ? "text-[var(--foreground)] bg-[var(--card-hover)]"
              : "text-[var(--text-muted)] hover:text-[var(--foreground)]"
          }`}
          style={{
            clipPath: isActive(tab.href)
              ? "polygon(0 0, calc(100% - 8px) 0, 100% 8px, 100% 100%, 8px 100%, 0 calc(100% - 8px))"
              : undefined,
            background: isActive(tab.href) ? "var(--card-hover)" : undefined,
          }}
        >
          {tab.label}
        </Link>
      ))}
    </div>
  );
}
```

- [ ] **Step 2:** Build to verify:

Run: `npx next build 2>&1 | tail -5`

- [ ] **Step 3:** Commit

```bash
git add src/components/stratos/sub-tabs.tsx
git commit -m "feat: add SubTabs shared navigation component"
```

---

### Task 6: Update CommandPalette styling for STRATOS

**Files:**
- Modify: `src/components/command-palette.tsx`

- [ ] **Step 1:** Update the modal backdrop and container to use STRATOS glass style:
  - Backdrop: `rgba(0,0,0,0.7)` + `backdrop-filter: blur(8px)`
  - Container: use `var(--glass-bg)`, `var(--border-color)`, `var(--glass-shadow)` CSS variables
  - Input: `var(--bg-secondary)` background, `var(--foreground)` text
  - Results: hover uses `var(--card-hover)`, selected uses `var(--accent-primary)` left border

- [ ] **Step 2:** Replace any hardcoded `text-white` with `text-[var(--foreground)]` (should already be done from prior work, verify).

- [ ] **Step 3:** Build + verify search works:

Run: `npx next build 2>&1 | tail -5`

- [ ] **Step 4:** Commit

```bash
git add src/components/command-palette.tsx
git commit -m "feat: restyle CommandPalette for STRATOS theme"
```

---

### Task 7: Clean up old files + Phase 1 verification

**Files:**
- Delete: `src/components/nav-bar.tsx` (replaced by stratos/header.tsx)
- Delete: `src/app/stratos/` (demo page, no longer needed)
- Delete: `src/app/demo/` (HeroSection demo)

- [ ] **Step 1:** Remove old NavBar component. Grep for any remaining imports and update them.

Run: `grep -rn "nav-bar" src/ --include="*.tsx" --include="*.ts"`

Fix any remaining references.

- [ ] **Step 2:** Remove `src/app/stratos/` directory (demo is superseded by the real migration).

- [ ] **Step 3:** Remove `src/app/demo/` directory.

- [ ] **Step 4:** Full build verification:

Run: `npx next build`

Expected: All routes compile, no TypeScript errors.

- [ ] **Step 5:** Visual check — start dev server, verify:
  - Header renders with STRATOS style at `/`
  - TickerStrip shows real market data
  - Theme toggle cycles dark → light → system
  - Light mode shows Racing Red accent colors
  - Search (F key) opens CommandPalette
  - All existing pages still render (may look unstyled — that's Phase 2-4)

- [ ] **Step 6:** Commit

```bash
git add -A
git commit -m "chore: remove old NavBar, demo pages; Phase 1 complete"
```

---

## Phase 2: Homepage + Core Pages

### Task 8: Build homepage dashboard

**Files:**
- Rewrite: `src/app/page.tsx`

- [ ] **Step 1:** Build the `IndexPanel` component — a 2x2 grid of 4 major indices. Each cell is a GlassPanel with:
  - Index name (11px uppercase label)
  - Current value (24px bold tabular-nums)
  - Change % with direction arrow + color
  - Recharts AreaChart (100px height, gradient fill, no axes)
  - Data from `useMarketIndices()`, filtered to: 台股加權 (TAIEX), SPY, QQQ, SOX/費半

- [ ] **Step 2:** Build `MoversPanel` — 3-column grid (Gainers / Losers / Most Active). Each column is a GlassPanel with ranked stock rows. Data from `useMarketMovers()`.

- [ ] **Step 3:** Integrate existing `SectorHeatmap` (from `@/components/stratos/charts`) with real `useHeatmap()` data.

- [ ] **Step 4:** Build `WatchlistSidebar` — GlassPanel with watchlist items from `useWatchlist()`, each row with Sparkline + price + change.

- [ ] **Step 5:** Build `NewsFeedPanel` — GlassPanel with timestamped items (use mock data for now since no news API exists).

- [ ] **Step 6:** Assemble page layout:
  - KPI row (4 KpiCards)
  - Main grid: IndexPanel (8col) + WatchlistSidebar (4col)
  - Bottom grid: SectorHeatmap (4col) + MoversPanel (4col) + NewsFeed (4col)

- [ ] **Step 7:** Build + visual verify. Commit.

```bash
git commit -m "feat: rebuild homepage as STRATOS war-room dashboard"
```

---

### Task 9: Rebuild stock detail page

**Files:**
- Rewrite: `src/app/stocks/[symbol]/page.tsx`

- [ ] **Step 1:** Wrap price chart in GlassPanel. Keep existing `usePrices()` + lightweight-charts integration. Add STRATOS-styled timeframe tabs and indicator toggles.

- [ ] **Step 2:** Company info sidebar — GlassPanel with `useCompanyInfo()` data.

- [ ] **Step 3:** Financial analysis section — GlassPanel with `useFinancialAnalysis()`. KpiCards for health scores.

- [ ] **Step 4:** Margin data — GlassPanel with `useMarginData()`.

- [ ] **Step 5:** Revenue trends — GlassPanel with `useRevenue()`, Recharts BarChart.

- [ ] **Step 6:** Build + verify stock detail page loads with real data. Commit.

```bash
git commit -m "feat: rebuild stock detail page with STRATOS panels"
```

---

### Task 10: Rebuild login page

**Files:**
- Rewrite: `src/app/login/page.tsx`

- [ ] **Step 1:** Centered GlassPanel form on full-height page. Logo at top.

- [ ] **Step 2:** Styled inputs with `var(--bg-secondary)` background, `var(--border-color)` border.

- [ ] **Step 3:** ClippedButton "登入" (red-solid), "註冊" (white-solid) toggle.

- [ ] **Step 4:** Keep `useAuth()` login/register logic unchanged.

- [ ] **Step 5:** Build + verify login flow works. Commit.

```bash
git commit -m "feat: rebuild login page with STRATOS style"
```

---

## Phase 3: Research Pages

### Task 11: Research layout with SubTabs

**Files:**
- Create: `src/app/research/layout.tsx`

- [ ] **Step 1:** Create layout that renders `SubTabs` with tabs: Screener (`/research`), Scanner (`/research/scanner`), Low Base (`/research/low-base`), Compare (`/research/compare`). Wrap `{children}` below.

- [ ] **Step 2:** Commit.

```bash
git commit -m "feat: add Research layout with SubTabs"
```

---

### Task 12: Migrate Screener to `/research`

**Files:**
- Create: `src/app/research/page.tsx`
- Source: `src/app/screener/page.tsx` (copy logic)
- Source: `src/components/screener/condition-builder.tsx` (keep, restyle)

- [ ] **Step 1:** Copy screener logic. Replace all UI containers with GlassPanel. Replace buttons with ClippedButton. Replace TabGroup usage.

- [ ] **Step 2:** Restyle condition-builder to use STRATOS tokens.

- [ ] **Step 3:** Build + verify screener works with real API. Commit.

```bash
git commit -m "feat: migrate Screener to /research with STRATOS style"
```

---

### Task 13: Migrate Scanner to `/research/scanner`

**Files:**
- Create: `src/app/research/scanner/page.tsx`
- Source: `src/app/scanner/page.tsx`

- [ ] **Step 1:** Copy scanner logic. Wrap in GlassPanel. Use ClippedButton for "Start Scan". Restyle signal table.

- [ ] **Step 2:** Build + verify. Commit.

```bash
git commit -m "feat: migrate Scanner to /research/scanner"
```

---

### Task 14: Migrate Low Base to `/research/low-base`

**Files:**
- Create: `src/app/research/low-base/page.tsx`
- Source: `src/app/low-base/page.tsx`

- [ ] **Step 1:** Copy low-base logic. Use KpiCard for scan stats. GlassPanel for ranking table.

- [ ] **Step 2:** Build + verify. Commit.

```bash
git commit -m "feat: migrate Low Base to /research/low-base"
```

---

### Task 15: Migrate Compare to `/research/compare`

**Files:**
- Create: `src/app/research/compare/page.tsx`
- Source: `src/app/compare/page.tsx`

- [ ] **Step 1:** Copy compare logic. Each stock in its own GlassPanel card. Use `var(--accent-primary)` for add button.

- [ ] **Step 2:** Build + verify. Commit.

```bash
git commit -m "feat: migrate Compare to /research/compare"
```

---

## Phase 4: Portfolio, Alerts, Remaining Pages

### Task 16: Portfolio layout with SubTabs

**Files:**
- Create: `src/app/portfolio/layout.tsx`

- [ ] **Step 1:** Create layout with SubTabs: Watchlist (`/portfolio`), Backtest (`/portfolio/backtest`), Portfolio Test (`/portfolio/test`).

- [ ] **Step 2:** Commit.

```bash
git commit -m "feat: add Portfolio layout with SubTabs"
```

---

### Task 17: Migrate Watchlist to `/portfolio`

**Files:**
- Rewrite: `src/app/portfolio/page.tsx`
- Source: `src/app/watchlist/page.tsx`

- [ ] **Step 1:** Rebuild with STRATOS Watchlist style (from stratos demo). Connect to `useWatchlist()` + real price data. Keep CSV import/export. Use ClippedButton for actions.

- [ ] **Step 2:** Build + verify. Commit.

```bash
git commit -m "feat: migrate Watchlist to /portfolio with STRATOS style"
```

---

### Task 18: Migrate Backtest to `/portfolio/backtest`

**Files:**
- Rewrite: `src/app/portfolio/backtest/page.tsx`
- Source: `src/app/backtest/page.tsx` + `src/app/backtest/components/*`

- [ ] **Step 1:** Copy all backtest components. Restyle strategy-builder, queue, results, history with GlassPanel + ClippedButton. Keep all hooks unchanged.

- [ ] **Step 2:** Replace TabGroup with SubTabs or internal tab state using STRATOS-styled toggles.

- [ ] **Step 3:** Build + verify backtest flow works end-to-end. Commit.

```bash
git commit -m "feat: migrate Backtest to /portfolio/backtest"
```

---

### Task 19: Migrate Portfolio Test to `/portfolio/test`

**Files:**
- Create: `src/app/portfolio/test/page.tsx`
- Source: `src/app/portfolio/page.tsx` + `src/app/portfolio/components/*`

- [ ] **Step 1:** Copy portfolio backtest logic. Restyle allocation editor + rebalance config with GlassPanel. Use ClippedButton for run button.

- [ ] **Step 2:** Build + verify. Commit.

```bash
git commit -m "feat: migrate Portfolio Test to /portfolio/test"
```

---

### Task 20: Migrate Alerts to `/alerts`

**Files:**
- Create: `src/app/alerts/page.tsx`
- Source: `src/app/notifications/page.tsx` + `src/components/notifications/*`

- [ ] **Step 1:** Copy notification logic. GlassPanel for rule list + creation form. ClippedButton for create/delete. Keep WebSocket integration.

- [ ] **Step 2:** Build + verify. Commit.

```bash
git commit -m "feat: migrate Alerts to /alerts"
```

---

### Task 21: Rebuild Heatmap + Institutional standalone pages

**Files:**
- Rewrite: `src/app/heatmap/page.tsx`
- Rewrite: `src/app/institutional/page.tsx`

- [ ] **Step 1:** Heatmap: full-width GlassPanel wrapping `SectorHeatmap` with real `useHeatmap()` data. Add click-to-expand for sector stocks.

- [ ] **Step 2:** Institutional: GlassPanel search + date range + 3-column table (Foreign/Trust/Dealer). Keep `useInstitutional()`.

- [ ] **Step 3:** Build + verify both pages. Commit.

```bash
git commit -m "feat: rebuild Heatmap + Institutional with STRATOS style"
```

---

### Task 22: Clean up old routes + final verification

**Files:**
- Delete: `src/app/screener/` (moved to `/research`)
- Delete: `src/app/scanner/` (moved to `/research/scanner`)
- Delete: `src/app/low-base/` (moved to `/research/low-base`)
- Delete: `src/app/compare/` (moved to `/research/compare`)
- Delete: `src/app/watchlist/` (moved to `/portfolio`)
- Delete: `src/app/backtest/` (moved to `/portfolio/backtest`)
- Delete: `src/app/notifications/` (moved to `/alerts`)

- [ ] **Step 1:** Delete old route directories. Grep for any remaining imports referencing old paths.

Run: `grep -rn "from.*app/screener\|from.*app/scanner\|from.*app/watchlist\|from.*app/backtest\|from.*app/notifications\|from.*app/compare\|from.*app/low-base" src/ --include="*.tsx" --include="*.ts"`

Fix any stale references.

- [ ] **Step 2:** Full build:

Run: `npx next build`

Expected: All routes compile, zero TypeScript errors.

- [ ] **Step 3:** Visual verification checklist:
  - [ ] `/` — Dashboard with 4 index charts, KPIs, watchlist, movers, heatmap
  - [ ] `/research` — Screener with SubTabs
  - [ ] `/research/scanner` — Scanner
  - [ ] `/research/low-base` — Low Base ranking
  - [ ] `/research/compare` — Stock comparison
  - [ ] `/portfolio` — Watchlist with CSV
  - [ ] `/portfolio/backtest` — Strategy backtest
  - [ ] `/portfolio/test` — Portfolio backtest
  - [ ] `/alerts` — Notification rules
  - [ ] `/stocks/2330.TW` — Stock detail
  - [ ] `/heatmap` — Full heatmap
  - [ ] `/institutional` — Institutional flows
  - [ ] `/login` — Auth page
  - [ ] Theme toggle: dark ↔ light ↔ system
  - [ ] i18n toggle: zh-TW ↔ en
  - [ ] Search: F key opens palette
  - [ ] Responsive: 1440px, 1024px, 768px, 375px

- [ ] **Step 4:** Commit

```bash
git add -A
git commit -m "chore: remove old routes, migration complete"
```

---

## Summary

| Phase | Tasks | Key Deliverable |
|-------|-------|-----------------|
| **Phase 1** | Tasks 1-7 | Foundation: shared components, CSS tokens, header, font |
| **Phase 2** | Tasks 8-10 | Homepage dashboard, stock detail, login |
| **Phase 3** | Tasks 11-15 | Research group: screener, scanner, low-base, compare |
| **Phase 4** | Tasks 16-22 | Portfolio group, alerts, heatmap, institutional, cleanup |

Each phase ends with a buildable, verifiable state. No phase depends on a later phase.
