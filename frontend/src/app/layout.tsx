import type { Metadata } from "next";
import { Rubik } from "next/font/google";
import { I18nProvider } from "@/i18n/context";
import { AuthProvider } from "@/contexts/auth-context";
import { ThemeProvider } from "@/contexts/theme-context";
import { QueryProvider } from "@/lib/query-provider";
import { NavBar, FooterStatusBar } from "@/components/nav-bar";
import { ServiceWorkerRegister } from "@/components/sw-register";
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
                <NavBar />
                {children}
                <FooterStatusBar />
                <ServiceWorkerRegister />
              </AuthProvider>
            </I18nProvider>
          </QueryProvider>
        </ThemeProvider>
      </body>
    </html>
  );
}
