"use client";

import React, { useState } from "react";
import { Eye, Layers, Bell, Zap, TrendingUp, TrendingDown } from "lucide-react";
import { GlassPanel, ClippedButton } from "./primitives";
import { Sparkline } from "./charts";
import { generateSparkline } from "./mock-data";

/* ------------------------------------------------------------------ */
/*  Shared styles                                                      */
/* ------------------------------------------------------------------ */

const tabNums: React.CSSProperties = { fontVariantNumeric: "tabular-nums" };

/* ------------------------------------------------------------------ */
/*  1. Watchlist                                                       */
/* ------------------------------------------------------------------ */

interface WatchlistSymbol {
  symbol: string;
  name: string;
  price: number;
  change: number;
  sector: string;
}

interface WatchlistProps {
  symbols: WatchlistSymbol[];
}

export function Watchlist({ symbols }: WatchlistProps) {
  const [selectedIdx, setSelectedIdx] = useState(0);

  return (
    <GlassPanel
      title="Watchlist"
      icon={<Eye size={14} strokeWidth={2} color="#9CA3AF" />}
      noPadding
    >
      <table style={{ width: "100%", borderCollapse: "collapse" }}>
        <thead>
          <tr>
            {["Symbol", "Last", "Chg %", ""].map((h) => (
              <th
                key={h}
                style={{
                  fontSize: 11,
                  fontWeight: 700,
                  textTransform: "uppercase",
                  color: "#9CA3AF",
                  textAlign: "left",
                  padding: "0 12px 8px",
                  letterSpacing: "0.04em",
                }}
              >
                {h}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {symbols.map((s, i) => {
            const isSelected = i === selectedIdx;
            const isPositive = s.change >= 0;

            return (
              <tr
                key={s.symbol}
                onClick={() => setSelectedIdx(i)}
                style={{
                  cursor: "pointer",
                  borderLeft: isSelected
                    ? "2px solid #EE3F2C"
                    : "2px solid transparent",
                  background: isSelected
                    ? "rgba(238,63,44,0.06)"
                    : "transparent",
                  transition: "background 150ms",
                }}
                onMouseEnter={(e) => {
                  if (!isSelected) {
                    e.currentTarget.style.background =
                      "rgba(255,255,255,0.02)";
                  }
                }}
                onMouseLeave={(e) => {
                  e.currentTarget.style.background = isSelected
                    ? "rgba(238,63,44,0.06)"
                    : "transparent";
                }}
              >
                {/* Symbol + Name */}
                <td style={{ padding: "8px 12px" }}>
                  <div
                    style={{
                      fontSize: 13,
                      fontWeight: 700,
                      color: "#fff",
                      lineHeight: 1.2,
                    }}
                  >
                    {s.symbol}
                  </div>
                  <div
                    style={{
                      fontSize: 11,
                      color: "#9CA3AF",
                      lineHeight: 1.2,
                    }}
                  >
                    {s.name}
                  </div>
                </td>

                {/* Last Price */}
                <td
                  style={{
                    padding: "8px 12px",
                    fontSize: 13,
                    color: "#fff",
                    ...tabNums,
                  }}
                >
                  {s.price.toFixed(2)}
                </td>

                {/* Change % */}
                <td
                  style={{
                    padding: "8px 12px",
                    fontSize: 12,
                    color: isPositive ? "#EE3F2C" : "#10B981",
                    ...tabNums,
                  }}
                >
                  {isPositive ? "▲" : "▼"}{" "}
                  {Math.abs(s.change).toFixed(2)}%
                </td>

                {/* Sparkline */}
                <td style={{ padding: "8px 12px", width: 64 }}>
                  <Sparkline
                    data={generateSparkline(s.price)}
                    color={isPositive ? "#EE3F2C" : "#10B981"}
                    width={56}
                    height={20}
                  />
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </GlassPanel>
  );
}

/* ------------------------------------------------------------------ */
/*  2. OrderBook                                                       */
/* ------------------------------------------------------------------ */

interface OrderLevel {
  price: number;
  size: number;
  total: number;
}

interface OrderBookProps {
  bids: OrderLevel[];
  asks: OrderLevel[];
}

export function OrderBook({ bids, asks }: OrderBookProps) {
  const maxTotal = Math.max(
    ...asks.map((a) => a.total),
    ...bids.map((b) => b.total),
    1,
  );

  const sortedAsks = [...asks].sort((a, b) => b.price - a.price);
  const sortedBids = [...bids].sort((a, b) => b.price - a.price);

  const spread =
    sortedAsks.length > 0 && sortedBids.length > 0
      ? sortedAsks[sortedAsks.length - 1].price - sortedBids[0].price
      : 0;
  const spreadPct =
    sortedBids.length > 0 && sortedBids[0].price > 0
      ? (spread / sortedBids[0].price) * 100
      : 0;

  const headerStyle: React.CSSProperties = {
    fontSize: 11,
    fontWeight: 700,
    textTransform: "uppercase",
    color: "#9CA3AF",
    textAlign: "right",
    padding: "0 8px 6px",
    letterSpacing: "0.04em",
  };

  const renderRow = (
    level: OrderLevel,
    side: "ask" | "bid",
  ) => {
    const color = side === "ask" ? "#EE3F2C" : "#10B981";
    const barWidth = `${(level.total / maxTotal) * 100}%`;

    return (
      <tr key={`${side}-${level.price}`} style={{ position: "relative" }}>
        <td
          style={{
            fontSize: 13,
            color,
            padding: "3px 8px",
            textAlign: "right",
            ...tabNums,
          }}
        >
          {level.price.toFixed(2)}
        </td>
        <td
          style={{
            fontSize: 13,
            color: "#fff",
            padding: "3px 8px",
            textAlign: "right",
            ...tabNums,
          }}
        >
          {level.size.toLocaleString()}
        </td>
        <td
          style={{
            fontSize: 13,
            color: "#fff",
            padding: "3px 8px",
            textAlign: "right",
            position: "relative",
            ...tabNums,
          }}
        >
          {/* Volume bar */}
          <div
            style={{
              position: "absolute",
              top: 0,
              right: 0,
              bottom: 0,
              width: barWidth,
              background:
                side === "ask"
                  ? "rgba(238,63,44,0.08)"
                  : "rgba(16,185,129,0.08)",
              pointerEvents: "none",
            }}
          />
          <span style={{ position: "relative", zIndex: 1 }}>
            {level.total.toLocaleString()}
          </span>
        </td>
      </tr>
    );
  };

  return (
    <GlassPanel
      title="Order Book"
      icon={<Layers size={14} strokeWidth={2} color="#9CA3AF" />}
      noPadding
    >
      <table style={{ width: "100%", borderCollapse: "collapse" }}>
        <thead>
          <tr>
            <th style={{ ...headerStyle, textAlign: "right" }}>Price</th>
            <th style={headerStyle}>Size</th>
            <th style={headerStyle}>Total</th>
          </tr>
        </thead>

        {/* Asks */}
        <tbody>{sortedAsks.map((a) => renderRow(a, "ask"))}</tbody>
      </table>

      {/* Spread */}
      <div
        style={{
          fontSize: 11,
          color: "#9CA3AF",
          textAlign: "center",
          padding: "6px 8px",
          borderTop: "1px solid rgba(255,255,255,0.06)",
          borderBottom: "1px solid rgba(255,255,255,0.06)",
          ...tabNums,
        }}
      >
        Spread: {spread.toFixed(2)} ({spreadPct.toFixed(2)}%)
      </div>

      {/* Bids */}
      <table style={{ width: "100%", borderCollapse: "collapse" }}>
        <tbody>{sortedBids.map((b) => renderRow(b, "bid"))}</tbody>
      </table>
    </GlassPanel>
  );
}

/* ------------------------------------------------------------------ */
/*  3. NewsFeed                                                        */
/* ------------------------------------------------------------------ */

interface NewsItem {
  time: string;
  title: string;
  severity: "positive" | "negative" | "neutral";
  source: string;
}

interface NewsFeedProps {
  items: NewsItem[];
}

const severityColor: Record<NewsItem["severity"], string> = {
  positive: "#10B981",
  negative: "#EE3F2C",
  neutral: "#9CA3AF",
};

export function NewsFeed({ items }: NewsFeedProps) {
  return (
    <GlassPanel
      title="News & Alerts"
      icon={<Bell size={14} strokeWidth={2} color="#9CA3AF" />}
    >
      <div style={{ maxHeight: 320, overflowY: "auto" }}>
        {items.map((item, i) => (
          <React.Fragment key={i}>
            {i > 0 && (
              <div
                style={{
                  height: 1,
                  background: "rgba(255,255,255,0.06)",
                }}
              />
            )}
            <div
              style={{
                display: "flex",
                alignItems: "center",
                gap: 10,
                padding: "10px 0",
              }}
            >
              {/* Time */}
              <span
                style={{
                  fontSize: 11,
                  color: "#9CA3AF",
                  minWidth: 40,
                  ...tabNums,
                }}
              >
                {item.time}
              </span>

              {/* Severity dot */}
              <span
                style={{
                  width: 6,
                  height: 6,
                  borderRadius: "50%",
                  background: severityColor[item.severity],
                  flexShrink: 0,
                }}
              />

              {/* Title */}
              <span
                style={{
                  fontSize: 13,
                  color: "#fff",
                  flex: 1,
                }}
              >
                {item.title}
              </span>

              {/* Source */}
              <span
                style={{
                  fontSize: 11,
                  color: "#9CA3AF",
                  fontStyle: "italic",
                  flexShrink: 0,
                }}
              >
                {item.source}
              </span>
            </div>
          </React.Fragment>
        ))}
      </div>
    </GlassPanel>
  );
}

/* ------------------------------------------------------------------ */
/*  4. QuickActions                                                    */
/* ------------------------------------------------------------------ */

interface QuickActionsProps {
  symbol: string;
}

export function QuickActions({ symbol }: QuickActionsProps) {
  const [shares, setShares] = useState("100");

  return (
    <GlassPanel
      title="Quick Actions"
      icon={<Zap size={14} strokeWidth={2} color="#9CA3AF" />}
    >
      {/* Symbol display */}
      <div
        style={{
          fontSize: 18,
          fontWeight: 700,
          color: "#fff",
          marginBottom: 16,
        }}
      >
        {symbol}
      </div>

      {/* Shares input */}
      <div style={{ marginBottom: 16 }}>
        <label
          style={{
            display: "block",
            fontSize: 11,
            fontWeight: 600,
            color: "#9CA3AF",
            textTransform: "uppercase",
            letterSpacing: "0.04em",
            marginBottom: 6,
          }}
        >
          Shares
        </label>
        <input
          type="text"
          value={shares}
          onChange={(e) => setShares(e.target.value)}
          style={{
            width: "100%",
            padding: "8px 12px",
            fontSize: 14,
            color: "#fff",
            background: "rgba(255,255,255,0.05)",
            border: "1px solid rgba(255,255,255,0.12)",
            borderRadius: 0,
            outline: "none",
            ...tabNums,
          }}
        />
      </div>

      {/* Action buttons */}
      <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
        <ClippedButton variant="red-solid" size="lg" className="w-full">
          BUY {symbol}
        </ClippedButton>
        <ClippedButton variant="green-solid" size="lg" className="w-full">
          SELL {symbol}
        </ClippedButton>
        <ClippedButton variant="cyan-ghost" size="md" className="w-full">
          Set Alert
        </ClippedButton>
      </div>
    </GlassPanel>
  );
}
