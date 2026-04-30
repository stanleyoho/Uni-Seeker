"use client";

import { Activity, Bell } from "lucide-react";
import { ClippedButton } from "./primitives";

// ---------------------------------------------------------------------------
// Ticker data (mock)
// ---------------------------------------------------------------------------
const TICKER_DATA = [
  { symbol: "2330.TW", name: "TSMC", price: 892.0, delta: +2.34 },
  { symbol: "2317.TW", name: "Hon Hai", price: 178.5, delta: -0.89 },
  { symbol: "AAPL", name: "Apple", price: 198.45, delta: +1.12 },
  { symbol: "NVDA", name: "NVIDIA", price: 875.3, delta: +3.45 },
  { symbol: "2454.TW", name: "MediaTek", price: 1285.0, delta: -1.56 },
  { symbol: "MSFT", name: "Microsoft", price: 425.8, delta: +0.67 },
  { symbol: "GOOGL", name: "Alphabet", price: 176.92, delta: -0.34 },
  { symbol: "AMZN", name: "Amazon", price: 186.5, delta: +2.18 },
  { symbol: "2308.TW", name: "Delta Elec", price: 378.0, delta: +1.05 },
  { symbol: "META", name: "Meta", price: 502.3, delta: +1.73 },
  { symbol: "TSLA", name: "Tesla", price: 248.42, delta: -2.91 },
  { symbol: "2382.TW", name: "Quanta", price: 312.5, delta: +0.48 },
];

const NAV_LINKS = [
  { label: "Markets", active: true },
  { label: "Portfolio", active: false },
  { label: "Research", active: false },
  { label: "Alerts", active: false, icon: Bell },
];

// ---------------------------------------------------------------------------
// StratosHeader
// ---------------------------------------------------------------------------
export function StratosHeader() {
  return (
    <header
      className="sticky top-0 z-50 h-16 flex items-center"
      style={{
        background: "rgba(0,0,0,0.8)",
        backdropFilter: "blur(20px)",
        WebkitBackdropFilter: "blur(20px)",
        borderBottom: "1px solid rgba(255,255,255,0.08)",
      }}
    >
      <div className="mx-auto flex w-full max-w-[1440px] items-center justify-between px-6">
        {/* ---- LEFT: Logo ---- */}
        <div className="flex items-center gap-2.5">
          <svg
            width="28"
            height="28"
            viewBox="0 0 28 28"
            fill="none"
            xmlns="http://www.w3.org/2000/svg"
            aria-hidden
          >
            <path
              d="M14 3L25 22H3L14 3Z"
              stroke="white"
              strokeWidth="1.5"
              strokeLinejoin="round"
              fill="none"
            />
            <path
              d="M14 10L20 22H8L14 10Z"
              fill="white"
              fillOpacity="0.25"
            />
            <path
              d="M18 22L22 14"
              stroke="white"
              strokeWidth="1.5"
              strokeLinecap="round"
            />
          </svg>

          <span
            className="text-white font-bold uppercase"
            style={{
              fontFamily: "Rubik, sans-serif",
              fontSize: 18,
              letterSpacing: "-0.04em",
            }}
          >
            STRATOS
          </span>
        </div>

        {/* ---- CENTER: Market session pill ---- */}
        <div
          className="hidden md:flex items-center gap-2 rounded-full px-4 py-1.5"
          style={{
            background: "rgba(255,255,255,0.06)",
            border: "1px solid rgba(255,255,255,0.1)",
          }}
        >
          <span className="relative flex h-1.5 w-1.5">
            <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-emerald-400 opacity-75" />
            <span className="relative inline-flex h-1.5 w-1.5 rounded-full bg-emerald-500" />
          </span>

          <div className="flex items-center gap-1.5 text-[#9CA3AF]">
            <Activity size={12} strokeWidth={1.8} />
            <span
              className="uppercase"
              style={{
                fontFamily: "Rubik, sans-serif",
                fontSize: 11,
                letterSpacing: "0.08em",
              }}
            >
              Market Open
            </span>
          </div>
        </div>

        {/* ---- RIGHT: Nav + avatar + CTA ---- */}
        <div className="flex items-center gap-6">
          <nav className="hidden lg:flex items-center gap-5">
            {NAV_LINKS.map(({ label, active, icon: Icon }) => (
              <a
                key={label}
                href="#"
                className={`transition-colors ${
                  active ? "text-white" : "text-[#9CA3AF] hover:text-white"
                }`}
                style={{ fontFamily: "Rubik, sans-serif", fontSize: 13 }}
              >
                <span className="flex items-center gap-1">
                  {Icon && <Icon size={13} strokeWidth={1.8} />}
                  {label}
                </span>
              </a>
            ))}
          </nav>

          {/* Avatar */}
          <div
            className="flex h-8 w-8 items-center justify-center rounded-full"
            style={{
              background: "#1a1a1a",
              border: "1px solid rgba(255,255,255,0.12)",
            }}
          >
            <span
              className="text-white"
              style={{ fontFamily: "Rubik, sans-serif", fontSize: 11 }}
            >
              ST
            </span>
          </div>

          <ClippedButton variant="red-solid" size="sm">
            Quick Trade
          </ClippedButton>
        </div>
      </div>
    </header>
  );
}

// ---------------------------------------------------------------------------
// TickerStrip
// ---------------------------------------------------------------------------
export function TickerStrip() {
  return (
    <div
      className="relative h-10 overflow-hidden"
      style={{
        background: "rgba(0,0,0,0.6)",
        borderBottom: "1px solid rgba(255,255,255,0.06)",
      }}
    >
      {/* Inline keyframes — keeps the component self-contained */}
      <style>{`
        @keyframes ticker-scroll {
          0%   { transform: translateX(0); }
          100% { transform: translateX(-50%); }
        }
        .ticker-track {
          animation: ticker-scroll 40s linear infinite;
        }
        .ticker-track:hover {
          animation-play-state: paused;
        }
      `}</style>

      <div className="ticker-track flex h-full items-center whitespace-nowrap">
        {/* Render the list twice for seamless loop */}
        {[0, 1].map((copy) => (
          <div key={copy} className="flex items-center">
            {TICKER_DATA.map((t) => {
              const isPositive = t.delta >= 0;
              // Asia convention: red = up, green = down
              const color = isPositive ? "#EE3F2C" : "#10B981";
              const sign = isPositive ? "+" : "";
              return (
                <div
                  key={`${copy}-${t.symbol}`}
                  className="flex items-center gap-2 px-5"
                  style={{ fontFamily: "Rubik, sans-serif" }}
                >
                  <span className="font-bold text-white" style={{ fontSize: 12 }}>
                    {t.symbol}
                  </span>
                  <span className="text-[#9CA3AF]" style={{ fontSize: 12 }}>
                    {t.name}
                  </span>
                  <span
                    className="text-white"
                    style={{
                      fontSize: 12,
                      fontVariantNumeric: "tabular-nums",
                    }}
                  >
                    ${t.price.toFixed(2)}
                  </span>
                  <span
                    style={{
                      color,
                      fontSize: 12,
                      fontVariantNumeric: "tabular-nums",
                    }}
                  >
                    {sign}
                    {t.delta.toFixed(2)}%
                  </span>
                </div>
              );
            })}
          </div>
        ))}
      </div>
    </div>
  );
}
