"use client";

import { useEffect, useState } from "react";
import { useParams } from "next/navigation";
import Link from "next/link";
import { StockChart } from "@/components/charts/stock-chart";
import { fetchPrices, type StockPrice } from "@/lib/api-client";
import { useI18n } from "@/i18n/context";

export default function StockDetailPage() {
  const { t } = useI18n();
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

  if (loading) return <div className="p-8 text-center">{t.stock.loading}</div>;
  if (error) return <div className="p-8 text-center text-red-500">{error}</div>;

  return (
    <div className="p-4 max-w-6xl mx-auto">
      <div className="flex items-center justify-between mb-4">
        <h1 className="text-2xl font-bold">{symbol}</h1>
        <div className="flex gap-2">
          <span className="px-4 py-2 text-sm rounded-lg bg-blue-600 text-white">
            {t.stock.chart}
          </span>
          <Link
            href={`/stocks/${encodeURIComponent(symbol)}/financials`}
            className="px-4 py-2 text-sm rounded-lg bg-gray-800 text-gray-300 hover:bg-gray-700 transition"
          >
            {t.stock.financials}
          </Link>
        </div>
      </div>
      {prices.length > 0 ? (
        <>
          <div className="mb-4 grid grid-cols-4 gap-4 text-sm">
            <div>
              <span className="text-gray-400">{t.stock.open}</span>
              <p className="text-lg">{prices[0].open}</p>
            </div>
            <div>
              <span className="text-gray-400">{t.stock.close}</span>
              <p className="text-lg">{prices[0].close}</p>
            </div>
            <div>
              <span className="text-gray-400">{t.stock.high}</span>
              <p className="text-lg">{prices[0].high}</p>
            </div>
            <div>
              <span className="text-gray-400">{t.stock.low}</span>
              <p className="text-lg">{prices[0].low}</p>
            </div>
          </div>
          <StockChart prices={prices} height={500} />
        </>
      ) : (
        <p className="text-gray-400">{t.stock.noData}</p>
      )}
    </div>
  );
}
