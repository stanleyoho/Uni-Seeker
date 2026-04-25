import type { Metadata } from "next";
import { Geist, Geist_Mono } from "next/font/google";
import { I18nProvider } from "@/i18n/context";
import { AuthProvider } from "@/contexts/auth-context";
import { QueryProvider } from "@/lib/query-provider";
import { NavBar, FooterStatusBar } from "@/components/nav-bar";
import "./globals.css";

const geistSans = Geist({
  variable: "--font-geist-sans",
  subsets: ["latin"],
});

const geistMono = Geist_Mono({
  variable: "--font-geist-mono",
  subsets: ["latin"],
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
      className={`${geistSans.variable} ${geistMono.variable} h-full antialiased`}
    >
      <body className="min-h-full flex flex-col bg-[#08090d] text-[#e2e8f0]">
        <QueryProvider>
          <I18nProvider>
            <AuthProvider>
              <NavBar />
              {children}
              <FooterStatusBar />
            </AuthProvider>
          </I18nProvider>
        </QueryProvider>
      </body>
    </html>
  );
}
