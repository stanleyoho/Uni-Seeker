import type { Metadata } from "next";
import { Geist, Geist_Mono } from "next/font/google";
import Link from "next/link";
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
      <body className="min-h-full flex flex-col bg-gray-900 text-white">
        <nav className="border-b border-gray-800 bg-gray-900/80 backdrop-blur sticky top-0 z-50">
          <div className="max-w-6xl mx-auto flex items-center gap-6 px-4 h-12 text-sm">
            <Link href="/" className="font-bold text-white hover:text-blue-400 transition">
              Uni-Seeker
            </Link>
            <Link href="/" className="text-gray-400 hover:text-white transition">
              Home
            </Link>
            <Link href="/screener" className="text-gray-400 hover:text-white transition">
              Screener
            </Link>
            <Link href="/notifications" className="text-gray-400 hover:text-white transition">
              Notifications
            </Link>
          </div>
        </nav>
        {children}
      </body>
    </html>
  );
}
