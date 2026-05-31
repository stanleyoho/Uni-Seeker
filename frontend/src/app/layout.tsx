import type { Metadata } from "next";
import { Rubik } from "next/font/google";
import { I18nProvider } from "@/i18n/context";
import { AuthProvider } from "@/contexts/auth-context";
import { ThemeProvider } from "@/contexts/theme-context";
import { QueryProvider } from "@/lib/query-provider";
import { StratosHeader } from "@/components/stratos/header";
import { ServiceWorkerRegister } from "@/components/sw-register";
import { OnboardingProvider } from "@/contexts/onboarding-context";
import { OnboardingResetHook } from "@/components/onboarding/reset-button";
import { WatchlistRail } from "@/components/watchlist/WatchlistRail";
import { CommandPalette } from "@/components/command-palette/CommandPalette";
import "./globals.css";

const rubik = Rubik({
  weight: ["300", "400", "500", "600", "700"],
  subsets: ["latin"],
  variable: "--font-rubik",
});

export const metadata: Metadata = {
  title: "Uni-Seeker",
  description: "Taiwan + US Stock Analysis Platform",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html
      lang="en"
      className={`${rubik.variable} h-full antialiased`}
    >
      <body className="min-h-full flex flex-col bg-[var(--background)] text-[var(--foreground)]">
        <ThemeProvider>
          <QueryProvider>
            <I18nProvider>
              <AuthProvider>
                <OnboardingProvider>
                  <StratosHeader />
                  {/*
                    Main content + persistent watchlist rail.
                    - On <lg, the rail collapses to `hidden` (mobile users
                      get the dedicated /watchlist + portfolio surface).
                    - On lg+, the rail sits as a 240px sticky column to the
                      right of the children. flex-1 lets the page absorb the
                      remaining horizontal room; min-w-0 stops long ticker
                      strips from forcing the column wider than the viewport.
                  */}
                  <div className="flex-1 flex flex-row min-h-0">
                    <div className="flex-1 min-w-0 flex flex-col">
                      {children}
                    </div>
                    <WatchlistRail />
                  </div>
                  <CommandPalette />
                  <ServiceWorkerRegister />
                  <OnboardingResetHook />
                </OnboardingProvider>
              </AuthProvider>
            </I18nProvider>
          </QueryProvider>
        </ThemeProvider>
      </body>
    </html>
  );
}
