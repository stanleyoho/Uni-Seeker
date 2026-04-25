"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import type { ScreenResult } from "@/lib/api-client";
import { EmptyState } from "@/components/ui/empty-state";

interface ResultsTableProps {
  results: ScreenResult[];
  total: number;
}

export function ResultsTable({ results, total }: ResultsTableProps) {
  const router = useRouter();

  if (results.length === 0) {
    return (
      <EmptyState
        icon={
          <svg className="w-12 h-12" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z" />
          </svg>
        }
        message="No results. Try adjusting your conditions."
      />
    );
  }

  const indicatorKeys = Array.from(
    new Set(results.flatMap((r) => Object.keys(r.indicator_values))),
  );

  return (
    <div>
      <p className="text-sm text-[var(--text-muted)] mb-3">{total} results found</p>
      <div className="overflow-x-auto rounded-xl border border-[var(--border-color)]">
        <table className="w-full text-sm text-left">
          <thead className="text-[var(--text-muted)] text-xs uppercase tracking-wider bg-[var(--bg-secondary)]">
            <tr>
              <th className="py-3 px-4 font-medium">Symbol</th>
              {indicatorKeys.map((key) => (
                <th key={key} className="py-3 px-4 font-medium">{key}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {results.map((r, i) => (
              <tr
                key={r.symbol}
                onClick={() => router.push(`/stocks/${encodeURIComponent(r.symbol)}`)}
                className={`border-t border-[var(--border-color)] cursor-pointer transition-all duration-150 hover:bg-[var(--card-hover)] ${
                  i % 2 === 0 ? "bg-[var(--card-bg)]" : "bg-[var(--bg-secondary)]/50"
                }`}
              >
                <td className="py-3 px-4">
                  <Link
                    href={`/stocks/${encodeURIComponent(r.symbol)}`}
                    className="text-[var(--accent-blue)] hover:text-blue-300 font-mono font-semibold transition-colors duration-200"
                    onClick={(e) => e.stopPropagation()}
                  >
                    {r.symbol}
                  </Link>
                </td>
                {indicatorKeys.map((key) => (
                  <td key={key} className="py-3 px-4 font-mono text-[var(--text-secondary)]">
                    {r.indicator_values[key] != null ? Number(r.indicator_values[key]).toFixed(2) : "-"}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
