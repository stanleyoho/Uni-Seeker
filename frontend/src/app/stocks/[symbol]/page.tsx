"use client";

import { useEffect, useState } from "react";
import { useParams } from "next/navigation";
import { StockChart } from "@/components/charts/stock-chart";
import { fetchPrices, type StockPrice } from "@/lib/api-client";

export default function StockDetailPage() {
  const params = useParams<{ symbol: string }>();
  const symbol = decodeURIComponent(params.symbol);
  const [prices, setPrices] = useState<StockPrice[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    fetchPrices(symbol, 120)
      .then((res) => {
        if (!cancelled) setPrices(res.data);
      })
      .catch((err) => {
        if (!cancelled) setError(err.message);
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [symbol]);

  if (loading) return <div className="p-8 text-center">Loading...</div>;
  if (error) return <div className="p-8 text-center text-red-500">{error}</div>;

  return (
    <div className="p-4 max-w-6xl mx-auto">
      <h1 className="text-2xl font-bold mb-4">{symbol}</h1>
      {prices.length > 0 ? (
        <>
          <div className="mb-4 grid grid-cols-4 gap-4 text-sm">
            <div>
              <span className="text-gray-400">Open</span>
              <p className="text-lg">{prices[0].open}</p>
            </div>
            <div>
              <span className="text-gray-400">Close</span>
              <p className="text-lg">{prices[0].close}</p>
            </div>
            <div>
              <span className="text-gray-400">High</span>
              <p className="text-lg">{prices[0].high}</p>
            </div>
            <div>
              <span className="text-gray-400">Low</span>
              <p className="text-lg">{prices[0].low}</p>
            </div>
          </div>
          <StockChart prices={prices} height={500} />
        </>
      ) : (
        <p className="text-gray-400">No price data available</p>
      )}
    </div>
  );
}
