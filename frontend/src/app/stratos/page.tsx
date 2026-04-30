"use client";

import { useState, useMemo } from "react";
import { StratosHeader, TickerStrip } from "./components/header";
import { AmbientBackground, KpiCard } from "./components/primitives";
import { PrimaryChart, SectorHeatmap } from "./components/charts";
import { Watchlist, OrderBook, NewsFeed, QuickActions } from "./components/panels";
import {
  SYMBOLS,
  SECTORS,
  NEWS_ITEMS,
  generateOHLCV,
  generateOrderBook,
} from "./components/mock-data";

export default function StratosPage() {
  const [selectedSymbol] = useState(SYMBOLS[0]);

  const ohlcv = useMemo(
    () => generateOHLCV(selectedSymbol.price, 60),
    [selectedSymbol.price],
  );

  const orderBook = useMemo(() => generateOrderBook(), []);

  return (
    <div className="relative min-h-screen" style={{ background: "#000" }}>
      <AmbientBackground />

      {/* Header + Ticker */}
      <StratosHeader />
      <TickerStrip />

      {/* Main Grid */}
      <main
        className="relative z-10 mx-auto px-4 md:px-6 py-4"
        style={{ maxWidth: 1440 }}
      >
        {/* KPI Row */}
        <div className="grid grid-cols-2 lg:grid-cols-4 gap-4 mb-4">
          <KpiCard
            label="Portfolio Value"
            value="$2,847,350"
            delta="+3.24%"
            direction="up"
          />
          <KpiCard
            label="Daily P&L"
            value="+$48,720"
            delta="+1.74%"
            direction="up"
          />
          <KpiCard
            label="Win Rate"
            value="68.4%"
            delta="+2.1%"
            direction="up"
          />
          <KpiCard
            label="Active Positions"
            value="12"
            delta="-2"
            direction="down"
          />
        </div>

        {/* Top Row: Chart + Watchlist */}
        <div className="grid grid-cols-1 lg:grid-cols-12 gap-4 mb-4">
          <div className="lg:col-span-8">
            <PrimaryChart symbol={selectedSymbol.symbol} data={ohlcv} />
          </div>
          <div className="lg:col-span-4">
            <Watchlist symbols={SYMBOLS} />
          </div>
        </div>

        {/* Mid Row: Heatmap + OrderBook + News */}
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-12 gap-4 mb-4">
          <div className="lg:col-span-4">
            <SectorHeatmap data={SECTORS} />
          </div>
          <div className="lg:col-span-4">
            <OrderBook bids={orderBook.bids} asks={orderBook.asks} />
          </div>
          <div className="lg:col-span-4">
            <NewsFeed items={NEWS_ITEMS} />
          </div>
        </div>

        {/* Bottom Row: Quick Actions */}
        <div className="grid grid-cols-1 lg:grid-cols-12 gap-4">
          <div className="lg:col-span-4 lg:col-start-9">
            <QuickActions symbol={selectedSymbol.symbol} />
          </div>
        </div>
      </main>
    </div>
  );
}
