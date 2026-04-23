"use client";

import { useEffect, useState, useCallback } from "react";
import Link from "next/link";
import { useI18n } from "@/i18n/context";
import { fetchLowBaseRanking, type LowBaseScore, type LowBaseRanking } from "@/lib/api-client";

function scoreColor(score: number): string {
  if (score > 70) return "text-green-400 bg-green-500/15 border-green-500/30";
  if (score >= 40) return "text-yellow-400 bg-yellow-500/15 border-yellow-500/30";
  return "text-red-400 bg-red-500/15 border-red-500/30";
}

function scoreBarColor(score: number): string {
  if (score > 70) return "bg-green-500";
  if (score >= 40) return "bg-yellow-500";
  return "bg-red-500";
}

function ScoreBar({ label, value, max = 100 }: { label: string; value: number; max?: number }) {
  const pct = Math.min((value / max) * 100, 100);
  return (
    <div className="flex items-center gap-2 text-xs">
      <span className="text-[#64748b] w-16 shrink-0 truncate">{label}</span>
      <div className="flex-1 h-1.5 bg-[#0f1724] rounded-full overflow-hidden">
        <div
          className={`h-full rounded-full transition-all duration-500 ${scoreBarColor(value)}`}
          style={{ width: `${pct}%` }}
        />
      </div>
      <span className="text-[#94a3b8] w-8 text-right font-mono">{value.toFixed(0)}</span>
    </div>
  );
}

function formatPct(v: number | null): string {
  if (v == null) return "-";
  return `${(v * 100).toFixed(1)}%`;
}

function formatNum(v: number | null, decimals = 2): string {
  if (v == null) return "-";
  return v.toFixed(decimals);
}

export default function LowBasePage() {
  const { t } = useI18n();
  const lb = t.lowBase;

  const [data, setData] = useState<LowBaseRanking | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(() => {
    setLoading(true);
    setError(null);
    fetchLowBaseRanking(20)
      .then(setData)
      .catch((err) => setError(err.message))
      .finally(() => setLoading(false));
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  return (
    <div className="p-4 md:p-6 max-w-7xl mx-auto animate-fade-in">
      {/* Header */}
      <div className="flex flex-col md:flex-row md:items-end justify-between gap-4 mb-6">
        <div>
          <h1 className="text-2xl md:text-3xl font-bold text-white tracking-tight">
            {lb.title}
          </h1>
          <p className="text-[#64748b] text-sm mt-1">{lb.subtitle}</p>
        </div>
        <button
          onClick={load}
          disabled={loading}
          className="self-start md:self-auto px-4 py-2 text-sm font-medium rounded-lg bg-blue-600 hover:bg-blue-700 text-white transition-all duration-200 disabled:opacity-50 disabled:cursor-not-allowed"
        >
          {loading ? lb.scanning : "Refresh"}
        </button>
      </div>

      {/* Stats cards */}
      {data && (
        <div className="grid grid-cols-2 gap-3 mb-6">
          <div className="bg-[#1a2332] border border-[#1e293b] rounded-xl p-4">
            <span className="text-[#64748b] text-xs uppercase tracking-wider font-medium">
              {lb.scanned}
            </span>
            <p className="text-xl font-semibold text-white mt-1 font-mono">
              {data.total_scanned.toLocaleString()}
            </p>
          </div>
          <div className="bg-[#1a2332] border border-[#1e293b] rounded-xl p-4">
            <span className="text-[#64748b] text-xs uppercase tracking-wider font-medium">
              {lb.qualified}
            </span>
            <p className="text-xl font-semibold text-white mt-1 font-mono">
              {data.total_qualified.toLocaleString()}
            </p>
          </div>
        </div>
      )}

      {/* Loading */}
      {loading && (
        <div className="flex items-center justify-center py-20">
          <div className="flex flex-col items-center gap-3">
            <div className="w-8 h-8 border-2 border-[#1e293b] border-t-blue-500 rounded-full animate-spin" />
            <span className="text-[#94a3b8]">{lb.scanning}</span>
          </div>
        </div>
      )}

      {/* Error */}
      {error && !loading && (
        <div className="bg-red-500/10 border border-red-500/20 rounded-xl p-6 text-center">
          <p className="text-red-400">{error}</p>
        </div>
      )}

      {/* Empty state */}
      {data && data.results.length === 0 && !loading && (
        <div className="text-center py-20">
          <p className="text-[#64748b] text-lg">{lb.noData}</p>
        </div>
      )}

      {/* Mobile cards */}
      {data && data.results.length > 0 && (
        <div className="md:hidden space-y-3">
          {data.results.map((item: LowBaseScore, idx: number) => (
            <Link
              key={item.symbol}
              href={`/stocks/${encodeURIComponent(item.symbol)}`}
              className="block bg-[#1a2332] border border-[#1e293b] rounded-xl p-4 hover:border-[#3b82f6]/40 transition-all duration-200"
            >
              <div className="flex items-center justify-between mb-3">
                <div className="flex items-center gap-3">
                  <span className="text-[#64748b] text-sm font-mono w-6">#{idx + 1}</span>
                  <div>
                    <span className="text-white font-semibold">{item.symbol}</span>
                    <span className="text-[#64748b] text-xs ml-2">{item.name}</span>
                  </div>
                </div>
                <span
                  className={`px-2.5 py-1 text-sm font-bold rounded-lg border ${scoreColor(item.total_score)}`}
                >
                  {item.total_score.toFixed(1)}
                </span>
              </div>
              <div className="space-y-1.5">
                <ScoreBar label={lb.valuationScore} value={item.valuation_score} />
                <ScoreBar label={lb.priceScore} value={item.price_position_score} />
                <ScoreBar label={lb.qualityScore} value={item.quality_score} />
              </div>
              <div className="mt-3 flex gap-4 text-xs text-[#64748b]">
                <span>PE%: {formatPct(item.pe_percentile)}</span>
                <span>MA240: {formatPct(item.ma240_deviation)}</span>
                <span>PEG: {formatNum(item.peg)}</span>
              </div>
            </Link>
          ))}
        </div>
      )}

      {/* Desktop table */}
      {data && data.results.length > 0 && (
        <div className="hidden md:block bg-[#1a2332] border border-[#1e293b] rounded-2xl overflow-hidden shadow-xl shadow-black/20">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-[#1e293b] text-[#64748b] text-xs uppercase tracking-wider">
                <th className="px-4 py-3 text-left w-12">{lb.rank}</th>
                <th className="px-4 py-3 text-left">{lb.stock}</th>
                <th className="px-4 py-3 text-center w-24">{lb.score}</th>
                <th className="px-4 py-3 text-left w-56">{lb.details}</th>
                <th className="px-4 py-3 text-right w-28">{lb.pePercentile}</th>
                <th className="px-4 py-3 text-right w-28">{lb.maDeviation}</th>
                <th className="px-4 py-3 text-right w-20">{lb.peg}</th>
              </tr>
            </thead>
            <tbody>
              {data.results.map((item: LowBaseScore, idx: number) => (
                <tr
                  key={item.symbol}
                  className={`border-b border-[#1e293b]/50 hover:bg-[#253449]/40 transition-colors duration-150 ${
                    idx % 2 === 0 ? "bg-transparent" : "bg-[#0f1724]/30"
                  }`}
                >
                  <td className="px-4 py-3 text-[#64748b] font-mono text-xs">#{idx + 1}</td>
                  <td className="px-4 py-3">
                    <Link
                      href={`/stocks/${encodeURIComponent(item.symbol)}`}
                      className="text-white font-semibold hover:text-blue-400 transition-colors duration-150"
                    >
                      {item.symbol}
                    </Link>
                    <span className="text-[#64748b] text-xs ml-2">{item.name}</span>
                  </td>
                  <td className="px-4 py-3 text-center">
                    <span
                      className={`inline-block px-2.5 py-1 text-sm font-bold rounded-lg border ${scoreColor(item.total_score)}`}
                    >
                      {item.total_score.toFixed(1)}
                    </span>
                  </td>
                  <td className="px-4 py-3">
                    <div className="space-y-1">
                      <ScoreBar label={lb.valuationScore} value={item.valuation_score} />
                      <ScoreBar label={lb.priceScore} value={item.price_position_score} />
                      <ScoreBar label={lb.qualityScore} value={item.quality_score} />
                    </div>
                  </td>
                  <td className="px-4 py-3 text-right text-[#94a3b8] font-mono text-xs">
                    {formatPct(item.pe_percentile)}
                  </td>
                  <td className="px-4 py-3 text-right text-[#94a3b8] font-mono text-xs">
                    {formatPct(item.ma240_deviation)}
                  </td>
                  <td className="px-4 py-3 text-right text-[#94a3b8] font-mono text-xs">
                    {formatNum(item.peg)}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
