"use client";

import { useRouter } from "next/navigation";
import type { ScreenResult } from "@/lib/api-client";

interface ResultsTableProps {
  results: ScreenResult[];
  total: number;
}

export function ResultsTable({ results }: ResultsTableProps) {
  const router = useRouter();

  if (results.length === 0) {
    return (
      <div className="flex flex-col items-center justify-center py-20 px-4 text-center">
        <div className="w-16 h-16 mb-4 text-[var(--text-muted)] opacity-20">
          <svg fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z" />
          </svg>
        </div>
        <p className="text-sm font-bold text-[var(--text-muted)] uppercase tracking-widest">
          No matches found
        </p>
        <p className="text-xs text-[var(--text-muted)] mt-1">
          Try adjusting your technical filters or logic flow.
        </p>
      </div>
    );
  }

  const indicatorKeys = Array.from(
    new Set(results.flatMap((r) => Object.keys(r.indicator_values))),
  );

  return (
    <div className="animate-fade-in">
      <div className="overflow-x-auto border border-[var(--border-subtle)] bg-[var(--bg-secondary)]/30">
        <table className="w-full text-left border-collapse">
          <thead>
            <tr className="border-b border-[var(--border-subtle)] bg-[var(--bg-secondary)]">
              <th className="py-3 px-4 text-[10px] font-bold text-[var(--text-muted)] uppercase tracking-[0.15em]">Symbol</th>
              {indicatorKeys.map((key) => (
                <th key={key} className="py-3 px-4 text-[10px] font-bold text-[var(--text-muted)] uppercase tracking-[0.15em] text-right">{key}</th>
              ))}
              <th className="py-3 px-4 text-[10px] font-bold text-[var(--text-muted)] uppercase tracking-[0.15em] text-right">Action</th>
            </tr>
          </thead>
          <tbody>
            {results.map((r) => (
              <tr
                key={r.symbol}
                onClick={() => router.push(`/stocks/${encodeURIComponent(r.symbol)}`)}
                className="border-b border-[var(--border-subtle)] cursor-pointer transition-all hover:bg-[var(--card-hover)] group"
              >
                <td className="py-3 px-4">
                  <div className="flex flex-col">
                    <span className="text-sm font-bold text-[var(--foreground)] group-hover:text-[var(--accent-cyan)] transition-colors">
                      {r.symbol}
                    </span>
                    <span className="text-[10px] text-[var(--text-muted)] font-medium">MARKET DATA</span>
                  </div>
                </td>
                {indicatorKeys.map((key) => (
                  <td key={key} className="py-3 px-4 font-bold text-right tabular-nums text-[var(--text-secondary)]">
                    {r.indicator_values[key] != null ? Number(r.indicator_values[key]).toFixed(2) : "-"}
                  </td>
                ))}
                <td className="py-3 px-4 text-right">
                  <span className="text-[10px] font-bold text-[var(--accent-cyan)] opacity-0 group-hover:opacity-100 transition-opacity">
                    VIEW DETAILS →
                  </span>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
